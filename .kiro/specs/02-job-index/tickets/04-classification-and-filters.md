# 04 — Role family, seniority, location, and the filters that use them

**What to build:** the feed becomes usable. Every job is classified into a role family and a
seniority band, and its country and remote status are derived from its location text. The feed
gains filters for all four, so a graduating software student in Canada sees graduate software
roles in Canada.

This is the ticket that makes the difference between a product and a list. Spike 001 measured
under 3% entry-level density on company boards, skewing to Bengaluru and Mexico City and to
titles like Administrative Coordinator. Without this, the feed is technically correct and
practically useless.

**Blocked by:** 02 — needs jobs in the index to classify.

**Status:** ready-for-agent

- [ ] Role family and seniority are derived deterministically from the title. **No model
      call** — this runs on every job on every refresh, per ADR 0003
- [ ] **Negative markers beat positive ones.** `Senior Software Engineer` contains
      `Engineer`; the decision that matters is `Senior`. Same for Staff, Principal, Lead,
      Manager, Director, and an explicit years-of-experience requirement
- [ ] Roman numerals are handled explicitly: `Engineer I` is entry-level, `Engineer II` is
      not
- [ ] Country and remote status are derived from the location string, and `location_raw` is
      stored unchanged alongside them, so a wrong guess is visibly wrong rather than quietly
      authoritative
- [ ] A title matching no rule is `other` / `unknown` rather than forced into a bucket, and
      such jobs are reachable by widening the filter. A classifier that silently hides a real
      opportunity is worse than one that admits uncertainty
- [ ] Classifier tests are table-driven over **real titles from spike 001's output**,
      including the ones that made this ticket necessary
- [ ] `GET /api/v1/jobs` filters by `role_family`, `seniority`, `country`, `remote`, `q` and
      `company`, combinable
- [ ] Filters are a hard exclusion, not a re-ordering — location was settled as a hard filter
      in ADR 0003
- [ ] The response carries the total and the active filters, so the UI can show a count and
      explain an empty result
- [ ] Reclassification does not require re-fetching: classification runs over stored jobs, so
      a rule fix can be applied to the existing index
- [ ] The feed screen has working filter controls, shows how many jobs match, and names the
      filter responsible when nothing does
