# 0005 — One shared job index, not per-student fetches

Status: Accepted · 2026-08-11

## Context

The original specification implied jobs were fetched for a student, after that
student uploaded a resume. Two things are wrong with that.

Jobs are identified by role and location, which are properties of a search, not of
a person. Fetching per student means the hundredth student searching "backend
engineer, Toronto" spends the same API budget as the first. On JSearch's free tier
of roughly 200 calls per month, that is exhausted immediately.

And coupling the fetch to resume upload is backwards: a resume is needed to
*score* a job, not to *find* one. It forces the student through a PDF upload before
they see any evidence the product works.

A third issue surfaced separately. The specification deduplicated by a hash of
title, company, and location — which treats "Software Engineer I" and "Software
Engineer 1" as different jobs, and the same role advertised remote and in-city as
two.

## Decision

One global `jobs` table, populated independently of any user. Anything
student-specific — scores, tailored versions, applications — lives in separate
tables keyed by student.

Sources are ingested in two tiers. Company job boards (Greenhouse, Lever, Ashby)
are primary: unauthenticated, unmetered, full description text, and the employer's
direct apply link. A registry of board tokens is seeded from an MIT-licensed public
dataset covering 63,000+ companies, filtered to the US and Canada. A warm set of
roughly 300 boards refreshes nightly so common searches are instant; anything else
is fetched lazily on a cache miss. One aggregator adds breadth for non-tech roles.

Deduplication normalises before comparing: lowercase, strip seniority markers and
parentheticals, canonicalise company legal suffixes, then exact match, then a
fuzzy token-set ratio above 0.9 within the same company. Pairs in the ambiguous
0.75–0.90 band are the one permitted model call in this path — batched, and the
verdict cached against the pair permanently.

**When a board and an aggregator describe the same job, the board record wins**
and the aggregator becomes an alias on the same row. This gives the student full
description text and the employer's real apply URL rather than a redirect.

Because whole boards are re-read nightly, a posting's disappearance is ground
truth that it closed. `closed_at` is set on absence, the row is kept for
application history, and it leaves the feed. Aggregator rows have no such signal
and get a 14-day expiry with freshness marked as unverified.

## Rejected

**Per-student fetching.** Multiplies API cost by user count for identical data.

**Requiring a resume before showing jobs.** Delays first value behind the
highest-friction step in onboarding.

**Naive hash deduplication.** Fails on the most common real variations.

**Eager scoring of the whole index on resume upload.** Scoring is free of API
cost but not free of time; scoring thousands of rows the student will never scroll
to makes first run slow for no benefit. Scores are computed for the visible page
and then persisted.

**Bulk open-data job exports.** Permissively licensed and periodic, so stale. A
stale index undercuts the freshness claim that motivates the board-first strategy.

## Consequences

- Onboarding is role and location first; the feed works before any upload. Resume
  upload then unlocks scores, gaps, and tailoring.
- Uploading a new resume creates a new `ResumeMaster` version and invalidates
  `MatchScore` rows referencing the previous one. Versions are never overwritten,
  so a bad parse cannot destroy a good one.
- Job descriptions are cached but never republished as Reachly's own; the
  employer's apply link and source attribution always travel with the row.
- Board-completeness per company is what makes the hook in
  [0001](0001-no-linkedin-scraping.md) possible, so the two decisions reinforce
  each other.
