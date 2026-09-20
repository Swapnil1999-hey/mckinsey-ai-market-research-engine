from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="AI Market Research & Strategy Engine", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = ResearchService()
dataset = DatasetStore()


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
