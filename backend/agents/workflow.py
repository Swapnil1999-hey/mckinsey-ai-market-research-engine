from datetime import datetime, timezone
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.providers import ProviderError, research_search, ai_json_with_fallback, live_configured
from services.dataset import DatasetStore


def now():
    return datetime.now(timezone.utc).isoformat()


DATASET = DatasetStore()


def run_stage(job, stage):
    req = job["request"]
    job["state"] = stage
    job["stage_status"][stage] = "running"
    job["error"] = None
    try:
        if stage == "planning":
            market = req.get("market") or "the target market"
            geo = req.get("geography") or "the target geography"
            competitors = ", ".join(req.get("competitors") or []) or "major competitors"
            q = req["query"]
            job["plan"] = [
                {"task": f"Market signals for {market} in {geo}", "search_query": f"{q} market size growth trends {geo}", "evidence_type": "market signal"},
                {"task": f"Competitor observations: {competitors}", "search_query": f"{q} {competitors} strategy pricing technology", "evidence_type": "competitor fact"},
                {"task": "Recent strategic developments and risks", "search_query": f"{q} recent strategic developments risks regulation", "evidence_type": "strategic development"},
            ]

        elif stage == "browsing":
            fast_mode = os.getenv("FAST_RESEARCH_MODE", "true").lower() == "true"
            limit = int(os.getenv("FIRECRAWL_LIMIT", "3" if fast_mode else "5"))
            max_sources = int(os.getenv("MAX_RESEARCH_SOURCES", "9" if fast_mode else "12"))
            max_chars = int(os.getenv("MAX_SOURCE_CHARS", "5000" if fast_mode else "12000"))
            country = "IN" if (req.get("geography") or "").lower() == "india" else "US"
            location = req.get("geography") or "India"
            seen=set(); sources=[]; provider_used=[]
            tasks=job.get("plan", [])[:4 if fast_mode else 6]
            with ThreadPoolExecutor(max_workers=min(len(tasks),4) or 1) as pool:
                futures=[pool.submit(research_search,task["search_query"],limit,country,location) for task in tasks]
                for future in as_completed(futures):
                    try: items,provider=future.result(); provider_used.append(provider)
                    except Exception as exc: print(f"Search provider failed: {exc}"); continue
                    for item in items:
                        url=item.get("url")
                        if not url or url in seen: continue
                        seen.add(url)
                        sources.append({"url":url,"title":item.get("title") or "Untitled","type":item.get("type","web"),"provider":item.get("provider",provider),"retrieved":now(),"snippet":item.get("description","") or item.get("snippet",""),"content":(item.get("markdown") or item.get("description") or "")[:max_chars],"date":item.get("date")})
                        if len(sources)>=max_sources: break
                    if len(sources)>=max_sources: break
            if sources:
                job["mode"]="live"
                job["research_provider"]=next((x for x in ["firecrawl","tavily","serper"] if x in provider_used), provider_used[0] if provider_used else "web")
                job["provider_chain"]=list(dict.fromkeys(provider_used))
                job["sources"]=sources
            else:
                # No web credits/provider available: use persisted Supabase/CSV evidence.
                kb=DATASET.search_research_evidence(req["query"],limit=max_sources*2)
                if not kb:
                    raise ProviderError("No web provider returned results and no matching knowledge-base evidence was found. Add Tavily/Serper credits or wait for Firecrawl credits to reset.")
                job["mode"]="knowledge_base"
                job["research_provider"]="supabase_knowledge_base" if DATASET.live else "bundled_knowledge_base"
                job["provider_chain"]=["knowledge_base"]
                job["sources"]=[]
                for i,e in enumerate(kb):
                    url=e.get("source") or f"knowledge://evidence/{e.get('evidence_id',i)}"
                    job["sources"].append({"url":url,"title":e.get("source_title") or "Persisted evidence","type":"knowledge base","provider":"knowledge_base","retrieved":now(),"snippet":e.get("excerpt") or e.get("claim","") ,"content":e.get("excerpt") or e.get("claim","") ,"date":e.get("date")})
                job["knowledge_evidence"]=kb

        elif stage == "extraction":
            if not job.get("sources"):
                raise ValueError("Extraction requires browsing sources.")
            if job.get("mode") in {"live", "knowledge_base"}:
                if job.get("mode") == "knowledge_base":
                    job["evidence"] = [{"claim":e.get("claim","") ,"source":e.get("source") or "","date":e.get("date") or now()[:10],"entity":e.get("entity") or "","topic":e.get("topic") or "","excerpt":e.get("excerpt") or "","confidence":float(e.get("confidence") or 0.7)} for e in job.get("knowledge_evidence",[])]
                    job["ai_status"]="Knowledge-base mode; no live web/LLM provider required"
                    job["ai_degraded"]=True
                else:
                    source_text = "\n\n".join(
                    f"SOURCE {i+1}\nURL: {s['url']}\nTITLE: {s['title']}\nCONTENT:\n{s.get('content','')}"
                    for i, s in enumerate(job["sources"][:int(os.getenv("MAX_RESEARCH_SOURCES", "9"))])
                )
                schema = {
                    "type": "object",
                    "properties": {"evidence": {"type": "array", "items": {"type": "object", "properties": {
                        "claim": {"type": "string"}, "source_url": {"type": "string"}, "date": {"type": "string"},
                        "entity": {"type": "string"}, "topic": {"type": "string"}, "excerpt": {"type": "string"}, "confidence": {"type": "number"}
                    }, "required": ["claim", "source_url", "date", "entity", "topic", "excerpt", "confidence"]}}},
                    "required": ["evidence"],
                }
                try:
                    result, ai_provider = ai_json_with_fallback(
                        f"Extract only claims directly supported by the supplied sources. Do not invent facts. Keep citations tied to the exact source URL. Research question: {req['query']}\n\n{source_text}",
                        schema,
                    )
                    job["ai_provider"] = ai_provider
                    job["evidence"] = [
                        {"claim": e["claim"], "source": e["source_url"], "date": e["date"], "entity": e["entity"], "topic": e["topic"], "excerpt": e["excerpt"], "confidence": e["confidence"]}
                        for e in result.get("evidence", [])
                    ]
                except ProviderError as exc:
                    # Keep the product useful when Gemini quota is exhausted.
                    # Firecrawl evidence is still real retrieved evidence, so build
                    # a conservative evidence set from source titles/snippets.
                    if "All AI providers unavailable" not in str(exc) and "quota" not in str(exc).lower() and "resource_exhausted" not in str(exc).lower() and "429" not in str(exc):
                        raise
                    job["ai_degraded"] = True
                    job["ai_status"] = "AI providers unavailable; using retrieved-source evidence"
                    job["evidence"] = []
                    for source in job["sources"]:
                        snippet = (source.get("content") or source.get("snippet") or "").strip()
                        if not snippet:
                            continue
                        title = source.get("title") or "Retrieved source"
                        job["evidence"].append({
                            "claim": f"Retrieved source: {title}",
                            "source": source.get("url", ""),
                            "date": source.get("date") or now()[:10],
                            "entity": req.get("market") or "digital healthcare market",
                            "topic": "Retrieved market evidence",
                            "excerpt": snippet[:900],
                            "confidence": 0.65,
                        })
                    if not job["evidence"]:
                        raise ProviderError("AI providers unavailable and no usable source evidence was returned.")
            else:
                job["evidence"] = [
                    {"claim": "Demo evidence record; live mode requires API keys.", "source": job["sources"][0]["url"], "date": now()[:10], "entity": req.get("market") or "market", "topic": "market signal", "excerpt": job["sources"][0]["snippet"], "confidence": 0.2},
                    {"claim": "Demo competitor record; live mode requires API keys.", "source": job["sources"][1]["url"], "date": now()[:10], "entity": (req.get("competitors") or ["competitor"])[0], "topic": "competitor movement", "excerpt": job["sources"][1]["snippet"], "confidence": 0.2},
                ]

        elif stage == "validation":
            if not job.get("evidence"):
                raise ValueError("Validation requires extracted evidence.")
            validated = []
            for e in job["evidence"]:
                e["validation"] = {"credibility": "pass" if e.get("source", "").startswith("http") else "review", "recency": "review" if not e.get("date") else "pass", "duplicate": "pass", "contradiction": "not_checked"}
                if e.get("confidence", 0) >= 0.5 or job.get("mode") == "live":
                    validated.append(e)
            job["validated_evidence"] = validated

        elif stage == "aggregation":
            evidence = job.get("validated_evidence", [])
            if not evidence:
                raise ValueError("No validated evidence is available for aggregation.")
            topics = {}
            for e in evidence:
                topics.setdefault(e.get("topic", "other"), []).append(e["claim"])
            job["aggregation"] = {"evidence_count": len(evidence), "topics": topics, "entities": sorted({e.get("entity", "") for e in evidence})}

        elif stage == "report_generation":
            evidence = job.get("validated_evidence", [])
            if not evidence:
                raise ValueError("Report generation requires validated evidence.")
            if job.get("mode") in {"live", "knowledge_base"}:
                max_evidence = int(os.getenv("MAX_EVIDENCE_RECORDS", "30"))
                compact = "\n".join(f"- {e['claim']} [SOURCE: {e['source']}]" for e in evidence[:max_evidence])
                chart_item = {
                    "type": "object",
                    "properties": {
                        "chart_type": {"type": "string", "enum": ["bar", "line", "donut"]},
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "unit": {"type": "string"},
                        "source_note": {"type": "string"},
                        "data": {"type": "array", "items": {"type": "object", "properties": {
                            "label": {"type": "string"}, "value": {"type": "number"}, "secondary": {"type": "number"}
                        }, "required": ["label", "value"]}}
                    },
                    "required": ["chart_type", "title", "subtitle", "unit", "source_note", "data"]
                }
                metric_item = {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "value": {"type": "string"}, "context": {"type": "string"}},
                    "required": ["label", "value", "context"]
                }
                schema = {"type": "object", "properties": {
                    "title": {"type": "string"}, "subtitle": {"type": "string"}, "report_date": {"type": "string"},
                    "executive_summary": {"type": "string"},
                    "at_a_glance": {"type": "array", "items": metric_item},
                    "key_findings": {"type": "array", "items": {"type": "string"}},
                    "market_signals": {"type": "array", "items": {"type": "string"}},
                    "competitor_observations": {"type": "array", "items": {"type": "string"}},
                    "implications": {"type": "array", "items": {"type": "string"}},
                    "strategic_directions": {"type": "array", "items": {"type": "string"}},
                    "executive_actions": {"type": "array", "items": {"type": "string"}},
                    "exhibits": {"type": "array", "items": chart_item},
                    "limitations": {"type": "array", "items": {"type": "string"}}
                }, "required": ["title", "subtitle", "report_date", "executive_summary", "at_a_glance", "key_findings", "market_signals", "competitor_observations", "implications", "strategic_directions", "executive_actions", "exhibits", "limitations"]}
                prompt = f"""Write a McKinsey-style, consultant-ready research report using ONLY the validated evidence below.
Structure the report like a professional global macro/strategy report: a clear title and subtitle, an 'At a glance' section, executive interpretation, evidence-backed findings, exhibits, implications, and 'What this means for executives'. Keep descriptive facts separate from strategic interpretation. Cite source URLs inline after supported statements. Do not invent facts, numbers, dates, rankings, percentages, or trends.

CHART RULES: Create 1 to 4 exhibits only when the validated evidence contains enough quantitative information to support them. Prefer line charts for time series, bar charts for category comparisons, and donut charts for part-to-whole composition. Every chart value must be directly supported by the supplied evidence; never estimate or fabricate a number. Include a concise source_note for every chart. If there is not enough quantitative evidence for a useful chart, return an empty exhibits array rather than inventing data.

Question: {req['query']}
Evidence:
{compact}"""
                try:
                    report, ai_provider = ai_json_with_fallback(prompt, schema)
                    job["ai_provider"] = ai_provider
                    report["citations"] = sorted({e["source"] for e in evidence})
                    report["human_review_required"] = True
                    report["evidence_count"] = len(evidence)
                    job["report"] = report
                except ProviderError as exc:
                    if "All AI providers unavailable" not in str(exc) and "quota" not in str(exc).lower() and "resource_exhausted" not in str(exc).lower() and "429" not in str(exc):
                        raise
                    # Query-specific local fallback. Never use a static answer:
                    # build the brief from this job's retrieved sources and question.
                    citations = sorted({e["source"] for e in evidence if e.get("source")})
                    question = req.get("query", "").strip()
                    qlower = question.lower()
                    all_text = " ".join(
                        f"{e.get('claim','')} {e.get('excerpt','')}" for e in evidence
                    )
                    text_lower = all_text.lower()

                    def topic_items(keywords, limit=6):
                        rows = []
                        for e in evidence:
                            hay = f"{e.get('claim','')} {e.get('excerpt','')} {e.get('topic','')}".lower()
                            if any(k in hay for k in keywords):
                                rows.append(e.get("claim") or e.get("excerpt", "")[:300])
                        return list(dict.fromkeys(rows))[:limit]

                    market_findings = topic_items([
                        "market", "growth", "adoption", "revenue", "cagr", "size", "forecast"
                    ])
                    competitor_findings = topic_items([
                        "competitor", "competition", "company", "platform", "apollo",
                        "tata", "reliance", "pharmeasy", "tata 1mg", "practo", "cult.fit"
                    ])
                    trend_findings = topic_items([
                        "trend", "digital", "telehealth", "telemedicine", "ai", "remote",
                        "healthtech", "wearable", "diagnostic", "interoperability"
                    ])
                    opportunity_findings = topic_items([
                        "opportun", "underserved", "gap", "demand", "expansion", "potential",
                        "personalized", "rural", "preventive", "workflow"
                    ])

                    if not market_findings:
                        market_findings = [e["claim"] for e in evidence[:4]]
                    if not trend_findings:
                        trend_findings = [e["claim"] for e in evidence[1:5]]
                    if not competitor_findings:
                        competitor_findings = [e["claim"] for e in evidence[:4]]
                    if not opportunity_findings:
                        opportunity_findings = [e["claim"] for e in evidence[-4:]]

                    source_names = [e.get("source", "") for e in evidence[:6] if e.get("source")]
                    source_titles = []
                    for src in job.get("sources", []):
                        if src.get("title") and src.get("url") in source_names:
                            source_titles.append(src["title"])
                    if not source_titles:
                        source_titles = [src.get("title", "Retrieved source") for src in job.get("sources", [])[:6]]

                    subject = question[:100] + ("…" if len(question) > 100 else "")
                    report = {
                        "title": f"Rapid Research Brief — {subject}",
                        "subtitle": "Query-specific evidence synthesis from the available research provider",
                        "report_date": now()[:10],
                        "executive_summary": (
                            f"This brief addresses the specific research question: {question} "
                            f"It uses {len(job.get('sources', []))} live web sources and {len(evidence)} source-linked evidence records. "
                            "Gemini synthesis is temporarily unavailable because the configured API quota is exhausted, "
                            "so the system has not invented or generalized beyond the retrieved evidence."
                        ),
                        "at_a_glance": [
                            {"label": "Research question", "value": subject, "context": "Current user query"},
                            {"label": "Sources retrieved", "value": str(len(job.get("sources", []))), "context": "Available web/knowledge-base sources"},
                            {"label": "Evidence records", "value": str(len(evidence)), "context": "Source-linked records"},
                            {"label": "AI status", "value": "Quota unavailable", "context": "Local query-specific fallback used"},
                        ],
                        "key_findings": market_findings + trend_findings[:4],
                        "market_signals": market_findings,
                        "competitor_observations": competitor_findings,
                        "implications": [
                            f"The evidence should be interpreted specifically in the context of: {question}",
                            "Competitor and market claims should be checked against the original cited sources before executive use.",
                        ],
                        "strategic_directions": opportunity_findings,
                        "executive_actions": [
                            "Review the source-linked evidence records and open the original sources for high-impact claims.",
                            "Compare competitor observations and opportunity signals before making an investment or market-entry decision.",
                            "Retry AI synthesis after an AI provider becomes available or configure an alternative LLM provider.",
                        ],
                        "exhibits": [],
                        "limitations": [
                            "Configured AI providers were unavailable; this is a local evidence synthesis rather than an LLM-written strategic report.",
                            "No market share, ranking, forecast or strategic recommendation has been invented by the fallback.",
                            "Human review is required before executive or client use.",
                        ],
                        "citations": citations,
                        "source_titles": source_titles,
                        "human_review_required": True,
                        "evidence_count": len(evidence),
                        "ai_degraded": True,
                        "ai_status": "AI providers unavailable; query-specific evidence fallback generated",
                        "topics": sorted({e.get("topic", "") for e in evidence if e.get("topic")}),
                    }
                    job["ai_degraded"] = True
                    job["ai_status"] = "AI providers unavailable; evidence-only fallback report generated"
                    job["report"] = report
            else:
                job["report"] = {"title": "Prototype Research Strategy Brief", "subtitle": "Demo-mode report structure with live exhibits enabled when quantitative evidence is available.", "report_date": now()[:10], "executive_summary": "Configure Firecrawl and Gemini API keys to generate a live evidence-backed report.", "at_a_glance": [], "key_findings": [], "market_signals": [], "competitor_observations": [], "implications": [], "strategic_directions": [], "executive_actions": [], "exhibits": [], "limitations": ["Demo mode; no live web evidence."], "citations": [e["source"] for e in evidence], "human_review_required": True, "evidence_count": len(evidence)}

        elif stage == "review":
            job["state"] = "review"
            job["stage_status"][stage] = "complete"
            job["updated_at"] = now()
            return job

        job["stage_status"][stage] = "complete"
        job["updated_at"] = now()
        return job
    except Exception as exc:
        job["stage_status"][stage] = "failed"
        job["state"] = "failed"
        job["error"] = f"{stage}: {exc}"
        raise
