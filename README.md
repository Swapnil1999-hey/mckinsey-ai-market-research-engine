# AI Market Research & Strategy Engine

A governed research-to-brief prototype built from the supplied product dossier and reference interface.

## Product flow
Query → Planner Agent → Web Browsing Agents → Data Extraction → Validation → Aggregation + Memory → Report Generation → Human Review.

The interface includes the required product surfaces: Research Intake Console, Research Plan, Agent Workflow Monitor, Evidence Review Panel, Strategy Brief Builder, Knowledge & Memory Workspace, and Operations & Quality Dashboard.

## Stack
- Frontend: Next.js, React, Tailwind CSS
- Backend/API: FastAPI
- Agent orchestration: LangGraph/LangChain/CrewAI-compatible service boundaries (the included demo workflow is deterministic and dependency-light)
- Browsing/scraping adapters: Firecrawl / Playwright / BeautifulSoup / Selenium interfaces
- LLM adapter: Gemini API-compatible service boundary
- Memory: Chroma / Qdrant / Supabase pgvector-compatible interface
- Operational data: PostgreSQL / Supabase-compatible schema
- Deployment notes: Vercel/Netlify + Render/Railway

## Run
### Frontend
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:3000.

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

The frontend defaults to `http://localhost:8000` for API calls.

## Environment
Copy `.env.example` to `.env`. Keep all model, scraping, database, and secret keys backend-only.

## Demo
1. Open New Research.
2. Enter a market-entry, competitor, or trend question.
3. Review the generated plan.
4. Start the research job.
5. Inspect workflow progress and evidence.
6. Generate the structured strategy brief.
7. Review/edit and log feedback.

## Repository structure
See the required dossier structure under `frontend/`, `backend/`, `ai/`, `data/`, `docs/`, `tests/`, and `deployment/`.

## Scope and safety
This release focuses on market research briefs, competitor scans, and trend summaries. It exposes source traceability, validation flags, conflicts, and human-review status. It does not present generated material as final client advice.


## Workflow fix
The prototype now has a one-click `POST /api/research-run` orchestration endpoint and an explicit `/api/aggregate` stage. The frontend submits the intake payload to the backend and renders stage status from the returned job instead of hard-coding Browsing as the last completed stage.

Run backend:
```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --port 8000
```

Run frontend in a second terminal:
```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.


## Live web research mode
The workflow now supports a real research mode when both `FIRECRAWL_API_KEY` and `GEMINI_API_KEY` are configured. Firecrawl v2 search is used for web/news discovery and page content; Gemini structured JSON output is used for evidence extraction and report generation. Firecrawl documents `POST /v2/search` with optional markdown scraping, and Gemini documents `generateContent` with JSON response schemas.

### Configure keys
1. Copy `.env.example` to `.env` in the project root (or create `backend/.env`), or set the variables in the shell used to launch FastAPI.
2. Add your Firecrawl key as `FIRECRAWL_API_KEY`.
3. Add your Google Gemini API key as `GEMINI_API_KEY`.
4. Restart FastAPI after changing `.env`.

Without those keys, the app deliberately stays in demo mode so the workflow remains testable; it does not pretend that demo records are live research.

## Gemini automatic retry + fallback
The live Gemini adapter now includes bounded resilience for transient API failures:
- Retries HTTP `408`, `429`, and `5xx` responses with exponential backoff and jitter.
- Retries network/connection errors with the same bounded strategy.
- After the primary model exhausts its retries, it automatically tries `GEMINI_FALLBACK_MODEL`.
- A primary `404` can also fail over, which helps when a configured model is unavailable to the project.
- The default primary/fallback are `gemini-3.6-flash` and `gemini-3.5-flash`.

Optional settings:
```env
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash
GEMINI_MAX_RETRIES=4
GEMINI_RETRY_BASE_SECONDS=2
GEMINI_TIMEOUT_SECONDS=120
```

For a faster local test, you can temporarily set `GEMINI_MAX_RETRIES=1` and `GEMINI_RETRY_BASE_SECONDS=0`.

## User Login, Account Profile & Appearance
The frontend now includes a login/create-account interface. New accounts save their User ID, name, email and role in browser localStorage for this prototype. After sign-in, the profile menu shows the saved user information and links to Profile and Settings. Settings supports editing name/email, signing out, and switching between Light and Dark workspace themes. Theme preference is persisted in browser localStorage.

> Production note: this is a local prototype authentication flow. For production deployment, replace localStorage credentials with backend authentication, password hashing, sessions/JWT, and a PostgreSQL/Supabase users table.

## Consultant-style report exhibits

The report workspace now follows the supplied Global Balance Sheet 2026 report structure: title/subtitle, At a glance, executive interpretation, findings, exhibits, implications, executive actions, limitations, and an evidence appendix. The report generator asks Gemini to create quantitative exhibits only from validated evidence. Supported exhibit types are line charts for time series, bar charts for category comparisons, and donut charts for part-to-whole composition. If the evidence does not contain enough quantitative support, the system returns no exhibit rather than inventing data. Reports can be printed to PDF from the browser.

## Supabase / PostgreSQL + pgvector

The app is database-first when `DATABASE_URL` is configured. Run `deployment/supabase/schema.sql` in Supabase SQL Editor, then from `backend` run `python -m services.seed_database` to import the bundled demo dataset. Set `DATA_SOURCE=database` to require the database, or leave `DATA_SOURCE=auto` for a safe CSV fallback. Dashboard, Evidence Review, Sources, Knowledge Base, report records, feedback, and review actions use the database when enabled.


## Provider failover (v4)
The research engine now detects exhausted/unavailable providers and routes automatically:
1. Firecrawl -> Tavily -> Serper for fresh web search.
2. Gemini -> OpenRouter -> Groq -> OpenAI for report/extraction AI.
3. If no web provider is available, the system queries the Supabase/CSV knowledge base instead of returning a generic demo answer.
4. `/api/providers/status` exposes provider availability for the dashboard.

Optional environment variables: `TAVILY_API_KEY`, `SERPER_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`. Keep all keys backend-only.

When all web credits are exhausted, the UI should identify the run as **Knowledge Base Research** rather than claiming it searched the live internet.
