import os, hashlib, hmac, secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from database.db import db_enabled, session

PBKDF2_ROUNDS = int(os.getenv("PASSWORD_PBKDF2_ROUNDS", "310000"))
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"

def _verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False

def init_auth_tables():
    if not db_enabled():
        return
    with session() as c:
        c.execute(text("""
        create table if not exists app_users (
          id uuid primary key default gen_random_uuid(),
          user_id text unique not null,
          full_name text not null,
          email text unique not null,
          password_hash text not null,
          role text not null default 'Researcher',
          status text not null default 'active',
          created_at timestamptz not null default now(),
          approved_at timestamptz,
          last_login timestamptz
        )
        """))
        c.execute(text("""
        create table if not exists app_sessions (
          id uuid primary key default gen_random_uuid(),
          token_hash text unique not null,
          user_id text not null references app_users(user_id) on delete cascade,
          created_at timestamptz not null default now(),
          expires_at timestamptz not null
        )
        """))
        c.execute(text("create index if not exists idx_app_sessions_token on app_sessions(token_hash)"))
        c.execute(text("create index if not exists idx_app_users_status on app_users(status)"))
        _ensure_owner(c)

def _ensure_owner(c):
    owner_id = os.getenv("OWNER_USER_ID", "swapnil.pathare").strip()
    owner_name = os.getenv("OWNER_NAME", "Swapnil Sudhakar Pathare").strip()
    owner_email = os.getenv("OWNER_EMAIL", "").strip()
    owner_password = os.getenv("OWNER_PASSWORD", "")
    if not owner_email or not owner_password:
        return
    row = c.execute(text("select user_id from app_users where user_id=:uid"), {"uid": owner_id}).first()
    if not row:
        c.execute(text("""insert into app_users
          (user_id, full_name, email, password_hash, role, status, approved_at)
          values (:uid,:name,:email,:phash,'Owner','active',now())
        """), {"uid": owner_id, "name": owner_name, "email": owner_email, "phash": _hash_password(owner_password)})
    else:
        c.execute(text("""update app_users set role='Owner', status='active', full_name=:name, email=:email
                          where user_id=:uid"""),
                  {"uid": owner_id, "name": owner_name, "email": owner_email})

def _user(row):
    if not row:
        return None
    return {
        "userId": row["user_id"], "name": row["full_name"], "email": row["email"],
        "role": row["role"], "status": row["status"], "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
        "lastLogin": row["last_login"].isoformat() if row["last_login"] else None
    }

def register(user_id: str, full_name: str, email: str, password: str):
    if not db_enabled():
        raise RuntimeError("Central authentication requires DATABASE_URL")
    uid, name, em = user_id.strip(), full_name.strip(), email.strip().lower()
    if not uid or not name or not em or len(password) < 6:
        raise ValueError("All fields are required and password must be at least 6 characters.")
    with session() as c:
        if c.execute(text("select 1 from app_users where lower(user_id)=lower(:uid)"), {"uid": uid}).first():
            raise ValueError("That User ID already exists.")
        if c.execute(text("select 1 from app_users where lower(email)=lower(:email)"), {"email": em}).first():
            raise ValueError("That email address is already registered.")
        c.execute(text("""insert into app_users(user_id,full_name,email,password_hash,role,status,approved_at)
                         values(:uid,:name,:email,:phash,'Researcher','active',now())"""),
                  {"uid":uid,"name":name,"email":em,"phash":_hash_password(password)})
        row=c.execute(text("select * from app_users where user_id=:uid"),{"uid":uid}).mappings().first()
        return _user(row)

def login(user_id: str, password: str):
    with session() as c:
        row=c.execute(text("select * from app_users where lower(user_id)=lower(:uid)"),{"uid":user_id.strip()}).mappings().first()
        if not row or not _verify_password(password, row["password_hash"]):
            raise ValueError("Invalid User ID or password.")
        if row["status"] != "active":
            raise ValueError(f"Account is {row['status']}.")
        token=secrets.token_urlsafe(48)
        expires=datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        c.execute(text("insert into app_sessions(token_hash,user_id,expires_at) values(:th,:uid,:exp)"),
                  {"th":token_hash,"uid":row["user_id"],"exp":expires})
        c.execute(text("update app_users set last_login=now() where user_id=:uid"),{"uid":row["user_id"]})
        return token, _user(row)

def current_user(token: str):
    if not token:
        return None
    th=hashlib.sha256(token.encode()).hexdigest()
    with session() as c:
        row=c.execute(text("""select u.* from app_sessions s join app_users u on u.user_id=s.user_id
                              where s.token_hash=:th and s.expires_at>now()"""),{"th":th}).mappings().first()
        return _user(row)

def logout(token: str):
    if not token:
        return
    th=hashlib.sha256(token.encode()).hexdigest()
    with session() as c:
        c.execute(text("delete from app_sessions where token_hash=:th"),{"th":th})

def require_user(token: str):
    user=current_user(token)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user

def require_owner(token: str):
    user=require_user(token)
    if user["role"].lower() != "owner":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Owner access required.")
    return user
