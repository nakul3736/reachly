# 04 â€” Role family, seniority, location, and the filters that use them

**What to build:** the feed becomes usable. Every job is classified into a role family and a
seniority band, and its country and remote status are derived from its location text. The feed
gains filters for all four, so a graduating software student in Canada sees graduate software
roles in Canada.

This is the ticket that makes the difference between a product and a list. Spike 001 measured
under 3% entry-level density on company boards, skewing to Bengaluru and Mexico City and to
titles like Administrative Coordinator. Without this, the feed is technically correct and
practically useless.

**Blocked by:** 02 â€” needs jobs in the index to classify.

**Status:** done

- [x] Role family and seniority are derived deterministically from the title. **No model
      call** â€” this runs on every job on every refresh, per ADR 0003
- [x] **Negative markers beat positive ones.** `Senior Software Engineer` contains
      `Engineer`; the decision that matters is `Senior`. Same for Staff, Principal, Lead,
      Manager, Director, and an explicit years-of-experience requirement
- [x] Roman numerals are handled explicitly: `Engineer I` is entry-level, `Engineer II` is
      not
- [x] Country and remote status are derived from the location string, and `location_raw` is
      stored unchanged alongside them, so a wrong guess is visibly wrong rather than quietly
      authoritative
- [x] A title matching no rule is `other` / `unknown` rather than forced into a bucket, and
      such jobs are reachable by widening the filter. A classifier that silently hides a real
      opportunity is worse than one that admits uncertainty
- [x] Classifier tests are table-driven over **real titles from spike 001's output**,
      including the ones that made this ticket necessary
- [x] `GET /api/v1/jobs` filters by `role_family`, `seniority`, `country`, `remote`, `q` and
      `company`, combinable
- [x] Filters are a hard exclusion, not a re-ordering â€” location was settled as a hard filter
      in ADR 0003
- [x] The response carries the total and the active filters, so the UI can show a count and
      explain an empty result
- [x] Reclassification does not require re-fetching: classification runs over stored jobs, so
      a rule fix can be applied to the existing index
- [x] The feed screen has working filter controls, shows how many jobs match, and names the
      filter responsible when nothing does

## What it did to the feed

Measured on the 2,586 real postings ingested from ten live company boards:

| Filter | Postings |
|---|---|
| unfiltered | 2,586 |
| open to graduates | 700 |
| plus technical roles | 196 |
| plus US or Canada | **85** |
| explicitly entry level only | **14** |

That last row is the reason the primary control is "open to graduates" rather than "entry
level". Only 14 of 2,586 titles carry an explicit entry-level marker, so a filter offering just
those returns almost nothing and reads as broken. Excluding the 1,886 that are definitely too
senior, and keeping the 686 unmarked, is the query that actually helps.

## Notes from implementation

**Two traps came from the real data, and neither would have been invented.** `Sr.` appears 205
times against `Senior` 513, so a rule matching only the long spelling leaves two hundred senior
roles looking unmarked — straight into a graduate's feed. And `CA` is ambiguous in the data we
actually have: `CA-Toronto` is Canada because these boards prefix an ISO country code, while
`San Francisco, CA` is California because American addresses suffix a state code. A two-letter
match puts every Bay Area job in the wrong country.

Recognising a bare country code is therefore deliberately asymmetric: `US` is accepted alone
because no state is abbreviated that way, and Canada is recognised only by provinces, cities
and the `CA-` prefix.

**Overfitting was tested for rather than assumed.** The rules were written while looking at ten
seeded boards, which is exactly how keyword lists become a description of one sample. Running
the classifier against 268 postings from Duolingo, Reddit and Discord — none seeded, none
consulted — gave a 12% `other` rate against 15% on the boards it was written against, with the
family distribution holding rather than collapsing. It also exposed two genuine vocabulary
gaps, both general rather than specific: `sourcer` is standard recruiting vocabulary, and
`editor` is publishing.

`test_classification_generality.py` keeps that honest. It asserts properties rather than
per-title answers — that families stay spread, that `other` does not absorb everything, that
nothing is labelled entry without an entry word present — because a table of expected answers
per title would be the same overfitting one level up. It includes a test guarding the holdout
set itself against drifting into similarity with the seeded data, the way the resume variants
do.

**The known weak point** is the Canadian city list, which is finite and will miss Saskatoon and
Kitchener. The robust rules are the country prefix, province codes and province names; the city
list is a fallback for bare `Toronto`, which the real data does contain. Expanding it further
would be the overfitting this ticket was careful to avoid.

**Classification runs over stored jobs, not only during fetch.** A corrected rule can be
reapplied to the whole index without asking ten providers for 2,586 postings again — on a free
host that is an hour, and a burst of requests we should not make to fix our own bug. Verified
by reclassifying all 2,586 in place.