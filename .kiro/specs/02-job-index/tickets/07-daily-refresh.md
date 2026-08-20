# 07 â€” The daily refresh

**What to build:** the index maintains itself. One external trigger runs every source, ingests,
classifies, dedups and sweeps for closures, and one broken board cannot take the run down with
it. `GET /api/v1/sources` afterwards shows what each source contributed.

**Blocked by:** 03, 05, 06 â€” this wires together what they build.

**Status:** done — except the two console steps noted below, which need repository and scheduler access

- [x] `POST /cron/refresh-jobs` runs the full cycle: fetch every active board, ingest,
      classify, dedup, sweep closures, expire stale aggregator rows
- [x] Driven by an **external** trigger per ADR 0007 â€” an in-process timer silently stops on a
      host that suspends idle processes, and silently is the problem
- [x] Cron behaviour unchanged from ticket 01: outside `/api/v1`, secret required, **404 rather
      than 401**, and fails closed when the secret is unset
- [x] **One failing board does not abort the run.** Each board is isolated; a Lever outage must
      not cost us Greenhouse, Ashby and The Muse
- [x] A failing board increments `consecutive_failures` and records `last_error`; a success
      resets both
- [x] Repeatedly failing boards are **backed off** rather than retried at full rate forever,
      so a permanently dead company does not consume the run window every day
- [x] The run is bounded in time and reports per-source counts â€” fetched, created, updated,
      skipped, closed â€” so a silently broken adapter is visible rather than merely quiet
- [x] The run is idempotent: triggered twice in a row, the second changes nothing but
      `last_seen_at`
- [x] A partially completed run leaves the index consistent, never half-swept
- [ ] The two GitHub repository secrets are set so the keep-alive workflow stops being a no-op,
      and a second independent trigger is registered per ADR 0007 â€” one scheduler is a single
      point of failure during a judged window
- [x] `GET /api/v1/sources` shows `last_succeeded_at` per source, and the feed screen surfaces
      how fresh the index is. Story 18 â€” a student needs to know whether they are looking at
      today's jobs or last week's

## Verified live, end to end

Three consecutive runs against the real index:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| boards | 18/18 | 18/18 | 18/18 |
| created | 174 | 0 | 0 |
| updated | 4,292 | 4,465 | 4,465 |
| closed | 0 | 1 | 0 |
| dedup collapsed | 13 | 0 | 0 |
| elapsed | 16.3s | 18.2s | — |

**Idempotent, as claimed:** the second identical run created nothing and collapsed nothing.

**The one closure was real, and proving it took a third run.** Coinbase withdrew `Strategic
Intelligence Manager, Protective Intelligence` between run 1 and run 2. A posting closed by a
flaky provider response would have reappeared on the next fetch and shown as `reopened: 1`; run 3
reported zero reopens, so the absence was genuine. Closure detection catching a live withdrawal
inside a minute is the strongest evidence this feature has.

Wrong secret returns **404**, not 401. Every board reports `last_succeeded_at`. The graduate
software filter returns 170 postings after the cycle, so the feed still serves what the refresh
just rewrote.

## Notes from implementation

**Backoff is a delay, never deactivation.** A board that has failed three times or more waits
`2^n` hours up to a cap of 72. Deactivating instead would be permanent in practice, because
nothing in this system would ever reactivate a board it had given up on — and a company that
deletes its board today may restore it tomorrow. Backed-off boards are counted separately from
failures: a board nobody asked is not a board that broke, and conflating them would have the
interface report a problem the run deliberately avoided.

**The run is bounded, and the ordering is what makes a short run fair.** Boards are visited least
recently fetched first, so the ones a truncated run misses are the ones the next run starts with.
Without that, a repeatedly truncated run would refresh the same prefix forever and the tail of the
registry would never be read. The host kills a request that outlives its limit and a killed run
reports nothing at all — no counts, no errors, indistinguishable from a run that found nothing —
so stopping early with a truthful summary is strictly better.

**A partial run cannot half-sweep.** Closure is scoped to the board just fetched, so a board never
reached keeps every posting. The alternative shape — sweeping globally once at the end — would
close the entire index every time a run was cut short.

**Dedup runs after classification, not before.** It reuses the seniority and role family derived a
moment earlier to rule pairs out for free, which is what keeps the inference band small. No
inference client is passed in the cron path: the deployed demo has no key, and a cycle that needed
one would silently do nothing in the environment the judges use.

**`scheduled-refresh.yml` did not exist.** The README described the keep-alive workflow and the
secrets it needs, and ticket 01 built the endpoint, but nothing ever created the workflow — so the
"external trigger" of ADR 0007 was documentation only. It now wakes the service first (a cold start
on the free tier can outlast the refresh request's own timeout, and a slow start must not be
reported as a refresh failure), fails closed with the missing secret named rather than reporting
success for requests it never made, and annotates a run that closes more than 500 postings, which
is the shape of an adapter change that empties the feed while every count looks busy.

## Two steps that need your access

1. **Repository secrets** — Settings ? Secrets and variables ? Actions ? New repository secret.
   Add `API_BASE_URL` = `https://reachly-api-82u2.onrender.com` and `CRON_SECRET` = the same value
   set on the Render service. Until both exist the workflow fails closed by design.
2. **A second, independent trigger** per ADR 0007 — register the same `POST` at cron-job.org with
   the `X-Cron-Secret` header. One scheduler is a single point of failure, and GitHub's cron is
   documented to run late or skip under load.