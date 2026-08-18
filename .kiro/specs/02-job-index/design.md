# 02 — Design

## Implementation decisions

### Modules

- **`adapters/http.py`** — the outbound transport seam. Supplies the `httpx.AsyncClient`
  every job source uses, and is the single point where tests and demo mode substitute
  recorded provider responses.
- **`adapters/job_sources/`** — one module per provider: Greenhouse, Lever, Ashby, The Muse.
  Each does exactly one job: turn that provider's JSON into `RawPosting`. No HTTP policy, no
  database access, no filtering.
- **`domain/job.py`** — `RawPosting`, the normalisation rules, and the fingerprint used for
  identity. Pure functions.
- **`domain/role_family.py`** — deterministic classification of title into role family and
  seniority band. Pure functions, no model call.
- **`domain/location.py`** — country extraction and remote detection from a location string.
- **`domain/dedup.py`** — exact and fuzzy comparison, and the decision about which band a
  pair falls into. Pure; it does not make the model call itself.
- **`services/job_index_service.py`** — orchestration: fetch, upsert, classify, dedup, close.
  The only module that both talks to the database and knows the order things happen in.
- **`api/jobs.py`** — the feed, filters and a single job. **`api/sources.py`** — board
  registry status.

`services/` still may not import FastAPI or anything from `api/`, and adapters still may not
import services. Those held through feature 01 and are worth more as the codebase grows.

### Schema

**`board_token`** — the registry that makes adding a company data rather than code.

`id`, `provider` (greenhouse | lever | ashby), `token`, `company_name`, `active`,
`last_fetched_at`, `last_succeeded_at`, `consecutive_failures`, `last_error`.

Unique on `(provider, token)`. Spike 001 found Lever slugs are unguessable — 12 of 20
plausible guesses 404'd — which is the whole reason this table exists rather than a list of
company names being transformed into URLs at runtime.

`consecutive_failures` drives backoff. A board that has failed repeatedly is skipped for a
while rather than retried at full rate forever, and `last_error` means a silently broken
adapter is diagnosable without reproducing it.

**`job`** — the index itself.

`id`, `source`, `source_job_id`, `company_name`, `title`, `location_raw`, `country`,
`is_remote`, `description`, `apply_url`, `posted_at`, `first_seen_at`, `last_seen_at`,
`closed_at`, `role_family`, `seniority`, `is_verified`, `canonical_job_id`,
`content_fingerprint`.

**Unique on `(source, source_job_id)`.** This one constraint is what makes ingestion
idempotent, and it is a constraint rather than a check-then-insert for the same reason
duplicate email registration was in feature 01: two concurrent refreshes would both pass the
check.

`location_raw` is kept alongside the derived `country` because story 21 asks for it, and
because a classifier that guesses wrong should be visibly wrong rather than quietly
authoritative. Same principle as storing resume dates as written.

`is_verified` distinguishes a company board from an aggregator. `canonical_job_id` is a
self-referencing key: null means this row is canonical, set means it is an alias of another.

`closed_at` rather than deletion. Story 29 — a student's application must still resolve to
the job it was made against.

**`dedup_verdict`** — the permanent cache.

`fingerprint_low`, `fingerprint_high`, `same_job`, `decided_by` (exact | fuzzy | inference),
`decided_at`. Unique on the ordered pair, which is why the columns are named low and high
rather than a and b: the pair is sorted before storage so a comparison cannot be asked twice
in opposite orders.

### Identity, and why fingerprints rather than ids

A job's identity across sources cannot come from any provider's id, because no two providers
share one. It is derived from normalised company, title and location — the three things every
source carries.

Normalisation collapses whitespace, casefolds, and strips the punctuation and decoration that
differs between sources without changing meaning: `Inc.`, `Ltd`, trailing `(Remote)`,
requisition numbers appended to titles. The same `normalise` discipline as
`domain/evidence.py`, for the same reason — two spellings of one thing must compare equal or
every downstream rule is wrong.

Fingerprints are **content-derived, never positional**, exactly as bullet ids are in feature
01, and for the identical reason: a positional identifier keeps resolving while pointing at
something else.

### Dedup, per ADR 0005

Three bands, and only one of them costs anything:

- **Exact fingerprint match** → same job. Free.
- **`rapidfuzz` token-set ratio above 0.90, within the same company** → same job. Free.
  Comparison is scoped to one company because cross-company title similarity is meaningless:
  every firm has a Software Engineer.
- **Between 0.75 and 0.90** → genuinely ambiguous. This is the one permitted model call in
  the feature, batched across pairs, and the verdict is cached permanently in
  `dedup_verdict`. **If inference is unavailable the pair degrades to distinct**, because a
  duplicate shown twice is a small annoyance and a real job wrongly collapsed is a lost
  opportunity.
- **Below 0.75** → distinct. Free.

When two rows are the same job, **the board record wins and the aggregator becomes the
alias**, never the reverse. The board is the company's own statement; the aggregator is a
copy of unknown age.

### Closure

**Absence from a successful board refresh is evidence the job closed.** After a board fetch
succeeds, any non-closed job from that board absent from the response gets `closed_at` set.

Three conditions on that rule, each of which prevents a way of destroying the index:

**Only on success.** A fetch that failed, timed out, or returned an empty list where it
previously returned hundreds is not evidence of anything. Treating a 500 as "every job at
this company closed" would empty the feed on a provider outage.

**Only for that board.** A Greenhouse refresh says nothing about Ashby jobs.

**Aggregator rows expire instead.** The Muse does not enumerate a complete set, so absence
proves nothing. Aggregator-only rows get a 14-day expiry and are marked unverified. Story 32.

A canonical board row that closes is closed **even if its aggregator alias is still listed**,
because the board is ground truth and the aggregator is the stale copy.

### Role family and seniority

Deterministic. Zero model calls, per ADR 0003 — this runs on every job on every refresh, and
a model call per job would be both slow and unaffordable.

Spike 001 is why this exists at all: under 3% of board postings are entry-level, and those
skew to non-software titles. Without this the feed is noise.

Both classifiers are keyword rules over the title, with **negative markers taking precedence
over positive ones**. `Senior Software Engineer` contains `Engineer`; the decision that
matters is `Senior`. Ambiguous roman numerals are handled explicitly — `Engineer II` is not
entry-level, `Engineer I` is.

A title that matches nothing is `other` and `unknown` rather than being forced into a
bucket, and the feed does not silently drop `unknown` — a student can widen to see it. A
classifier that quietly hides a real opportunity is worse than one that admits uncertainty.

### API contract

- `GET /api/v1/jobs` — filters `role_family`, `seniority`, `country`, `remote`, `q`,
  `company`, `posted_within_days`; paging `page`, `page_size`. Returns items, total, and
  which filters are active. Closed jobs are excluded unless explicitly requested.
- `GET /api/v1/jobs/{id}` — one job with its full description, its source, its verification
  state, and its aliases. 404 when closed and not requested.
- `GET /api/v1/sources` — per-source counts, `last_succeeded_at`, failure state. Story 28.
- `POST /cron/refresh-jobs` — exists from ticket 01, extended here. Outside `/api/v1`,
  secret required, 404 rather than 401, fails closed when unset.

The feed is **public**: browsing jobs needs no account. Story 1 is the first thing a visitor
should be able to do, and requiring registration to see whether the product has any jobs in
it is the reason people leave. Everything student-specific stays authenticated.

### DEMO_MODE

Per ADR 0010, the deployed instance runs in demo mode, so this must be the honest path.

**The substitution is at the transport, not the adapter.** Demo mode swaps in recorded
provider payloads; every adapter's normalisation, classification, dedup and closure logic
runs for real. This is a direct consequence of ticket 06: `FixtureResumeParser` returned a
finished result and skipped the risky code, which meant judges exercised a different program.
A `JobSource` fixture returning a tidy list of jobs would repeat that mistake exactly.

Recorded payloads are committed, and include the unhappy ones — a 500, a 404 board, a
timeout, and a malformed body — in the same commit as the adapter that handles them.

## Testing decisions

### What makes a good test here

Assert on what the index contains and what the feed returns, never on how a provider's JSON
was walked. A test that asserts an adapter called a particular parsing helper prevents
refactoring and proves nothing.

For each provider the interesting question is not "does it parse" but **"does it parse
something we did not write ourselves"** — which is why fixtures are recorded from the real
API rather than hand-authored to match the parser.

### Seams under test

- **Seam 1 — the inbound HTTP API** via `httpx.AsyncClient`. Unchanged from feature 01, and
  where the feed, filters and paging are tested.
- **Seam 3 — the outbound HTTP transport.** New, and the only new seam in this feature.
  Recorded provider responses go in here.
- **Seam 2 — `LLMClient`.** Reused, not extended. The ambiguous-band dedup call goes through
  the protocol feature 01 already established.

Three seams total after this feature. The fewer the better, and a `JobSource` protocol was
rejected specifically because it would have made four while hiding the code most likely to
be wrong.

### Priority

Full rigour, per the agreed reduction in test density:

- **Closure detection.** Every guard: failure is not closure, an empty response is not
  closure, one board's refresh does not close another's, a closed job stays retrievable, a
  reappearing job reopens.
- **Dedup.** Every band boundary, the ordered-pair cache, board-beats-aggregator, and
  degradation to distinct when inference is unavailable.
- **Classification.** Table-driven over **real titles taken from spike 001's output**,
  including the ones that made the filter necessary — Administrative Coordinator, and the
  Bengaluru and Mexico City postings. Negative markers beating positive ones.
- **Idempotence.** The same payload ingested twice produces one row.

Reduced: CRUD paths and individual error-message wording.

### Prior art

- `test_resume_variants.py` — fixtures that deliberately disagree, plus a test asserting they
  have not drifted into similarity. The provider payloads need the same guard, since four
  recorded fixtures that all happen to look alike would pass while testing nothing.
- `test_parse_evidence.py` — table-driven assertions over a pure function. The classifier
  tests take this shape.
- `conftest.py` — schema-per-test and direct session access for asserting on rows rather than
  through the API, which closure tests need.

## Further notes

**Quota.** The common path makes **zero** model calls. Only the 0.75–0.90 band costs
anything, it is batched, and the verdict is cached permanently. Given that ordinary
development exhausted a day's free quota in an afternoon, a design that called a model per
job would have been unusable regardless of its accuracy.

**The board token registry needs seeding**, from `kalil0321/ats-scrapers` (MIT, ~63k
companies) per ADR 0009. Licence verified during design. A curated subset is seeded rather
than all of it: the constraint is refresh time inside a free host's request window, not
storage.

**Why the index is shared rather than per-student**, restating ADR 0005 because it shapes
every module here: a per-student fetch would multiply provider requests by the user count,
make rate limits a function of popularity, and make dedup and closure impossible to reason
about since no student would see the whole picture.
