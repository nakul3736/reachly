# 03 â€” Lever, Ashby and The Muse

**What to build:** the index draws from all four sources. Three more adapters behind the same
transport seam, each with a recorded payload. The Muse matters most: spike 001 measured 96.7%
entry-level density against under 3% on company boards, so it is where the roles this product
exists for actually are.

**Blocked by:** 02 â€” the transport seam, normalisation and upsert path.

**Status:** done

- [x] Lever adapter against the verified shape
      `api.lever.co/v0/postings/{token}?mode=json`
- [x] Ashby adapter against `api.ashbyhq.com/posting-api/job-board/{token}`
- [x] The Muse adapter against `themuse.com/api/public/jobs?page=N&level=Entry%20Level`,
      keyless, paginated
- [x] Muse rows are stored as **unverified** â€” it is an aggregator, so its postings are a
      copy of unknown age and the feed must not present them as company-confirmed
- [x] Each adapter has a payload recorded from the live API, and the four recorded payloads
      are asserted to differ structurally, the way the resume variants are. Four fixtures
      that happen to look alike would pass while testing nothing
- [x] A source returning zero results is distinguishable from a source that failed
- [x] Muse pagination stops at a bounded page count rather than following pages until the
      API disagrees
- [x] Each source's contribution is visible in `GET /api/v1/sources`, so an adapter that
      silently stops returning anything is noticed
- [x] The feed shows jobs from all four sources, and the source is visible on every row

## What the four sources produced

| Source | Postings | Verified | Explicit entry level |
|---|---|---|---|
| Greenhouse | 2,586 | yes | 14 |
| Ashby | 1,145 | yes | 8 |
| Lever | 466 | yes | 16 |
| **The Muse** | **240** | no | **237** |
| | 4,437 | | 275 |

The Muse is 5% of the index and 85% of everything in it that is explicitly entry level. Spike
001 predicted 96.7% density against 2.8% on company boards; the ingested data reproduces that
almost exactly. It is also why the aggregator was worth the extra rules it forces — unverified
storage, timer expiry instead of absence sweeping, and losing to a board record in dedup.

The company boards still supply most of the *useful* postings, though: of 166 graduate-suitable
software roles in the US or Canada, Greenhouse contributed 85 and The Muse 7. The Muse's
entry-level filter is not a software filter, which is exactly what the role-family classifier
was built for.

## Notes from implementation

**Each provider disagrees with the others somewhere that matters.** Lever returns a bare JSON
array rather than an object, puts the title in `text`, and dates postings in **epoch
milliseconds** — passed to a seconds parser that becomes the year 58,000, read as ISO it fails
and the posting looks undated. Lever also splits a posting between `description` and
`additional`, so storing only the first drops the responsibilities and requirements, which is
both what a student needs and what feature 04 tailors against.

Ashby is the most cooperative: it supplies stripped plain text and states `isRemote` outright.
That produced a small design rule — a provider's own claim is consulted only where Reachly's own
deterministic rules came back unknown. The Muse marking `Security Officer` as entry level is a
fact no title rule can derive, and discarding it would waste the one thing that source is better
at. But a hint never overrides a rule that did fire, or an aggregator could quietly relabel a
senior role into a graduate's feed.

**A real posting broke the schema.** One Muse job listed in dozens of cities produced 820
characters of location against `varchar(500)`, which failed the entire refresh with a 500 rather
than dropping one posting. Provider-supplied display text has no length we get to assume, story
21 says it is shown as written so truncating loses what the student reads, and Postgres charges
nothing for `text` over `varchar`. Reproduced as a failing test before the column was changed.
The migration notes that its downgrade can legitimately fail on a populated database — refusing
is better than silently cutting a student's data.

**The transport seam became a real module, prompted by a real mistake.** The refresh endpoint
constructed its own client, which meant the test suite was quietly making live requests to The
Muse. `adapters/http.py` is now the single place clients are made, and the cron tests substitute
a transport that answers 503 to anything not explicitly stubbed — so a forgotten stub fails a
test instead of reaching the network.

**One test had to change rather than the code.** The guard for "a provider with no adapter yet"
named Ashby, which now has one. It names two providers that genuinely have none instead, because
the behaviour it protects — an unbuilt provider must not take down the run — still matters and
would otherwise have been silently deleted by its own success.