# Environment Setup

Use environment variables for Gemini, Firecrawl, database, and vector-memory credentials. Deploy frontend to Vercel/Netlify and backend to Render/Railway.

## Gemini resilience settings

The backend supports automatic retry and model fallback for transient Gemini failures. Configure these in the project-root `.env` or `backend/.env`:

```env
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash
GEMINI_MAX_RETRIES=4
GEMINI_RETRY_BASE_SECONDS=2
GEMINI_TIMEOUT_SECONDS=120
```

The backend loads the project-root `.env` and then `backend/.env`; when both exist, `backend/.env` takes precedence.


### Provider failover
Firecrawl and Gemini are optional rather than single points of failure. Configure one or more of:
- `TAVILY_API_KEY` or `SERPER_API_KEY` for alternative web search.
- `OPENROUTER_API_KEY`, `GROQ_API_KEY`, or `OPENAI_API_KEY` for alternative LLM generation.
The backend automatically detects failures/quota exhaustion and falls back. Never expose these keys through `NEXT_PUBLIC_*`.
