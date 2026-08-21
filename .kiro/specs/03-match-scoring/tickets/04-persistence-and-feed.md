# 04 — Persistence, invalidation, and the scored feed

**What to build:** `MatchScore` storage, lazy computation for the page being viewed, and a feed
ordered by score.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] `MatchScore` unique on `(student_id, job_id, resume_master_id)`
- [ ] **Including the resume version in the key is what makes invalidation free.** Uploading a new
      resume does not delete anything — the old rows simply stop matching the key, and remain correct
      about the resume they describe. Story 33
- [ ] Scores are computed for the twenty postings on the page being viewed, then persisted. A pass
      over 4,437 rows per student would be the most expensive operation in the application, almost
      all of it for postings nobody scrolls to
- [ ] A second render of the same page recomputes nothing
- [ ] The feed is ordered by score descending, with a stable tiebreak so pagination cannot show or
      skip a posting between pages — story 32
- [ ] **Nothing is hidden by score.** ADR 0003 rejected the 60-point cutoff, and it stays rejected:
      a student whose profile scores badly against every posting they want needs to see that pattern
- [ ] The feed still works for a student with no resume, ordered by recency, with the score area
      explaining what uploading would add rather than showing zeros — story 34
- [ ] Sub-scores are returned to the client, never only the total
- [ ] Score computation failing for one posting must not fail the page
- [ ] Requesting page 2 does not rescore page 1
- [ ] The public unauthenticated feed keeps working — scoring requires a student, and the index is
      shared and browsable without one
