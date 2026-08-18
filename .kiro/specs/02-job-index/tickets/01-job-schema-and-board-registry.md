# 01 — Job schema and the board token registry

**What to build:** Reachly knows which company boards exist, and can tell you their state.
`GET /api/v1/sources` lists every registered board with its provider, company name, whether
it is active, and when it was last fetched successfully. A seed command populates a curated
set of real boards, so adding a company later is a data change rather than a deployment.

Nothing is fetched yet. This ticket exists so the next one has somewhere to put jobs and
something to iterate over.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `board_token` table: provider, token, company name, active flag, `last_fetched_at`,
      `last_succeeded_at`, `consecutive_failures`, `last_error`, unique on
      `(provider, token)`
- [ ] `job` table per the design, **unique on `(source, source_job_id)`** — the constraint
      that makes ingestion idempotent, expressed as a constraint rather than a
      check-then-insert because two concurrent refreshes would both pass the check
- [ ] `dedup_verdict` table with the pair stored in sorted order, so the same comparison
      cannot be cached twice under opposite orderings
- [ ] Migrations apply from empty, `alembic check` is clean, and `alembic downgrade base`
      succeeds
- [ ] Generated migration files are reformatted so ruff passes — autogenerate emits long
      lines and unsorted imports
- [ ] A seed command registers a curated set of real Greenhouse, Lever and Ashby boards,
      taken from the tokens spike 001 verified as reachable
- [ ] Seeding is idempotent: running it twice leaves one row per board and does not reset
      failure counters
- [ ] `GET /api/v1/sources` returns each board's state, and is public — a visitor should be
      able to see the product has real companies behind it
- [ ] Timestamps are timezone-aware and UTC
