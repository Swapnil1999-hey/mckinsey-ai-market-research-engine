# Dynamic Dataset Performance Fix

The dashboard previously calculated its overview by joining `research_requests`,
`sources`, and `evidence_records` in one query. That can create a large
intermediate result because each request may have many sources and evidence
records.

This update:
- uses independent aggregate queries instead of a three-table fan-out;
- aggregates evidence by `evidence_date` in PostgreSQL;
- adds a 30-second dashboard aggregate cache;
- adds indexes for evidence dates, updates, request market/geography, and source retrieval;
- keeps Evidence Review paginated;
- gives the dashboard a 10-second request timeout and a useful error state.

## Apply the database indexes

Run `deployment/supabase/schema.sql` in the Supabase SQL editor. The new
indexes are safe `CREATE INDEX IF NOT EXISTS` statements.

No API keys or passwords should be committed to the project ZIP. Keep secrets
in `backend/.env` locally.
