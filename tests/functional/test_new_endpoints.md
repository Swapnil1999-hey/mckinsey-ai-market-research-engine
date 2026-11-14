# New Endpoint Test Contracts

> These contracts document the expected request/response behaviour for the two
> smart-query endpoints added to the McKinsey AI Market Research & Strategy
> Engine backend (`backend/api/main.py`).  They are written as a living
> specification; use them to drive manual smoke-testing or automated integration
> tests (e.g. with `httpx`, `requests`, or Postman).

---

## GET /api/classify

Classifies a free-text query as market-research **relevant** or **irrelevant**
before any expensive pipeline work is started.

### Test 1: Weather query

| Field | Value |
|---|---|
| **Request** | `GET /api/classify?query=what%20is%20the%20weather%20today` |
| **Expected status** | `200 OK` |
| **Expected body** | `{ "verdict": "irrelevant", "category": "weather", "preview": { "is_irrelevant": true, "answer": "...", "redirect": "..." } }` |

**Assertions:**
- `verdict == "irrelevant"`
- `preview.is_irrelevant == true`
- `preview.category == "weather"`
- `preview.answer` is a non-empty string
- `preview.redirect` length > 10 characters

---

### Test 2: Market research query

| Field | Value |
|---|---|
| **Request** | `GET /api/classify?query=competitor%20analysis%20fintech%20India` |
| **Expected status** | `200 OK` |
| **Expected body** | `{ "verdict": "relevant", "category": "" }` |

**Assertions:**
- `verdict == "relevant"`
- `category == ""`
- Response body does **not** contain a `preview` key

---

### Test 3: Empty query

| Field | Value |
|---|---|
| **Request** | `GET /api/classify?query=` |
| **Expected status** | `400 Bad Request` |
| **Expected body** | `{ "detail": "query parameter is required" }` |

**Assertions:**
- HTTP status code is `400`
- `detail` field equals `"query parameter is required"`

---

### Test 4: Date query

| Field | Value |
|---|---|
| **Request** | `GET /api/classify?query=what%20is%20today%20date` |
| **Expected status** | `200 OK` |

**Assertions:**
- `verdict == "irrelevant"`
- `category == "date_time"`
- `preview.is_irrelevant == true`

---

## POST /api/ask

Universal smart endpoint: short-circuits with a helpful answer for irrelevant
questions; runs the full 8-stage research pipeline for valid market-research
queries.

### Test 5: Irrelevant question short-circuit

| Field | Value |
|---|---|
| **Request** | `POST /api/ask` |
| **Body** | `{ "query": "what is the weather today" }` |
| **Content-Type** | `application/json` |
| **Expected status** | `200 OK` |
| **Expected body** | `{ "is_irrelevant": true, "category": "weather", "answer": "...", "redirect": "..." }` |

**Assertions:**
- HTTP status is `200`
- `is_irrelevant == true`
- `category == "weather"`
- `answer` is non-empty string
- `redirect` length > 10 characters
- Response body does **not** contain a `result` key (pipeline was **not** run)

---

### Test 6: Valid research question

| Field | Value |
|---|---|
| **Request** | `POST /api/ask` |
| **Body** | `{ "query": "EV market growth in India 2025" }` |
| **Content-Type** | `application/json` |
| **Expected status** | `200 OK` |
| **Expected body** | `{ "is_irrelevant": false, "category": "market_research", "result": { ... } }` |

**Assertions:**
- HTTP status is `200`
- `is_irrelevant == false`
- `category == "market_research"` (or equivalent non-empty string)
- `result` key is present and is an object
- Response body does **not** have `answer` / `redirect` at top level

---

### Test 7: Min-length validation

| Field | Value |
|---|---|
| **Request** | `POST /api/ask` |
| **Body** | `{ "query": "" }` |
| **Content-Type** | `application/json` |
| **Expected status** | `422 Unprocessable Entity` |

**Assertions:**
- HTTP status is `422`
- Response body contains a `detail` array with at least one validation error
  describing the `query` field

---

## Rate-limit behaviour (GET & POST)

After more than **10 requests within 60 seconds** from the same IP:

| Field | Value |
|---|---|
| **Expected status** | `429 Too Many Requests` |
| **Expected body** | `{ "detail": "Rate limit exceeded: max 10 requests per 60s. Please wait before submitting another query." }` |

**Assertions:**
- 11th request within the window returns HTTP `429`
- After the 60-second window resets, requests succeed again

---

*Last updated: 2026-11-14 — covers endpoints `/api/classify` (GET) and `/api/ask` (POST).*
