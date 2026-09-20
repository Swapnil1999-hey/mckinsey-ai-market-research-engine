import json
import os
import random
import time
from typing import Any

import requests


class ProviderError(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        value = int(_env(name, str(default)))
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float | None = None) -> float:
    try:
        value = float(_env(name, str(default)))
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


def firecrawl_search(query: str, limit: int = 5, country: str = "IN", location: str = "India") -> list[dict[str, Any]]:
    """Search Firecrawl with a few compatibility fallbacks.

    Firecrawl's search API can return an empty result set even when the request
    itself succeeds. We first use the current v2 web search shape, then retry
    with a simpler web-only request, and finally try news. This prevents an
    empty optional source category from making the whole research job fail.
    """
    key = _env("FIRECRAWL_API_KEY")
    if not key:
        raise ProviderError("FIRECRAWL_API_KEY is not configured")

    base = _env("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v2").rstrip("/")
    # Keep queries focused; very long consultant prompts are poor search queries.
    clean_query = " ".join((query or "").split())[:350]
    if not clean_query:
        raise ProviderError("Firecrawl search query is empty")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    attempts = [
        {
            "query": clean_query,
            "limit": max(1, min(limit, 20)),
            "sources": ["web"],
            "country": country,
            "location": location,
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        },
        {
            "query": clean_query,
            "limit": max(1, min(limit, 20)),
            "sources": ["web"],
            "country": country,
            "location": location,
        },
        {
            "query": clean_query,
            "limit": max(1, min(limit, 20)),
            "sources": ["news"],
            "country": country,
            "location": location,
        },
    ]

    errors: list[str] = []
    for payload in attempts:
        try:
            r = requests.post(f"{base}/search", headers=headers, json=payload, timeout=_env_float("FIRECRAWL_TIMEOUT_SECONDS", 35.0, minimum=5.0, maximum=90.0))
        except requests.RequestException as exc:
            errors.append(str(exc))
            continue

        if not r.ok:
            errors.append(f"HTTP {r.status_code}: {r.text[:300]}")
            # Credit/quota failures will not be fixed by trying the same API again.
            if r.status_code in {401,402,403,429} and any(x in r.text.lower() for x in ("credit","quota","limit","exhausted","payment")):
                break
            continue

        try:
            body = r.json()
        except ValueError:
            errors.append("Firecrawl returned non-JSON response")
            continue

        if body.get("success") is False:
            errors.append(str(body.get("error") or body.get("code") or "unknown Firecrawl error"))
            continue

        data = body.get("data") or {}
        results: list[dict[str, Any]] = []
        for group in ("web", "news"):
            items = data.get(group) or []
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url") or item.get("metadata", {}).get("url") or item.get("metadata", {}).get("sourceURL")
                if not url:
                    continue
                results.append({
                    "url": url,
                    "title": item.get("title") or item.get("metadata", {}).get("title") or "Untitled",
                    "description": item.get("description") or item.get("snippet") or item.get("metadata", {}).get("description") or "",
                    "markdown": item.get("markdown") or "",
                    "type": group,
                    "date": item.get("date"),
                })

        if results:
            return results

    detail = "; ".join(errors[-3:])
    if detail:
        print(f"Firecrawl search returned no usable sources. Attempts: {detail}")
    return []

def _is_retryable_gemini_status(status_code: int) -> bool:
    """Gemini documents 408, 429 and 5xx as transient errors worth retrying."""
    return status_code in {408, 429} or 500 <= status_code <= 599


def _backoff_seconds(retry_number: int, base_seconds: float, max_seconds: float = 30.0) -> float:
    """Exponential backoff with jitter: base*2^retry_number, capped, plus small jitter."""
    exponential = min(max_seconds, base_seconds * (2 ** retry_number))
    jitter = random.uniform(0, min(1.0, exponential * 0.25))
    return min(max_seconds, exponential + jitter)


def _gemini_request(
    model: str,
    key: str,
    prompt: str,
    schema: dict[str, Any],
    max_retries: int,
    retry_base_seconds: float,
    timeout_seconds: float,
) -> tuple[dict[str, Any] | None, int | None, str | None]:
    """
    Make one Gemini request with bounded retries.

    Returns (parsed_json, status_code, error_text). A successful request returns
    the parsed JSON and (None, None) for the error fields. A retryable HTTP error
    is retried with exponential backoff. Non-retryable HTTP errors return immediately.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.2,
        },
    }
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    last_status: int | None = None
    last_text: str | None = None

    for retry_number in range(max_retries + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            # Network/connection errors are transient in the same way as 5xx.
            last_status = None
            last_text = str(exc)
            if retry_number >= max_retries:
                return None, None, last_text
            delay = _backoff_seconds(retry_number, retry_base_seconds)
            print(f"Gemini model {model}: network error; retrying in {delay:.1f}s ({retry_number + 1}/{max_retries})")
            time.sleep(delay)
            continue

        if response.ok:
            try:
                body = response.json()
                text = body["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text), None, None
            except Exception as exc:
                return None, response.status_code, f"Gemini returned an unexpected response: {exc}"

        last_status = response.status_code
        last_text = response.text[:1000]

        # Quota exhaustion (429 RESOURCE_EXHAUSTED) is not fixed by retrying.
        # Return immediately so the workflow can use its local evidence fallback
        # instead of wasting time on sleep/retry cycles.
        if response.status_code == 429 and (
            "quota" in response.text.lower()
            or "resource_exhausted" in response.text.lower()
            or "generate_content_free_tier_requests" in response.text.lower()
        ):
            return None, last_status, last_text

        if not _is_retryable_gemini_status(response.status_code):
            return None, last_status, last_text

        if retry_number >= max_retries:
            return None, last_status, last_text

        delay = _backoff_seconds(retry_number, retry_base_seconds)
        print(
            f"Gemini model {model}: HTTP {response.status_code}; "
            f"retrying in {delay:.1f}s ({retry_number + 1}/{max_retries})"
        )
        time.sleep(delay)

    return None, last_status, last_text


def gemini_json(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """
    Generate structured JSON with automatic Gemini resilience.

    Primary model is GEMINI_MODEL. Transient errors (408/429/5xx and network
    failures) receive bounded exponential-backoff retries with jitter. If the
    primary model still fails, GEMINI_FALLBACK_MODEL is attempted. A fallback is
    also attempted for a primary 404/model-not-found response, which is useful
    when a configured model has been retired or is unavailable to the project.
    """
    key = _env("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY is not configured")

    primary_model = _env("GEMINI_MODEL", "gemini-3.6-flash")
    fallback_model = _env("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")
    max_retries = _env_int("GEMINI_MAX_RETRIES", 2, minimum=0, maximum=8)
    retry_base_seconds = _env_float("GEMINI_RETRY_BASE_SECONDS", 1.0, minimum=0.0, maximum=30.0)
    timeout_seconds = _env_float("GEMINI_TIMEOUT_SECONDS", 60.0, minimum=5.0, maximum=300.0)

    models = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models.append(fallback_model)

    failures: list[str] = []
    for index, model in enumerate(models):
        result, status_code, error_text = _gemini_request(
            model=model,
            key=key,
            prompt=prompt,
            schema=schema,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
            timeout_seconds=timeout_seconds,
        )
        if result is not None:
            if index > 0:
                print(f"Gemini fallback succeeded using model {model}")
            return result

        status_label = str(status_code) if status_code is not None else "network"
        failures.append(f"{model} ({status_label}): {(error_text or 'unknown error')[:500]}")

        # The next model is the configured fallback. Continue after any primary
        # failure so a retired/unavailable primary can fail over cleanly.
        if index == 0 and len(models) > 1:
            print(f"Gemini primary model {model} unavailable; trying fallback {fallback_model}")

    raise ProviderError("Gemini request failed after retries/fallback: " + " | ".join(failures))



def _provider_key(name: str) -> str:
    return _env(name)


def _normalize_search_items(items, provider: str):
    out=[]
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url=item.get('url') or item.get('link')
        if not url:
            continue
        out.append({
            'url': url,
            'title': item.get('title') or 'Untitled',
            'description': item.get('description') or item.get('snippet') or '',
            'markdown': item.get('markdown') or item.get('content') or item.get('raw_content') or '',
            'type': item.get('type') or 'web',
            'date': item.get('date') or item.get('published_date'),
            'provider': provider,
        })
    return out


def tavily_search(query: str, limit: int = 5, country: str = 'IN', location: str = 'India') -> list[dict[str, Any]]:
    key=_provider_key('TAVILY_API_KEY')
    if not key:
        return []
    payload={
        'api_key': key, 'query': ' '.join((query or '').split())[:350],
        'search_depth': _env('TAVILY_SEARCH_DEPTH','basic'),
        'max_results': max(1,min(limit,10)), 'include_answer': False,
        'include_raw_content': True,
    }
    try:
        r=requests.post('https://api.tavily.com/search',json=payload,timeout=_env_float('TAVILY_TIMEOUT_SECONDS',25,5,60))
        if not r.ok:
            print(f'Tavily unavailable: HTTP {r.status_code}: {r.text[:250]}')
            return []
        body=r.json()
        return _normalize_search_items(body.get('results'), 'tavily')
    except Exception as exc:
        print(f'Tavily unavailable: {exc}')
        return []


def serper_search(query: str, limit: int = 5, country: str = 'IN', location: str = 'India') -> list[dict[str, Any]]:
    key=_provider_key('SERPER_API_KEY')
    if not key:
        return []
    payload={'q':' '.join((query or '').split())[:350], 'num':max(1,min(limit,10)), 'gl':country.lower() if country else 'in', 'hl':'en'}
    headers={'X-API-KEY':key,'Content-Type':'application/json'}
    try:
        r=requests.post('https://google.serper.dev/search',headers=headers,json=payload,timeout=_env_float('SERPER_TIMEOUT_SECONDS',25,5,60))
        if not r.ok:
            print(f'Serper unavailable: HTTP {r.status_code}: {r.text[:250]}')
            return []
        body=r.json()
        items=[]
        for item in (body.get('organic') or [])[:limit]:
            items.append({'url':item.get('link'),'title':item.get('title'),'snippet':item.get('snippet'),'type':'web'})
        for item in (body.get('news') or [])[:max(0,limit-len(items))]:
            items.append({'url':item.get('link'),'title':item.get('title'),'snippet':item.get('snippet'),'type':'news','date':item.get('date')})
        return _normalize_search_items(items, 'serper')
    except Exception as exc:
        print(f'Serper unavailable: {exc}')
        return []


def search_provider_status() -> dict[str, bool]:
    return {
        'firecrawl': bool(_env('FIRECRAWL_API_KEY')),
        'tavily': bool(_env('TAVILY_API_KEY')),
        'serper': bool(_env('SERPER_API_KEY')),
        'gemini': bool(_env('GEMINI_API_KEY')),
        'openrouter': bool(_env('OPENROUTER_API_KEY')),
        'groq': bool(_env('GROQ_API_KEY')),
        'openai': bool(_env('OPENAI_API_KEY')),
    }


def research_search(query: str, limit: int = 5, country: str = 'IN', location: str = 'India') -> tuple[list[dict[str, Any]], str]:
    """Provider router. Tries Firecrawl first, then optional alternatives."""
    if _env('FIRECRAWL_API_KEY'):
        items=firecrawl_search(query,limit,country,location)
        if items:
            return items,'firecrawl'
    for name,fn in (('tavily',tavily_search),('serper',serper_search)):
        if _env({'tavily':'TAVILY_API_KEY','serper':'SERPER_API_KEY'}[name]):
            items=fn(query,limit,country,location)
            if items:
                return items,name
    return [], 'knowledge_base'


def _openai_compatible_json(base_url: str, api_key: str, model: str, prompt: str, timeout: float) -> dict[str, Any]:
    url=base_url.rstrip('/')+'/chat/completions'
    payload={
        'model':model,
        'messages':[{'role':'system','content':'Return valid JSON only. Follow the requested JSON structure exactly and do not invent evidence.'},{'role':'user','content':prompt}],
        'temperature':0.2,
        'response_format':{'type':'json_object'},
    }
    r=requests.post(url,headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'},json=payload,timeout=timeout)
    if not r.ok:
        raise ProviderError(f'Alternative LLM HTTP {r.status_code}: {r.text[:500]}')
    body=r.json(); content=body['choices'][0]['message']['content']
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderError(f'Alternative LLM returned invalid JSON: {exc}')


def alternative_llm_json(prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Try optional OpenRouter, Groq, then OpenAI after Gemini is unavailable."""
    schema_hint=json.dumps(schema, ensure_ascii=False)
    full_prompt=prompt+"\n\nJSON schema to follow:\n"+schema_hint
    timeout=_env_float('ALT_LLM_TIMEOUT_SECONDS',60,5,180)
    if _env('OPENROUTER_API_KEY'):
        model=_env('OPENROUTER_MODEL','openai/gpt-4o-mini')
        return _openai_compatible_json('https://openrouter.ai/api/v1',_env('OPENROUTER_API_KEY'),model,full_prompt,timeout),'openrouter'
    if _env('GROQ_API_KEY'):
        model=_env('GROQ_MODEL','llama-3.3-70b-versatile')
        return _openai_compatible_json('https://api.groq.com/openai/v1',_env('GROQ_API_KEY'),model,full_prompt,timeout),'groq'
    if _env('OPENAI_API_KEY'):
        model=_env('OPENAI_MODEL','gpt-4o-mini')
        return _openai_compatible_json('https://api.openai.com/v1',_env('OPENAI_API_KEY'),model,full_prompt,timeout),'openai'
    raise ProviderError('No alternative LLM provider is configured')


def ai_json_with_fallback(prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Gemini first; alternative LLMs second."""
    try:
        return gemini_json(prompt,schema),'gemini'
    except ProviderError as gemini_exc:
        print(f'Gemini unavailable; trying alternative LLM: {gemini_exc}')
        try:
            return alternative_llm_json(prompt,schema)
        except ProviderError as alt_exc:
            raise ProviderError(f'All AI providers unavailable. Gemini: {gemini_exc}; alternatives: {alt_exc}')


def live_configured() -> bool:
    # Live mode can operate with web search alone and use local evidence synthesis
    # when every LLM is unavailable.
    return bool(_env("FIRECRAWL_API_KEY") or _env("TAVILY_API_KEY") or _env("SERPER_API_KEY"))
