# 06 — Deduplication

**What to build:** one row per real job. The same role listed on a company's Greenhouse board
and on The Muse collapses into a single feed entry, with the board's copy kept as the truth and
the aggregator's kept as an alias.

Without this, adding The Muse — the source that carries almost all the entry-level roles — makes
the feed worse rather than better, because it duplicates the board postings it syndicated.

**Full test rigour.** Every band boundary, and the failure mode in both directions: a duplicate
shown twice is an annoyance, a real job wrongly collapsed is an opportunity the student never
sees.

**Blocked by:** 03 — a duplicate requires two sources carrying the same job. And 05, because
closure and dedup interact and closure defines which record is authoritative.

**Status:** ready-for-agent

- [ ] Identity is a fingerprint over normalised company, title and location — **content-derived,
      never a provider id**, since no two providers share one
- [ ] Normalisation collapses whitespace, casefolds, and strips what differs between sources
      without changing meaning: `Inc.`, `Ltd`, trailing `(Remote)`, requisition numbers appended
      to titles
- [ ] Exact fingerprint match collapses, at no cost
- [ ] `rapidfuzz` token-set ratio above 0.90 collapses, **scoped to one company** — every firm
      has a Software Engineer, so cross-company title similarity is meaningless
- [ ] Below 0.75 stays distinct, at no cost
- [ ] The 0.75–0.90 band is the **one** permitted model call, **batched** across pairs rather
      than one call per pair
- [ ] The verdict is cached permanently, keyed on the **sorted** pair, so the same comparison
      cannot be paid for twice under opposite orderings
- [ ] **Inference unavailable degrades to distinct**, never to collapsed, and the feed keeps
      working. The cheap failure is chosen deliberately over the expensive one
- [ ] **The board record wins; the aggregator becomes the alias**, never the reverse. The board
      is the company's own statement, the aggregator a copy of unknown age
- [ ] A canonical job that closes is closed **even when its aggregator alias is still listed**,
      because the board is ground truth and the aggregator is the stale copy
- [ ] An alias never appears as its own feed row
- [ ] The job detail screen shows where else the posting was seen, so collapsing is visible
      rather than something the student has to trust
- [ ] Dedup runs over stored jobs, so a threshold change can be reapplied without re-fetching
      and without spending inference again on already-decided pairs
