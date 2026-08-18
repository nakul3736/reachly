# Testing steering

## Principles

Tests never touch the network. The suite runs with `DEMO_MODE=true` and every
external boundary served from fixtures. A test that fails on a plane is broken.

Test the decisions, not the framework. There is no value in asserting that FastAPI
routes or SQLAlchemy relationships work. There is high value in asserting that a
fabricated resume bullet is rejected.

## Priority order

Where time is limited, this is the order that matters:

1. **The provenance validator.** Adversarial cases, deliberately trying to smuggle
   claims past it: a technology absent from the source, an invented metric, a
   changed number, an employer that does not appear, a plausible-but-absent
   certification. This is the product's central promise — see ADR 0006.
2. **Deduplication and normalisation.** Table-driven cases from real titles:
   `Software Engineer I` against `Software Engineer 1`, seniority markers,
   parenthetical suffixes, company legal suffixes, remote versus city.
3. **Scoring.** Each component in isolation, then the weighted total. Experience-fit
   parsing gets its own cases: `3+ years`, `3-5 years`, `minimum 2 years`,
   `new grad`, and descriptions stating nothing.
4. **Closure detection.** A job absent from a board refresh is closed; a job still
   present is not; a failed board fetch closes nothing. That last case matters —
   a network error must never mark an entire company's jobs as closed.
5. **Auth and ownership.** One student cannot read another's resumes, scores, or
   applications.

## Conventions

pytest, `httpx.AsyncClient` against the ASGI app, transactional fixtures rolled
back per test. Factory helpers in `tests/factories.py` rather than fixture files
that grow into a second schema.

Parametrise over table-driven cases instead of writing near-identical tests.

Name tests as the behaviour asserted: `test_rejects_bullet_introducing_unseen_technology`,
not `test_validator_2`.

## Fixtures

Recorded provider responses live in `app/fixtures/` as JSON named for the provider
and scenario: `greenhouse_board_ok.json`, `hunter_domain_search_no_results.json`.

Record the unhappy paths too — an empty result, a rate-limit response, a malformed
payload. Those are the branches that break in front of a judge, and they are the
ones nobody records.

Adding an external call without a fixture in the same commit breaks `DEMO_MODE`,
which is the path judges use. Treat it as a build failure.


## Tests that need something the repository cannot contain

Some properties can only be established against a real external thing: a genuine resume,
or a real model. Both are used, and neither may break a fresh clone.

The pattern, used twice so far:

- **Gate on an environment variable and skip when it is absent**, with a reason naming the
  variable. `pytest -rs` then lists the skip and its reason, so a skipped test is never
  mistaken for a passing one.
  - `REACHLY_REAL_RESUME_PDF` — a real resume, read from **outside** the repository. This
    project is public and a real resume carries a name, phone number and email address.
  - `GEMINI_LIVE_TESTS=1` plus `GEMINI_API_KEY` — tests that call the real model. Two
    variables, so having a key configured for the application does not silently start
    spending quota on every test run.

- **Assert structural properties only** when the input is real personal data. Counts,
  shapes, whether a date appears in the source. Never a name, an employer, or a contact
  detail — asserting on real personal content puts it in the repository by another route.

- **Buy an expensive result once.** Cache a live parse per document per session and assert
  several properties against it. An earlier version called the model twice on one document
  to check two properties of the same parse, and exhausted a day's free quota in two runs.

- **Committed fixtures must disagree with each other.** One sample cannot show whether code
  is general. The three resume variants differ in heading case, bullet marker, date position
  and section order, and there is a test asserting they have not drifted into similarity —
  because if they had, they would keep passing while testing nothing.
