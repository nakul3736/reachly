# 0003 — Job matching is deterministic, not model-driven

Status: Accepted · 2026-08-11

## Context

The original specification had a model score every job 0–100 against the student
profile, showing only those above 60. It also defined the match score a second
time, and differently, as "keyword overlap, tone fit, experience level alignment."

Both the cost and the contradiction are problems. Scoring every job with a model
is one API call per job per student — a feed of 200 jobs is 200 calls, per user,
per search. That is unaffordable on a free tier, slow enough to break the stated
ten-minute promise, and non-deterministic, so the same job can score differently
on two loads with nothing to explain the difference.

## Decision

The feed contains no model calls at all. Matching is pure Python:

| Component | Weight | Method |
|---|---|---|
| Skill overlap | 40 | Profile skills against skills extracted from the description |
| Experience fit | 30 | Required years parsed from title and body, against the student |
| Keyword similarity | 20 | BM25 over description text |
| Freshness | 10 | Age of the posting |

Location is a hard filter, not a scored component — a job in the wrong city is
not a weak match, it is not a match.

Sub-scores are persisted and shown in the interface rather than rolled into an
opaque number.

Experience fit carries the second-heaviest weight deliberately. "3+ years
required" is the single most common reason a new graduate's application is
discarded, and it is cheap to detect with a regular expression. Surfacing it is
more useful to the target user than any refinement of the other components.

## Rejected

**Model scoring as primary.** Cost, latency, and non-determinism, as above.

**Model scoring as a re-rank of the top N.** Defensible, and still rejected for
v1: it reintroduces per-user cost and a variable the user cannot inspect, in
exchange for ranking improvements at positions the student will mostly not reach.

**Hiding jobs below a threshold.** The original 60-point cutoff hides the signal
that matters most — that the student's profile is weak against the roles they
want. Everything is shown, sorted, with the reason visible.

## Consequences

- Scores can be computed at feed render with no API budget, so they are computed
  lazily per page and then persisted. See `MatchScore` in the schema.
- `MatchScore` carries `resume_master_id`, so uploading a new resume invalidates
  the scores derived from the old one.
- Skill extraction from job descriptions needs a skills vocabulary. A curated
  list is used rather than a model, which also feeds the skill-gap resource map.
- The one place a model remains permitted in the matching path is deduplication
  tie-breaking — see [0005](0005-shared-job-index.md).
