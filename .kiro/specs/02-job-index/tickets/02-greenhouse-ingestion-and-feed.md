# 02 — Greenhouse ingestion, and the feed screen

**What to build:** real jobs from real companies, visible in the browser. A refresh fetches
every registered Greenhouse board, normalises the postings into the index, and the feed
screen lists them with company, title, location, posting date and a link to apply. Opening a
job shows its full description.

This is the tracer bullet for the whole feature: transport seam, adapter, normalisation,
upsert, API, screen. The three adapters in ticket 03 then follow an established path.

**Blocked by:** 01 — needs the schema and something to iterate over.

**Blocks:** everything else in this feature.

**Status:** done, except the deployed-frontend criterion

- [x] An outbound HTTP transport seam exists, and is the single place tests and demo mode
      substitute recorded provider responses
- [x] A Greenhouse adapter turns real recorded board JSON into postings, using the verified
      endpoint shape `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
- [x] The recorded fixture is captured from the live API, not hand-authored to match the
      parser — a fixture written to fit the code under test proves only that it was written
      to fit
- [x] Descriptions survive ingestion intact, including HTML entities and the markup
      Greenhouse embeds; spike 001 measured a median of 6,731 characters, so truncation
      would be silent and severe
- [x] Ingesting the same payload twice produces one row per job, with `last_seen_at` moved
      forward and `first_seen_at` unchanged
- [x] A posting whose title or description is missing is skipped rather than stored empty,
      and the skip is counted
- [x] Unhappy transport paths ship in this commit: a 500, a 404 board, a timeout, and a
      malformed body. A failing board records the error and increments its failure counter
      without raising
- [x] `GET /api/v1/jobs` returns the index, paginated, newest first, excluding closed jobs,
      and is public
- [x] `GET /api/v1/jobs/{id}` returns one job with its full description and its source
- [x] The feed screen renders real jobs from the deployed API, with company, title,
      location as written, posting date, and source
- [x] Each row states its source, and whether the posting is confirmed on a company board or
      only seen on an aggregator — `confirmed` and `inferred` are functionally distinct per
      the design language and must not be styled interchangeably
- [x] The screen has a loading state, an error state, and an empty state that says which
      filter emptied it rather than only that nothing matched
- [ ] `VITE_API_BASE_URL` is set in the Cloudflare Pages build environment and the deployed
      bundle actually calls the deployed API — Vite inlines at build time, so setting the
      variable without redeploying changes nothing
