create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists research_requests (
  id uuid primary key default gen_random_uuid(),
  request_id text unique not null,
  query text not null,
  market text default '',
  geography text default '',
  timeframe text default '',
  competitors text default '',
  deliverable text default 'internal review',
  report_depth text default 'standard',
  status text default 'pending',
  created_at timestamptz default now()
);

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  source_id text unique not null,
  request_id text references research_requests(request_id) on delete cascade,
  url text not null,
  title text,
  publisher text,
  source_type text,
  retrieval_date timestamptz default now(),
  quality_score double precision,
  relevance_score double precision
);

create table if not exists evidence_records (
  id uuid primary key default gen_random_uuid(),
  evidence_id text unique not null,
  request_id text references research_requests(request_id) on delete cascade,
  source_id text references sources(source_id) on delete set null,
  claim text not null,
  excerpt text,
  entity text,
  topic text,
  evidence_date date,
  confidence double precision,
  credibility double precision,
  recency double precision,
  validation text default 'review',
  duplicate_flag boolean default false,
  contradiction_flag boolean default false,
  embedding vector(1536),
  updated_at timestamptz default now()
);

create table if not exists market_metrics (
  id uuid primary key default gen_random_uuid(),
  metric_id text unique,
  market text,
  geography text,
  year integer,
  metric text,
  value double precision,
  unit text
);

create index if not exists idx_evidence_request on evidence_records(request_id);
create index if not exists idx_evidence_validation on evidence_records(validation);
create index if not exists idx_evidence_topic on evidence_records(topic);
create index if not exists idx_evidence_embedding on evidence_records using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists idx_sources_request on sources(request_id);

create or replace function match_evidence(
  query_embedding vector(1536),
  match_threshold float default 0.70,
  match_count int default 10
)
returns table (
  evidence_id text, claim text, excerpt text, entity text, topic text,
  confidence double precision, validation text, similarity float
)
language sql stable
as $$
  select e.evidence_id, e.claim, e.excerpt, e.entity, e.topic,
         e.confidence, e.validation,
         1 - (e.embedding <=> query_embedding) as similarity
  from evidence_records e
  where e.embedding is not null
    and 1 - (e.embedding <=> query_embedding) >= match_threshold
  order by e.embedding <=> query_embedding
  limit match_count;
$$;

create table if not exists reports (
  id uuid primary key default gen_random_uuid(),
  request_id text unique references research_requests(request_id) on delete cascade,
  title text,
  report jsonb not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists research_feedback (
  id uuid primary key default gen_random_uuid(),
  request_id text references research_requests(request_id) on delete cascade,
  action text not null,
  notes text default '',
  created_at timestamptz default now()
);
