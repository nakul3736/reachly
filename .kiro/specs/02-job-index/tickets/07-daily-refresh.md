# 07 — The daily refresh

**What to build:** the index maintains itself. One external trigger runs every source, ingests,
classifies, dedups and sweeps for closures, and one broken board cannot take the run down with
it. `GET /api/v1/sources` afterwards shows what each source contributed.

**Blocked by:** 03, 05, 06 — this wires together what they build.

**Status:** ready-for-agent

- [ ] `POST /cron/refresh-jobs` runs the full cycle: fetch every active board, ingest,
      classify, dedup, sweep closures, expire stale aggregator rows
- [ ] Driven by an **external** trigger per ADR 0007 — an in-process timer silently stops on a
      host that suspends idle processes, and silently is the problem
- [ ] Cron behaviour unchanged from ticket 01: outside `/api/v1`, secret required, **404 rather
      than 401**, and fails closed when the secret is unset
- [ ] **One failing board does not abort the run.** Each board is isolated; a Lever outage must
      not cost us Greenhouse, Ashby and The Muse
- [ ] A failing board increments `consecutive_failures` and records `last_error`; a success
      resets both
- [ ] Repeatedly failing boards are **backed off** rather than retried at full rate forever,
      so a permanently dead company does not consume the run window every day
- [ ] The run is bounded in time and reports per-source counts — fetched, created, updated,
      skipped, closed — so a silently broken adapter is visible rather than merely quiet
- [ ] The run is idempotent: triggered twice in a row, the second changes nothing but
      `last_seen_at`
- [ ] A partially completed run leaves the index consistent, never half-swept
- [ ] The two GitHub repository secrets are set so the keep-alive workflow stops being a no-op,
      and a second independent trigger is registered per ADR 0007 — one scheduler is a single
      point of failure during a judged window
- [ ] `GET /api/v1/sources` shows `last_succeeded_at` per source, and the feed screen surfaces
      how fresh the index is. Story 18 — a student needs to know whether they are looking at
      today's jobs or last week's
