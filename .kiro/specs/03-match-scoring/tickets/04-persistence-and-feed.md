# 04 — Persistence, invalidation, and the scored feed

**What to build:** `MatchScore` storage, lazy computation for the page being viewed, and a feed
ordered by score.

**Blocked by:** 03.

**Status:** done

- [x] `MatchScore` unique on `(student_id, job_id, resume_master_id)`
- [x] **Including the resume version in the key is what makes invalidation free.** Uploading a new
      resume does not delete anything — the old rows simply stop matching the key, and remain correct
      about the resume they describe. Story 33
- [x] Scores are computed for the twenty postings on the page being viewed, then persisted. A pass
      over 4,437 rows per student would be the most expensive operation in the application, almost
      all of it for postings nobody scrolls to
- [x] A second render of the same page recomputes nothing
- [x] The feed is ordered by score descending, with a stable tiebreak so pagination cannot show or
      skip a posting between pages — story 32
- [x] **Nothing is hidden by score.** ADR 0003 rejected the 60-point cutoff, and it stays rejected:
      a student whose profile scores badly against every posting they want needs to see that pattern
- [x] The feed still works for a student with no resume, ordered by recency, with the score area
      explaining what uploading would add rather than showing zeros — story 34
- [x] Sub-scores are returned to the client, never only the total
- [x] Score computation failing for one posting must not fail the page
- [x] Requesting page 2 does not rescore page 1
- [x] The public unauthenticated feed keeps working — scoring requires a student, and the index is
      shared and browsable without one

## Ranking is bounded, and that is a real tradeoff

Ordering by score and computing scores lazily are in direct tension: you cannot sort by a number
you have not calculated. Scoring the whole index per student was rejected in ADR 0003 and the
design brief, so the feed scores a bounded window of the filtered set and ranks that.

The bound is 200, chosen from the index rather than taste � the graduate software filter returns
about 170 postings, so in practice the entire relevant set is ranked and the ordering is genuinely
global. Beyond the bound the tail falls back to recency, and `ranked_within` is returned to the
client so the interface can say so rather than implying an ordering it does not have.

The tiebreak is the job id, not the total alone. Two postings on the same score could otherwise
swap between page 1 and page 2 of one session, showing the student one posting twice and hiding
another � a bug that needs two equal scores to appear and so would not show up in casual testing.
