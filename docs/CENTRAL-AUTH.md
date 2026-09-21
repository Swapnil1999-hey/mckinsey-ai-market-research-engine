# Centralized Account & Owner Administration

The application no longer stores account records in browser localStorage. Accounts are stored in PostgreSQL/Supabase in `app_users`; sessions are stored in `app_sessions`.

## Roles
- `owner`: full user administration. The bootstrap owner is **Swapnil Sudhakar Pathare**.
- `researcher`: normal workspace user.

## New-account flow
1. User creates an account.
2. The record is stored with `status = pending`.
3. The owner opens **User Management**.
4. Owner selects **Approve**.
5. User can sign in from any device using the same User ID/password.

## Delete flow
Owner selects **Delete**. The account is removed and its owned research requests are removed through the database cascade, along with related sources, evidence, reports, feedback, and sessions.

## Owner bootstrap environment variables
Set these in the backend environment (local `.env` or the production host):

```env
OWNER_USER_ID=swapnil.sudhakar.pathare
OWNER_NAME=Swapnil Sudhakar Pathare
OWNER_EMAIL=your-real-owner-email@example.com
OWNER_PASSWORD=use-a-strong-private-password
```

Never commit `.env` or real passwords/API keys.
