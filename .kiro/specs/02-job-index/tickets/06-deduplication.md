# 06 â€” Deduplication

**What to build:** one row per real job. The same role listed on a company's Greenhouse board
and on The Muse collapses into a single feed entry, with the board's copy kept as the truth and
the aggregator's kept as an alias.

Without this, adding The Muse â€” the source that carries almost all the entry-level roles â€” makes
the feed worse rather than better, because it duplicates the board postings it syndicated.

**Full test rigour.** Every band boundary, and the failure mode in both directions: a duplicate
shown twice is an annoyance, a real job wrongly collapsed is an opportunity the student never
sees.

**Blocked by:** 03 â€” a duplicate requires two sources carrying the same job. And 05, because
closure and dedup interact and closure defines which record is authoritative.

**Status:** done

- [x] Identity is a fingerprint over normalised company, title and location â€” **content-derived,
      never a provider id**, since no two providers share one
- [x] Normalisation collapses whitespace, casefolds, and strips what differs between sources
      without changing meaning: `Inc.`, `Ltd`, trailing `(Remote)`, requisition numbers appended
      to titles
- [x] Exact fingerprint match collapses, at no cost
- [x] `rapidfuzz` token-set ratio above 0.90 collapses, **scoped to one company** â€” every firm
      has a Software Engineer, so cross-company title similarity is meaningless
- [x] Below 0.75 stays distinct, at no cost
- [x] The 0.75â€“0.90 band is the **one** permitted model call, **batched** across pairs rather
      than one call per pair
- [x] The verdict is cached permanently, keyed on the **sorted** pair, so the same comparison
      cannot be paid for twice under opposite orderings
- [x] **Inference unavailable degrades to distinct**, never to collapsed, and the feed keeps
      working. The cheap failure is chosen deliberately over the expensive one
- [x] **The board record wins; the aggregator becomes the alias**, never the reverse. The board
      is the company's own statement, the aggregator a copy of unknown age
- [x] A canonical job that closes is closed **even when its aggregator alias is still listed**,
      because the board is ground truth and the aggregator is the stale copy
- [x] An alias never appears as its own feed row
- [x] The job detail screen shows where else the posting was seen, so collapsing is visible
      rather than something the student has to trust
- [x] Dedup runs over stored jobs, so a threshold change can be reapplied without re-fetching
      and without spending inference again on already-decided pairs

## What it does on the real index

4,437 postings, 2,991 comparisons, **116 collapsed** — 107 by exact fingerprint, 9 by fuzzy match,
22 left undecided because no model was configured. 53 of the collapses are Muse copies folded into
the company board posting they syndicated, which is the case that justified the source.

Verified after the run: **0 cross-country collapses, 0 seniority mismatches, 0 location
mismatches, and 0 board records demoted to aliases of an aggregator.**

## Three bugs the real data found, none of which reasoning caught

The first version collapsed **219** postings, and six of the first twelve inspected were wrong.

**1. A country-only location was erased.** Stripping country words unconditionally turned `Canada`
and `United States` into the same empty string, so Stripe's `Credit Risk Strategy and Analytics` in
each country produced one identical fingerprint. For a product scoped to US and Canadian graduates
that hid half the affected postings. Country words are now dropped only when something else
remains.

**2. Titles matching did not mean locations matched.** Stripe lists `Director, Sales Compensation`
once for the US and again for Canada — identical company, identical title, two different jobs. A
location agreement threshold of 0.50 now gates every fuzzy collapse, set from measurement:
`Toronto, ON` against `Vancouver, BC` scores 0.33 and `San Francisco` against `New York` 0.19,
while `Toronto` against `Toronto, Ontario, Canada` scores 0.61 and `New York, NY` against `New
York` 0.80.

**3. A shared region made two towns look alike.** Masonicare's `Nursing Assistant` in Wallingford
and in Stonington merged because the `CT` they share pulled their similarity up. Two-letter codes
are now compared separately from place names — which also makes a *differing* code decisive, so
`Portland, OR` and `Portland, ME` never merge despite sharing a whole city name.

## Two departures from the ticket, both measured

**`token_sort_ratio`, not `token_set_ratio`.** The ticket specified token-set. Measuring it on
normalised titles showed it scores a subset as a perfect match: 100 for `data analyst` against
`senior data analyst`, 100 for `software engineer` against `software engineer machine learning`,
100 for `software engineer platform` against `platform engineer`. Each is two different openings,
and collapsing them is the failure the ticket itself calls the expensive one. `token_sort_ratio`
scores those 77, 67 and 79 while still scoring every genuine reorder 100.

**Ranks are compared as sets.** A title can hold two rank words — `Retail Sales Associate` uses
"associate" as the job, and `Senior Retail Sales Associate` adds a rank on top — so asking which
one is "the" rank has no correct answer. This replaced two earlier attempts: bucketing staff with
senior merged Discord's `Senior Data Scientist` with its `Staff Data Scientist`, and picking a
single most-specific rank got `Senior Retail Sales Associate` wrong.

## Generality, proven rather than assumed

`test_dedup_generality.py` asserts properties, never per-title answers — a table of expected
verdicts would encode whatever the current thresholds happen to produce and then defend it against
improvement. Its vocabulary is deliberately from healthcare, logistics, retail, hospitality,
education and construction, because The Muse's entry-level feed is mostly not software.

One test reads the module source and asserts **no seeded company or board token appears anywhere in
the executable code**, so a rule fitted to Stripe or Shopify fails the suite. Another guards the
holdout against drifting toward software vocabulary, which would quietly stop it proving anything.

Live probe against seven boards outside the seed set — Duolingo, Reddit, Discord, Coinbase, Ramp,
Vanta, Lever's demo — **1,055 postings, 0 suspect fuzzy collapses.** Of 30 exact-fingerprint
groups, the only two with differing text are `Front End Engineer`/`Front-End Engineer` and `Full
Stack Engineer`/`Full-Stack Engineer`, which are correct.

## The one model call, verified live

`test_dedup_live.py`, gated on `GEMINI_LIVE_TESTS=1` **and** `GEMINI_API_KEY`. Three ambiguous
pairs went out as **one** request and came back correctly discriminated: `Software Engineer,
Platform` against `Platform Engineer` returned same job, `Customer Success Associate` against
`Customer Success Manager` returned different. A second test confirms the model does not merge two
seniorities. Total live cost: two calls.