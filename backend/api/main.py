from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path

# Support both a project-root .env and backend/.env. The backend file wins when both exist.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)
from uuid import uuid4

from services.research import ResearchService
from services.dataset import DatasetStore
from database.db import db_enabled, fetch_all, session
from services.providers import search_provider_status
from sqlalchemy import text
from services.auth import init_auth_tables, register as auth_register, login as auth_login, current_user, logout as auth_logout, require_owner

app = FastAPI(title="AI Market Research & Strategy Engine", version="1.2.0")
bearer_scheme = HTTPBearer(auto_error=False)

@app.on_event("startup")
def startup_auth():
    init_auth_tables()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = ResearchService()
dataset = DatasetStore()


class RegisterRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=6, max_length=200)

class LoginRequest(BaseModel):
    user_id: str
    password: str

def bearer_token(authorization: str = ""):
    return authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""

@app.post("/api/auth/register")
def auth_register_endpoint(req: RegisterRequest):
    try:
        user=auth_register(req.user_id, req.full_name, req.email, req.password)
        return {"user":user}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

@app.post("/api/auth/login")
def auth_login_endpoint(req: LoginRequest):
    try:
        token,user=auth_login(req.user_id, req.password)
        return {"token":token,"user":user}
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

@app.get("/api/auth/me")
def auth_me(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    user = current_user(credentials.credentials)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid."
        )

    return {"user": user}

@app.post("/api/auth/logout")
def auth_logout_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    auth_logout(credentials.credentials)

    return {"ok": True}

class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200)

@app.patch("/api/auth/profile")
def auth_profile(req: ProfileUpdateRequest, authorization: str = Header("")):
    token=bearer_token(authorization)
    user=current_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    try:
        with session() as c:
            exists=c.execute(text("select 1 from app_users where lower(email)=lower(:email) and user_id<>:uid"),{"email":req.email.strip(),"uid":user["userId"]}).first()
            if exists: raise ValueError("That email address is already registered.")
            c.execute(text("update app_users set full_name=:name,email=:email where user_id=:uid"),
                      {"name":req.full_name.strip(),"email":req.email.strip().lower(),"uid":user["userId"]})
            row=c.execute(text("select * from app_users where user_id=:uid"),{"uid":user["userId"]}).mappings().first()
            return {"user": {
                "userId":row["user_id"],"name":row["full_name"],"email":row["email"],"role":row["role"],
                "status":row["status"],"createdAt":row["created_at"].isoformat() if row["created_at"] else None,
                "lastLogin":row["last_login"].isoformat() if row["last_login"] else None
            }}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/admin/users")
def admin_users(authorization: str = Header("")):
    require_owner(bearer_token(authorization))
    rows=fetch_all("""select user_id,full_name,email,role,status,created_at,approved_at,last_login
                      from app_users order by created_at desc""")
    return {"items":[dict(r) for r in rows]}

@app.post("/api/admin/users/{user_id}/suspend")
def admin_suspend(user_id: str, authorization: str = Header("")):
    owner=require_owner(bearer_token(authorization))
    if user_id == owner["userId"]:
        raise HTTPException(status_code=400, detail="The permanent owner cannot be suspended.")
    with session() as c:
        c.execute(text("update app_users set status='suspended' where user_id=:uid and role<>'Owner'"),{"uid":user_id})
    return {"ok":True}

@app.post("/api/admin/users/{user_id}/reactivate")
def admin_reactivate(user_id: str, authorization: str = Header("")):
    require_owner(bearer_token(authorization))
    with session() as c:
        c.execute(text("update app_users set status='active', approved_at=coalesce(approved_at,now()) where user_id=:uid"),{"uid":user_id})
    return {"ok":True}

@app.delete("/api/admin/users/{user_id}")
def admin_delete(user_id: str, authorization: str = Header("")):
    owner=require_owner(bearer_token(authorization))
    if user_id == owner["userId"]:
        raise HTTPException(status_code=400, detail="The permanent owner cannot be deleted.")
    with session() as c:
        c.execute(text("delete from app_users where user_id=:uid and role<>'Owner'"),{"uid":user_id})
    return {"ok":True}


class ResearchRequest(BaseModel):
    query: str = Field(min_length=5)
    market: str = ""
    geography: str = ""
    timeframe: str = ""
    competitors: list[str] = []
    output_format: str = "internal review"
    report_depth: str = "standard"


def job_or_404(job_id: str):
    try:
        return service.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Research job not found")


@app.get("/health")
def health():
    return {"status": "ok", "database": db_enabled(), "data_source": "database" if dataset.live else "demo"}


@app.post("/api/research-jobs")
def create_job(req: ResearchRequest):
    jid = str(uuid4())
    return service.create(jid, req.model_dump())


@app.post("/api/research-run")
def run_research(req: ResearchRequest):
    jid = str(uuid4())
    service.create(jid, req.model_dump())
    try:
        return service.run_full(jid)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/research-plan")
def plan(job_id: str):
    job_or_404(job_id)
    return service.plan(job_id)


@app.post("/api/browse")
def browse(job_id: str):
    job_or_404(job_id)
    return service.browse(job_id)


@app.post("/api/extract-evidence")
def extract(job_id: str):
    job_or_404(job_id)
    return service.extract(job_id)


@app.post("/api/validate-evidence")
def validate(job_id: str):
    job_or_404(job_id)
    return service.validate(job_id)


@app.post("/api/aggregate")
def aggregate(job_id: str):
    job_or_404(job_id)
    return service.aggregate(job_id)


@app.post("/api/generate-report")
def report(job_id: str):
    job_or_404(job_id)
    return service.report(job_id)


@app.post("/api/review")
def review(job_id: str):
    job_or_404(job_id)
    return service.review(job_id)


@app.get("/api/reports/{job_id}")
def get_report(job_id: str):
    return job_or_404(job_id)


@app.post("/api/feedback")
def feedback(job_id: str, action: str, notes: str = ""):
    job_or_404(job_id)
    return service.feedback(job_id, action, notes)


@app.get("/api/data/overview")
def data_overview(market: str = "All", geography: str = "All"):
    return dataset.overview(market, geography)

@app.get("/api/data/filters")
def data_filters():
    return dataset.filters()

@app.get("/api/data/evidence")
def data_evidence(page: int = 1, page_size: int = 20, market: str = "All", topic: str = "All", validation: str = "All", search: str = ""):
    return dataset.evidence_page(page, page_size, market, topic, validation, search)

@app.get("/api/data/sources")
def data_sources(page: int = 1, page_size: int = 20, market: str = "All", source_type: str = "All", search: str = ""):
    return dataset.sources_page(page, page_size, market, source_type, search)

@app.get("/api/data/knowledge")
def data_knowledge(market: str = "All"):
    return dataset.knowledge(market)


@app.get("/api/data/status")
def data_status():
    return {"database_connected": db_enabled(), "data_source": "database" if dataset.live else "demo", "pgvector_enabled": db_enabled()}

@app.patch("/api/data/evidence/{evidence_id}")
def update_evidence(evidence_id: str, validation: str, claim: str | None = None):
    if validation not in {"pass", "review"}:
        raise HTTPException(status_code=400, detail="validation must be pass or review")
    row = dataset.update_evidence(evidence_id, validation, claim)
    if not row:
        raise HTTPException(status_code=404, detail="Evidence record not found")
    return row

@app.post("/api/data/semantic-search")
def semantic_search(query_embedding: list[float], threshold: float = 0.70, limit: int = 10):
    if not db_enabled():
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    expected = int(__import__('os').getenv("EMBEDDING_DIM", "1536"))
    if len(query_embedding) != expected:
        raise HTTPException(status_code=400, detail=f"Expected an embedding with {expected} dimensions")
    with session() as c:
        rows = c.execute(text("select * from match_evidence(cast(:embedding as vector), :threshold, :limit)"), {"embedding": "[" + ",".join(map(str, query_embedding)) + "]", "threshold": threshold, "limit": min(50, max(1, limit))}).mappings().all()
    return {"items": [dict(r) for r in rows], "count": len(rows)}


@app.get("/api/providers/status")
def providers_status():
    status=search_provider_status()
    return {"providers":status,"recommended_mode":"live" if any(status[k] for k in ("firecrawl","tavily","serper")) else "knowledge_base","ai_available":any(status[k] for k in ("gemini","openrouter","groq","openai"))}
