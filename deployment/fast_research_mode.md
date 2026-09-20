# Fast Research Mode

The research workflow is optimized for faster end-to-end report generation while keeping live Firecrawl research, Gemini retry/fallback, Supabase/PostgreSQL, pgvector, evidence review, exhibits, and reports.

## What changed
- Firecrawl searches run concurrently instead of sequentially.
- Fast mode limits search results and total sources to reduce latency and model context size.
- Web content sent to Gemini is capped per source.
- Extraction and report generation use compact evidence payloads.
- Gemini retries are bounded to reduce long waits during transient failures.
- Firecrawl request timeout is bounded.
- AI evidence dates are normalized before PostgreSQL DATE insertion.

## Recommended backend settings
```env
FAST_RESEARCH_MODE=true
FIRECRAWL_LIMIT=3
FIRECRAWL_TIMEOUT_SECONDS=35
MAX_RESEARCH_SOURCES=9
MAX_SOURCE_CHARS=4000
MAX_EVIDENCE_RECORDS=30
GEMINI_MAX_RETRIES=2
GEMINI_RETRY_BASE_SECONDS=1
GEMINI_TIMEOUT_SECONDS=60
```

Set `FAST_RESEARCH_MODE=false` and increase the limits when deeper research is preferred over response speed.
