# 01 — Job schema and the board token registry

**What to build:** Reachly knows which company boards exist, and can tell you their state.
`GET /api/v1/sources` lists every registered board with its provider, company name, whether
it is active, and when it was last fetched successfully. A seed command populates a curated
set of real boards, so adding a company later is a data change rather than a deployment.

Nothing is fetched yet. This ticket exists so the next one has somewhere to put jobs and
something to iterate over.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `board_token` table: provider, token, company name, active flag, `last_fetched_at`,
      `last_succeeded_at`, `consecutive_failures`, `last_error`, unique on
      `(provider, token)`
- [x] `job` table per the design, **unique on `(source, source_job_id)`** — the constraint
      that makes ingestion idempotent, expressed as a constraint rather than a
      check-then-insert because two concurrent refreshes would both pass the check
- [x] `dedup_verdict` table with the pair stored in sorted order, so the same comparison
      cannot be cached twice under opposite orderings
- [x] Migrations apply from empty, `alembic check` is clean, and `alembic downgrade base`
      succeeds
- [x] Generated migration files are reformatted so ruff passes — autogenerate emits long
      lines and unsorted imports
- [x] A seed command registers a curated set of real Greenhouse, Lever and Ashby boards,
      taken from the tokens spike 001 verified as reachable
- [x] Seeding is idempotent: running it twice leaves one row per board and does not reset
      failure counters
- [x] `GET /api/v1/sources` returns each board's state, and is public — a visitor should be
      able to see the product has real companies behind it
- [x] Timestamps are timezone-aware and UTC

## Notes from implementation

**Where TDD discipline slipped, and what it cost.** The tests for the three tables were
written before the models, but they were written *all at once* — thirteen of them in one
file, then all three models — which the TDD skill names as horizontal slicing, and I never
ran them to watch them fail. Both halves of red-green were skipped: no red observed, no
vertical slice.

It cost something concrete. Wiring board seeding into startup put `await seed_boards(session)`
on **both** return paths of `seed_demo_student`, so every container start seeded the registry
twice. The suite stayed green throughout, because no test asserted how many times seeding
runs — a test I would have been forced to think about had I been working one slice at a time.

**Five tests were then deleted as worthless.** `test_a_board_can_be_registered`,
`test_a_job_can_be_stored`, `test_timestamps_are_timezone_aware_and_utc`,
`test_a_job_can_be_marked_closed` and `test_a_verdict_can_be_cached` all inserted a row and
read it back. They assert that SQLAlchemy works. Every invariant in the schema could be
deleted and all five would still pass. What remains are the constraint tests, which genuinely
fail if the constraint is missing, and the endpoint tests, which go through the API.

**Board seeding was moved out of the demo account seed** while fixing the duplication, and
that turned out to matter. The demo account needs credentials from the environment and
legitimately fails without them; the registry needs nothing. Seeding them together meant a
deployment without demo credentials also got an empty job index — a much worse failure than
a missing test login. Boards now seed first and independently.

**The Muse is deliberately not in the registry.** It is one endpoint for every company, not
one board per company, so a row for it would imply a per-company token that does not exist —
and would put an aggregator in a table whose rows are treated as authoritative for closure
detection. There is a test asserting it stays out.
