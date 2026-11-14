# API Documentation — McKinsey AI Market Research & Strategy Engine
Version: 1.3.0 | Base URL: configured via NEXT_PUBLIC_API_URL

## Health & Status
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | /health | None | Backend health, DB status, data source |
| GET | /api/providers/status | None | Provider availability (Firecrawl/Tavily/Serper/Gemini) |

## Smart Query Interface (New in v1.3)
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | /api/classify | None | Classify a query as relevant or irrelevant. Query param: query (string). Returns verdict, category, reason, preview (if irrelevant) |
| POST | /api/ask | None | Universal endpoint. Irrelevant questions get a helpful answer. Market research questions run the full pipeline. Body: { query: string } |

### /api/classify Response Examples
Irrelevant query (weather):
```json
{ "verdict": "irrelevant", "category": "weather", "reason": "...", "preview": { "is_irrelevant": true, "category": "weather", "answer": "...", "redirect": "..." } }
```

Relevant query:
```json
{ "verdict": "relevant", "category": "", "reason": "Contains market-research keyword: 'competitor'" }
```

### Irrelevant Categories Handled
weather · date_time · sports · entertainment · personal_advice · cooking_recipes · crypto_stock_trading · travel_booking · health_medical · general_knowledge

## Authentication
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | /api/auth/register | None | Create account. Body: { user_id, full_name, email, password } |
| POST | /api/auth/login | None | Login. Body: { user_id, password }. Returns { token, user } |
| GET | /api/auth/me | Bearer | Current session user |
| POST | /api/auth/logout | Bearer | Invalidate session |
| PATCH | /api/auth/profile | Bearer | Update full_name and email |

## Owner / Administration
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | /api/admin/users | Owner | List all users |
| POST | /api/admin/users/{user_id}/suspend | Owner | Suspend user |
| POST | /api/admin/users/{user_id}/reactivate | Owner | Reactivate user |
| DELETE | /api/admin/users/{user_id} | Owner | Delete user |
| POST | /api/admin/users/{user_id}/sessions/revoke | Owner | Revoke all sessions |

## Research Workflow
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | /api/research-jobs | None | Create a research job. Body: ResearchRequest |
| POST | /api/research-run | None | Create + run full 8-stage pipeline. Returns completed job |
| POST | /api/research-plan | None | Run planning stage. Query param: job_id |
| POST | /api/browse | None | Run browsing stage |
| POST | /api/extract-evidence | None | Extract evidence from sources |
| POST | /api/validate-evidence | None | Validate extracted evidence |
| POST | /api/aggregate | None | Aggregate findings |
| POST | /api/generate-report | None | Generate strategy report |
| POST | /api/review | None | Move job to review state |
| GET | /api/reports/{job_id} | None | Retrieve research job + report |
| POST | /api/feedback | None | Save human review feedback |

### ResearchRequest Body
```json
{ "query": "string (required, min 5)", "market": "string", "geography": "string", "timeframe": "string", "competitors": ["string"], "output_format": "string", "report_depth": "standard|detailed|deep dive" }
```

## Data & Knowledge
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | /api/data/overview | None | Dashboard metrics. Params: market, geography |
| GET | /api/data/filters | None | Available filter values |
| GET | /api/data/evidence | None | Paginated evidence. Params: page, page_size, market, topic, validation, search |
| GET | /api/data/sources | None | Paginated sources |
| GET | /api/data/knowledge | None | Knowledge base. Param: market |
| GET | /api/data/status | None | Database connection status |
| PATCH | /api/data/evidence/{evidence_id} | None | Update evidence validation/claim |
| POST | /api/data/semantic-search | None | Vector similarity search. Body: { query_embedding: float[], threshold: float, limit: int } |
