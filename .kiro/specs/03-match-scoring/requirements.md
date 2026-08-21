# Feature 03 — Deterministic match scoring

## The problem this solves

A student looking at 4,437 postings has no way to tell which ones are worth an evening. The
filters from feature 02 answer "could I apply?" — not senior, right country, right field. They
cannot answer "should I apply to this one before that one?", and 170 graduate-suitable software
postings in the US and Canada is still more than anyone reads carefully.

The failure this addresses is specific and measured. Spike 001 found that entry-level density on
company boards is 2.8%, and that most postings surviving the filters still ask for experience the
student does not have. A posting titled `Software Engineer` with "5+ years required" in the body
passes every filter Reachly has, because the title says nothing. That is the single most common
reason a new graduate's application is discarded, and it is invisible until the student has already
spent the evening.

## What it is

Every posting carries a score out of 100, decomposed into four parts the student can read:

| Component | Weight | Source |
|---|---|---|
| Skill overlap | 40 | Profile skills against skills found in the description |
| Experience fit | 30 | Years required, parsed from title and body, against the student's |
| Keyword similarity | 20 | BM25 over description text |
| Freshness | 10 | Age of the posting |

Location is not scored. ADR 0003: a job in the wrong country is not a weak match, it is not a
match, and it is already excluded by a filter.

## Non-negotiables carried in from steering

- **No model calls anywhere in this feature.** ADR 0003 and non-negotiable 5. Matching is pure
  Python, so the same posting scores the same on two loads and the reason is inspectable.
- **The score is never shown as a bare number.** The four components are always visible. A single
  opaque figure is the thing the product exists to replace.
- **Nothing is hidden by score.** The original specification cut everything below 60. That hides
  the most useful signal a student can receive — that their profile is weak against the roles they
  are targeting. Everything is shown, ordered, with the reason attached.
- **Inferred is never presented as confirmed.** A score computed from a description that never
  stated a requirement must say so rather than implying the requirement was met.

## User stories

**Story 30** — As a student, I see why a posting scored what it did, broken into four parts, so I
can tell a genuine mismatch from a description that simply did not mention my skills.

**Story 31** — As a student, I see when a posting requires more experience than I have, before I
spend an evening on it. This is the component with the most weight after skills, because it is the
most common silent rejection.

**Story 32** — As a student, the feed is ordered by score rather than date, so the first screen is
the one worth reading.

**Story 33** — As a student, uploading a new resume re-scores everything, because a score derived
from a resume I have replaced is a lie about my current profile.

**Story 34** — As a student with no resume uploaded, the feed still works and tells me what
uploading one would add, rather than showing zeros or an error.

**Story 35** — As a student, I can tell the difference between "this posting does not need the
skills you have" and "this posting did not list its skills", because those call for different
decisions.

## Acceptance boundaries

- Scoring is computed lazily for the page being viewed, then persisted, so a feed render costs one
  pass over twenty postings rather than over the whole index.
- A stored score records which resume version produced it. A new active resume invalidates the
  scores derived from the old one rather than leaving them to drift.
- Skill extraction from descriptions uses a curated vocabulary, not a model, and the vocabulary is
  data rather than code so it can grow without a deploy.
- The experience parser must distinguish "3+ years required" from "3+ years preferred" and from "3
  years of study", and must not read a graduation year as a requirement.
- Scores are integers 0–100. Sub-scores are integers within their own weight, so they sum to the
  total without rounding drift.
