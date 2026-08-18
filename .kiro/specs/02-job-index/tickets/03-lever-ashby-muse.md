# 03 — Lever, Ashby and The Muse

**What to build:** the index draws from all four sources. Three more adapters behind the same
transport seam, each with a recorded payload. The Muse matters most: spike 001 measured 96.7%
entry-level density against under 3% on company boards, so it is where the roles this product
exists for actually are.

**Blocked by:** 02 — the transport seam, normalisation and upsert path.

**Status:** ready-for-agent

- [ ] Lever adapter against the verified shape
      `api.lever.co/v0/postings/{token}?mode=json`
- [ ] Ashby adapter against `api.ashbyhq.com/posting-api/job-board/{token}`
- [ ] The Muse adapter against `themuse.com/api/public/jobs?page=N&level=Entry%20Level`,
      keyless, paginated
- [ ] Muse rows are stored as **unverified** — it is an aggregator, so its postings are a
      copy of unknown age and the feed must not present them as company-confirmed
- [ ] Each adapter has a payload recorded from the live API, and the four recorded payloads
      are asserted to differ structurally, the way the resume variants are. Four fixtures
      that happen to look alike would pass while testing nothing
- [ ] A source returning zero results is distinguishable from a source that failed
- [ ] Muse pagination stops at a bounded page count rather than following pages until the
      API disagrees
- [ ] Each source's contribution is visible in `GET /api/v1/sources`, so an adapter that
      silently stops returning anything is noticed
- [ ] The feed shows jobs from all four sources, and the source is visible on every row
