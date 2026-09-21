# Production deployment — McKinsey AI Market Research & Strategy Engine

## Architecture
- Frontend: Vercel (Next.js)
- Backend: Render (FastAPI)
- Database: Supabase PostgreSQL + pgvector
- Web/AI providers: configured as backend-only environment variables

## 1. Supabase
1. Create a Supabase project.
2. Run `deployment/supabase/schema.sql` in SQL Editor.
3. Copy the Postgres connection string from Supabase Database settings. Prefer the pooler connection for hosted deployments when appropriate.
4. Keep the connection string private.

## 2. Render
Create a Web Service from this repository. The included `render.yaml` uses `backend` as the root directory and starts:

`uvicorn api.main:app --host 0.0.0.0 --port $PORT`

Set these secrets/environment variables in Render:
- DATABASE_URL
- OWNER_USER_ID
- OWNER_NAME
- OWNER_EMAIL
- OWNER_PASSWORD
- CORS_ORIGINS (set after Vercel deployment, e.g. https://your-app.vercel.app)
- GEMINI_API_KEY
- TAVILY_API_KEY
- SERPER_API_KEY
- GROQ_API_KEY
- FIRECRAWL_API_KEY

Never commit real credentials.

After deployment, verify:
`https://YOUR-RENDER-HOST/health`

Expected shape includes `status: ok` and database connectivity.

## 3. Vercel
Import the repository into Vercel and set **Root Directory** to `frontend`.
Set:

`NEXT_PUBLIC_API_URL=https://YOUR-RENDER-HOST`

Deploy.

## 4. Finish CORS
Copy the final Vercel URL into Render's `CORS_ORIGINS` variable. You can include multiple comma-separated origins if you have a custom domain and Vercel preview domain.

## 5. Owner account
The backend creates/maintains the owner from:
- OWNER_USER_ID
- OWNER_NAME
- OWNER_EMAIL
- OWNER_PASSWORD

The owner is not deletable through the owner UI. New researcher accounts remain pending until approved by the owner.

## 6. Production checks
- Create account on Device A.
- Approve it from the owner account.
- Sign in from Device B.
- Verify the account is centrally stored in Supabase.
- Verify the owner can approve/delete non-owner accounts.
- Verify research endpoints require authentication.
- Verify no API key is present in frontend source or browser network responses.
