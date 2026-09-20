from pathlib import Path
import csv
from collections import Counter, defaultdict
from typing import Any
from database.db import db_enabled, fetch_all, fetch_one, session
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'

class DatasetStore:
    """Database-first intelligence store with a safe bundled CSV fallback."""
    def __init__(self):
        self.requests = self._read('sample_research_requests.csv')
        self.sources = self._read('sample_sources.csv')
        self.evidence = self._read('sample_evidence_records.csv')
        self.metrics = self._read('sample_market_metrics.csv')

    @property
    def live(self):
        return db_enabled() and __import__('os').getenv('DATA_SOURCE','auto').lower() != 'demo'

    def _read(self, name):
        with open(DATA / name, newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def _page(self, rows, page=1, page_size=25):
        page=max(1,int(page)); page_size=max(1,min(100,int(page_size)))
        total=len(rows); start=(page-1)*page_size
        return {'items':rows[start:start+page_size],'page':page,'page_size':page_size,'total':total,'pages':max(1,(total+page_size-1)//page_size)}

    def overview(self, market=None, geography=None):
        """Return compact dashboard aggregates without loading the full evidence dataset."""
        if self.live:
            # Keep the dashboard fast: every metric is aggregated in SQL and only
            # a few dozen rows are returned to the browser.
            key = (market or "All", geography or "All")
            filters_r = []
            params = {}
            if market and market != "All":
                filters_r.append("market = :market")
                params["market"] = market
            if geography and geography != "All":
                filters_r.append("geography = :geo")
                params["geo"] = geography
            rw = (" WHERE " + " AND ".join(filters_r)) if filters_r else ""

            filters_e = []
            if market and market != "All":
                filters_e.append("r.market = :market")
            if geography and geography != "All":
                filters_e.append("r.geography = :geo")
            ew = (" WHERE " + " AND ".join(filters_e)) if filters_e else ""

            stats = fetch_one(f"""
                SELECT
                  (SELECT count(*) FROM research_requests{rw}) AS requests,
                  (SELECT count(*) FROM sources s JOIN research_requests r ON r.request_id=s.request_id
                     {ew}) AS sources,
                  (SELECT count(*) FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                     {ew}) AS evidence,
                  (SELECT count(*) FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                     {(' WHERE ' + ' AND '.join(filters_e + ["e.validation = 'pass'"])) if filters_e else " WHERE e.validation = 'pass'"}) AS validated_evidence,
                  (SELECT count(*) FROM research_requests{rw}{' AND ' if rw else ' WHERE '}status='completed') AS completed,
                  (SELECT count(*) FROM research_requests{rw}{' AND ' if rw else ' WHERE '}status='running') AS running,
                  (SELECT count(*) FROM research_requests{rw}{' AND ' if rw else ' WHERE '}status='pending') AS pending,
                  (SELECT count(*) FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                     {(' WHERE ' + ' AND '.join(filters_e + ["e.validation <> 'pass'"])) if filters_e else " WHERE e.validation <> 'pass'"}) AS needs_review,
                  COALESCE((SELECT avg(e.confidence)*100 FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                     {ew}), 0) AS avg_confidence
            """, params) or {}

            topics = fetch_all(f"""SELECT e.topic AS label, count(*) AS value
                FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                {ew} GROUP BY e.topic ORDER BY value DESC LIMIT 8""", params)
            entities = fetch_all(f"""SELECT e.entity AS label, count(*) AS value
                FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                {ew} GROUP BY e.entity ORDER BY value DESC LIMIT 8""", params)
            years = fetch_all(f"""SELECT extract(year FROM e.evidence_date)::int AS year, count(*) AS value
                FROM evidence_records e JOIN research_requests r ON r.request_id=e.request_id
                {(' WHERE ' + ' AND '.join(filters_e + ['e.evidence_date IS NOT NULL'])) if filters_e else ' WHERE e.evidence_date IS NOT NULL'}
                GROUP BY 1 ORDER BY 1""", params)

            # Do NOT compare a bound parameter to the SQL identifier "All".
            # Build the market/geography filter explicitly instead.
            metric_filters = []
            metric_params = {}
            if market and market != "All":
                metric_filters.append("market = :metric_market")
                metric_params["metric_market"] = market
            if geography and geography != "All":
                metric_filters.append("geography = :metric_geo")
                metric_params["metric_geo"] = geography
            mw = (" WHERE " + " AND ".join(metric_filters)) if metric_filters else ""
            metrics = fetch_all(f"""SELECT market, geography, year, metric, value, unit
                FROM market_metrics{mw} ORDER BY year""", metric_params)

            result = {
                "demo": False,
                **{k: (v or 0) for k, v in stats.items()},
                "top_topics": topics,
                "top_entities": entities,
                "evidence_by_year": years,
                "market_metrics": metrics,
            }
            return result
        return self._demo_overview(market, geography)

    def _demo_overview(self, market=None, geography=None):
        reqs=self.requests
        if market and market!='All': reqs=[x for x in reqs if x['market']==market]
        if geography and geography!='All': reqs=[x for x in reqs if x['geography']==geography]
        ids={x['request_id'] for x in reqs}; sources=[x for x in self.sources if x['request_id'] in ids]; evidence=[x for x in self.evidence if x['request_id'] in ids]; validated=[x for x in evidence if x['validation']=='pass']
        status=Counter(x['status'] for x in reqs); topic=Counter(x['topic'] for x in evidence); entities=Counter(x['entity'] for x in evidence); year=defaultdict(int)
        for x in evidence: year[x['date'][:4]]+=1
        return {'demo':True,'requests':len(reqs),'sources':len(sources),'evidence':len(evidence),'validated_evidence':len(validated),'completed':status.get('completed',0),'running':status.get('running',0),'pending':status.get('pending',0),'needs_review':sum(1 for x in evidence if x['validation']!='pass'),'avg_confidence':round(sum(float(x['confidence']) for x in evidence)/max(len(evidence),1)*100,1),'top_topics':[{'label':k,'value':v} for k,v in topic.most_common(8)],'top_entities':[{'label':k,'value':v} for k,v in entities.most_common(8)],'evidence_by_year':[{'year':k,'value':year[k]} for k in sorted(year)],'market_metrics':[x for x in self.metrics if not market or market=='All' or x['market']==market]}

    def filters(self):
        if self.live:
            return {'markets':['All']+[x['market'] for x in fetch_all('select distinct market from research_requests where market is not null and market<>\'\' order by market')], 'geographies':['All']+[x['geography'] for x in fetch_all('select distinct geography from research_requests where geography is not null and geography<>\'\' order by geography')], 'topics':['All']+[x['topic'] for x in fetch_all('select distinct topic from evidence_records where topic is not null and topic<>\'\' order by topic')], 'statuses':['All','pass','review']}
        return {'markets':['All']+sorted({x['market'] for x in self.requests}),'geographies':['All']+sorted({x['geography'] for x in self.requests}),'topics':['All']+sorted({x['topic'] for x in self.evidence}),'statuses':['All','pass','review']}

    def evidence_page(self, page=1, page_size=20, market='All', topic='All', validation='All', search=''):
        if self.live:
            where=['1=1']; p={}
            if market!='All': where.append('r.market=:market'); p['market']=market
            if topic!='All': where.append('e.topic=:topic'); p['topic']=topic
            if validation!='All': where.append('e.validation=:validation'); p['validation']=validation
            if search.strip(): where.append('(e.claim ilike :q or e.entity ilike :q or e.excerpt ilike :q)'); p['q']=f"%{search.strip()}%"
            off=(max(1,page)-1)*min(100,max(1,page_size)); lim=min(100,max(1,page_size))
            total=(fetch_one(f'''select count(*) total from evidence_records e join research_requests r on r.request_id=e.request_id where {' and '.join(where)}''',p) or {'total':0})['total']
            rows=fetch_all(f'''select e.evidence_id,e.claim,e.excerpt,e.entity,e.topic,e.evidence_date date,e.confidence,e.credibility,e.recency,e.validation,e.source_id,r.market,r.geography from evidence_records e join research_requests r on r.request_id=e.request_id where {' and '.join(where)} order by e.updated_at desc nulls last,e.evidence_id offset :off limit :lim''',{**p,'off':off,'lim':lim})
            pages=max(1,(total+lim-1)//lim); return {'items':rows,'page':page,'page_size':lim,'total':total,'pages':pages}
        req_by_id={x['request_id']:x for x in self.requests}; rows=[]; q=(search or '').lower().strip()
        for x in self.evidence:
            req=req_by_id.get(x['request_id'],{})
            if market!='All' and req.get('market')!=market or topic!='All' and x['topic']!=topic or validation!='All' and x['validation']!=validation: continue
            if q and q not in (x['claim']+' '+x['entity']+' '+x['excerpt']).lower(): continue
            rows.append({**x,'market':req.get('market',''),'geography':req.get('geography','')})
        return self._page(rows,page,page_size)

    def sources_page(self,page=1,page_size=20,market='All',source_type='All',search=''):
        if self.live:
            where=['1=1'];p={}
            if market!='All': where.append('r.market=:market');p['market']=market
            if source_type!='All': where.append('s.source_type=:type');p['type']=source_type
            if search.strip(): where.append('(s.title ilike :q or s.publisher ilike :q or s.url ilike :q)');p['q']=f"%{search.strip()}%"
            lim=min(100,max(1,page_size));off=(max(1,page)-1)*lim;total=(fetch_one(f'''select count(*) total from sources s join research_requests r on r.request_id=s.request_id where {' and '.join(where)}''',p) or {'total':0})['total']
            rows=fetch_all(f'''select s.source_id,s.url,s.title,s.publisher,s.source_type,s.retrieval_date,r.market,r.geography from sources s join research_requests r on r.request_id=s.request_id where {' and '.join(where)} order by s.retrieval_date desc offset :off limit :lim''',{**p,'off':off,'lim':lim});return {'items':rows,'page':page,'page_size':lim,'total':total,'pages':max(1,(total+lim-1)//lim)}
        req_by_id={x['request_id']:x for x in self.requests};rows=[];q=(search or '').lower().strip()
        for x in self.sources:
            req=req_by_id.get(x['request_id'],{})
            if market!='All' and req.get('market')!=market or source_type!='All' and x['source_type']!=source_type: continue
            if q and q not in (x['title']+' '+x['publisher']+' '+x['url']).lower(): continue
            rows.append({**x,'market':req.get('market',''),'geography':req.get('geography','')})
        return self._page(rows,page,page_size)

    def knowledge(self, market='All'):
        if self.live:
            p={'market':market}; where='1=1' if market=='All' else 'r.market=:market'
            n=fetch_one(f'''select count(*) count from evidence_records e join research_requests r on r.request_id=e.request_id where e.validation='pass' and {where}''',p)['count']
            topics=fetch_all(f'''select e.topic,count(*) count from evidence_records e join research_requests r on r.request_id=e.request_id where e.validation='pass' and {where} group by e.topic order by count desc limit 12''',p)
            entities=fetch_all(f'''select e.entity,count(*) count from evidence_records e join research_requests r on r.request_id=e.request_id where e.validation='pass' and {where} group by e.entity order by count desc limit 12''',p)
            return {'validated_findings':n,'topic_patterns':topics,'entities':entities}
        ids={x['request_id'] for x in self.requests if market=='All' or x['market']==market};ev=[x for x in self.evidence if x['request_id'] in ids and x['validation']=='pass'];topics=Counter(x['topic'] for x in ev);entities=Counter(x['entity'] for x in ev);return {'validated_findings':len(ev),'topic_patterns':[{'topic':k,'count':v} for k,v in topics.most_common(12)],'entities':[{'entity':k,'count':v} for k,v in entities.most_common(12)]}

    def search_research_evidence(self, query: str, limit: int = 12):
        terms=[t.lower() for t in __import__('re').findall(r'[A-Za-z0-9]{4,}', query or '')]
        terms=list(dict.fromkeys(terms))[:12]
        if self.live:
            if not terms:
                return []
            clauses=[]; params={'lim':max(1,min(50,limit))}
            for i,t in enumerate(terms):
                params[f'q{i}']=f'%{t}%'
                clauses.append(f'(lower(e.claim) like :q{i} or lower(e.excerpt) like :q{i} or lower(e.topic) like :q{i} or lower(e.entity) like :q{i})')
            rows=fetch_all(f'''select e.evidence_id,e.claim,e.excerpt,e.entity,e.topic,e.evidence_date date,e.confidence,e.source_id,s.url source,s.title source_title
                from evidence_records e left join sources s on s.source_id=e.source_id
                where e.validation='pass' and ({' or '.join(clauses)})
                order by e.confidence desc nulls last,e.updated_at desc nulls last limit :lim''',params)
            return rows
        q=(query or '').lower()
        rows=[]
        for e in self.evidence:
            hay=' '.join([e.get('claim',''),e.get('excerpt',''),e.get('topic',''),e.get('entity','')]).lower()
            score=sum(1 for t in terms if t in hay)
            if score and e.get('validation')=='pass': rows.append((score,e))
        rows.sort(key=lambda x:x[0],reverse=True)
        return [x[1] for x in rows[:limit]]

    def update_evidence(self, evidence_id:str, validation:str, claim:str|None=None):
        if self.live:
            with session() as c:
                r=c.execute(text('''update evidence_records set validation=:v,claim=coalesce(:claim,claim),updated_at=now() where evidence_id=:id returning evidence_id,claim,validation'''),{'id':evidence_id,'v':validation,'claim':claim}).first()
                if not r: return None
                return dict(r._mapping)
        for x in self.evidence:
            if x['evidence_id']==evidence_id:
                x['validation']=validation
                if claim: x['claim']=claim
                return x
        return None
