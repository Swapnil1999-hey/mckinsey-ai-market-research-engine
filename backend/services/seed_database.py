import csv
import os
from pathlib import Path
from database.db import db_enabled, session
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

def rows(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def main():
    if not db_enabled():
        raise SystemExit("DATABASE_URL is not configured")
    reqs = rows("sample_research_requests.csv")
    sources = rows("sample_sources.csv")
    evidence = rows("sample_evidence_records.csv")
    metrics = rows("sample_market_metrics.csv")
    with session() as c:
        for r in reqs:
            c.execute(text("""insert into research_requests(request_id,query,market,geography,timeframe,competitors,deliverable,report_depth,status)
              values (:id,:query,:market,:geo,:time,:comp,:deliv,:depth,:status)
              on conflict(request_id) do update set query=excluded.query, market=excluded.market, geography=excluded.geography,
              timeframe=excluded.timeframe, competitors=excluded.competitors, deliverable=excluded.deliverable, report_depth=excluded.report_depth, status=excluded.status"""),
              {"id":r["request_id"],"query":r.get("query", ""),"market":r.get("market",""),"geo":r.get("geography",""),"time":r.get("timeframe",""),"comp":r.get("competitors", ""),"deliv":r.get("output_format",r.get("deliverable","internal review")),"depth":r.get("report_depth","standard"),"status":r.get("status","completed")})
        for r in sources:
            c.execute(text("""insert into sources(source_id,request_id,url,title,publisher,source_type,retrieval_date,quality_score,relevance_score)
              values (:id,:rid,:url,:title,:pub,:type,now(),:quality,:relevance) on conflict(source_id) do nothing"""),
              {"id":r["source_id"],"rid":r["request_id"],"url":r["url"],"title":r.get("title"),"pub":r.get("publisher"),"type":r.get("source_type"),"quality":float(r.get("quality_score") or 0),"relevance":float(r.get("relevance_score") or 0)})
        for r in evidence:
            c.execute(text("""insert into evidence_records(evidence_id,request_id,source_id,claim,excerpt,entity,topic,evidence_date,confidence,credibility,recency,validation,duplicate_flag,contradiction_flag)
              values (:id,:rid,:sid,:claim,:excerpt,:entity,:topic,:date,:confidence,:credibility,:recency,:validation,:dup,:contra)
              on conflict(evidence_id) do update set claim=excluded.claim, excerpt=excluded.excerpt, validation=excluded.validation"""),
              {"id":r["evidence_id"],"rid":r["request_id"],"sid":r.get("source_id"),"claim":r["claim"],"excerpt":r.get("excerpt"),"entity":r.get("entity"),"topic":r.get("topic"),"date":r.get("date"),"confidence":float(r.get("confidence") or 0),"credibility":float(r.get("credibility") or 0),"recency":float(r.get("recency") or 0),"validation":r.get("validation","review"),"dup":str(r.get("duplicate_flag","false")).lower()=="true","contra":str(r.get("contradiction_flag","false")).lower()=="true"})
        for r in metrics:
            for metric_name, value in (("signal_index", r.get("signal_index")), ("adoption_percent", r.get("adoption_percent"))):
                if value in (None, ""): continue
                mid=f"{r.get('market','')}-{r.get('year','')}-{metric_name}"
                c.execute(text("""insert into market_metrics(metric_id,market,geography,year,metric,value,unit)
                  values (:id,:market,'',:year,:metric,:value,:unit) on conflict(metric_id) do update set value=excluded.value"""),
                  {"id":mid,"market":r.get("market"),"year":int(r.get("year") or 0),"metric":metric_name,"value":float(value),"unit":"index" if metric_name=="signal_index" else "%"})
    print(f"Imported {len(reqs)} requests, {len(sources)} sources, {len(evidence)} evidence records, {len(metrics)} metrics.")

if __name__ == "__main__": main()
