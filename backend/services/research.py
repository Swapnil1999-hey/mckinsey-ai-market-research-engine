from datetime import datetime, date, timezone
import re
from agents.workflow import run_stage
from database.db import db_enabled, session
from sqlalchemy import text
import json, hashlib

STAGES = ["intake","planning","browsing","extraction","validation","aggregation","report_generation","review"]


def normalize_evidence_date(value):
    """Convert AI-generated dates to PostgreSQL DATE-compatible ISO values."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    value = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(value, fmt).date().replace(day=1).isoformat()
        except ValueError:
            pass
    if re.fullmatch(r"\d{4}", value):
        return f"{value}-01-01"
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None

class ResearchService:
    def __init__(self): self.jobs = {}

    def _sync(self, job):
        if not db_enabled(): return
        req=job["request"]; rid=job["id"]
        with session() as c:
            c.execute(text('''insert into research_requests(request_id,query,market,geography,timeframe,competitors,deliverable,report_depth,status)
              values (:rid,:query,:market,:geo,:time,:comp,:deliv,:depth,:status)
              on conflict(request_id) do update set status=excluded.status'''),{
                "rid":rid,"query":req.get("query",""),"market":req.get("market",""),"geo":req.get("geography",""),"time":req.get("timeframe",""),
                "comp":json.dumps(req.get("competitors",[])),"deliv":req.get("output_format","internal review"),"depth":req.get("report_depth","standard"),"status":job.get("state","pending")})
            for i,s in enumerate(job.get("sources",[])):
                url=s.get("url");
                if not url: continue
                sid="src-"+hashlib.sha1(url.encode()).hexdigest()[:20]
                c.execute(text('''insert into sources(source_id,request_id,url,title,publisher,source_type,quality_score,relevance_score)
                  values (:sid,:rid,:url,:title,:pub,:type,:q,:rel) on conflict(source_id) do update set title=excluded.title'''),{
                  "sid":sid,"rid":rid,"url":url,"title":s.get("title","Untitled"),"pub":s.get("publisher",""),"type":s.get("type","web"),"q":s.get("quality_score"),"rel":s.get("relevance_score")})
            for i,e in enumerate(job.get("evidence",[])):
                claim=e.get("claim",""); eid="ev-"+hashlib.sha1((rid+claim+str(i)).encode()).hexdigest()[:20]; src=e.get("source","")
                sid="src-"+hashlib.sha1(src.encode()).hexdigest()[:20] if src else None
                val=e.get("validation",{}); validation="pass" if isinstance(val,dict) and val.get("credibility")=="pass" else e.get("validation","review") if isinstance(e.get("validation"),str) else "review"
                c.execute(text('''insert into evidence_records(evidence_id,request_id,source_id,claim,excerpt,entity,topic,evidence_date,confidence,credibility,recency,validation)
                  values (:eid,:rid,:sid,:claim,:excerpt,:entity,:topic,:date,:conf,:cred,:rec,:validation)
                  on conflict(evidence_id) do update set claim=excluded.claim,excerpt=excluded.excerpt,validation=excluded.validation,confidence=excluded.confidence'''),{
                  "eid":eid,"rid":rid,"sid":sid,"claim":claim,"excerpt":e.get("excerpt",""),"entity":e.get("entity",""),"topic":e.get("topic",""),"date":normalize_evidence_date(e.get("date")),
                  "conf":float(e.get("confidence") or 0),"cred":1.0 if validation=="pass" else 0.0,"rec":1.0 if e.get("date") else 0.0,"validation":validation})
            if job.get("report"):
                c.execute(text('''insert into reports(request_id,title,report) values (:rid,:title,cast(:report as jsonb))
                  on conflict(request_id) do update set title=excluded.title,report=excluded.report,updated_at=now()'''),{"rid":rid,"title":job["report"].get("title","Research report"),"report":json.dumps(job["report"])})

    def create(self,jid,data):
        self.jobs[jid]={"id":jid,"created_at":datetime.now(timezone.utc).isoformat(),"request":data,"state":"intake","stage_status":{s:"waiting" for s in STAGES},"sources":[],"evidence":[],"validated_evidence":[],"aggregation":None,"report":None,"feedback":[],"error":None}
        self.jobs[jid]["stage_status"]["intake"]="complete"; self._sync(self.jobs[jid]); return self.jobs[jid]
    def get(self,jid):
        if jid not in self.jobs: raise KeyError(jid)
        return self.jobs[jid]
    def _run(self,jid,stage):
        job=self.get(jid); result=run_stage(job,stage); self._sync(result); return result
    def plan(self,jid): return self._run(jid,"planning")
    def browse(self,jid): return self._run(jid,"browsing")
    def extract(self,jid): return self._run(jid,"extraction")
    def validate(self,jid): return self._run(jid,"validation")
    def aggregate(self,jid): return self._run(jid,"aggregation")
    def report(self,jid): return self._run(jid,"report_generation")
    def review(self,jid):
        job=self.get(jid);job["state"]="review";job["stage_status"]["review"]="ready";self._sync(job);return job
    def run_full(self,jid):
        for stage in ["planning","browsing","extraction","validation","aggregation","report_generation","review"]: self._run(jid,stage)
        return self.get(jid)
    def feedback(self,job_id,action,notes=""):
        job=self.get(job_id);job["feedback"].append({"action":action,"notes":notes,"created_at":datetime.now(timezone.utc).isoformat()});job["state"]="review";job["stage_status"]["review"]="complete"
        if db_enabled():
            with session() as c: c.execute(text("insert into research_feedback(request_id,action,notes) values (:rid,:action,:notes)"),{"rid":job_id,"action":action,"notes":notes})
        self._sync(job);return job
