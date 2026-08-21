# 0011 — Skill extraction is model-assisted, at refresh time

Status: Accepted · 2026-08-20 · Amends [0003](0003-deterministic-scoring-over-llm.md)

## Context

ADR 0003 settled that matching is deterministic and that the feed path contains no model calls. It
also assumed skill extraction from job descriptions would use a curated vocabulary alone.

Building against that assumption showed the weakness. A vocabulary only finds terms someone thought
to list. Real descriptions state requirements in ways no list anticipates — "comfortable owning a
service end to end", "experience with columnar stores", "familiarity with infrastructure as code" —
and a graduate reading a 12/40 skill score has no way to tell whether the posting genuinely wanted
different skills or whether Reachly simply failed to recognise the ones it named.

Skill overlap is 40% of the score. An extractor that under-reads descriptions makes the single
heaviest component quietly wrong, which is a failure this project has already had once: Gemini
returned 7 "skills" for a resume containing 46, and nothing broke until the numbers were counted by
hand.

## Decision

Skill extraction uses both, in a fixed order:

1. **The vocabulary always runs.** Deterministic, free, and the floor beneath everything else.
2. **The model runs once per posting, at refresh time**, and its output is unioned onto the
   vocabulary's. The result is stored on the job row with the timestamp that produced it.
3. **The feed path reads the stored set and calls nothing.** ADR 0003's rule survives intact: a
   render makes no model calls, and the same posting scores identically on two loads.

Enrichment is bounded to postings that survive the graduate filters. That is 170 postings out of
4,437, because the rest are senior, outside the US and Canada, or in fields the student is not
searching. Batched at roughly twenty descriptions per request, the whole relevant index costs about
nine calls rather than 222.

When inference is unavailable the score falls back to vocabulary-only and **says which basis it
used**, rather than presenting a thinner reading as the same answer.

## Why this is not a reversal of 0003

0003 rejected model scoring: one call per job per student per search, non-deterministic, unbounded.
Every one of those properties is absent here. This is one call per *posting*, ever, shared across
all students, cached, and off the render path. The score itself is still pure arithmetic over stored
values, and still inspectable term by term.

The line 0003 was really drawing is that **the student must never wait on a model, and must never
see a number they cannot interrogate**. Both hold.

## Consequences

- `jobs` carries `extracted_skills` and `skills_extracted_at`. The timestamp matters: it records
  whether a posting's skills predate a prompt change.
- A posting can be re-enriched without re-fetching it, the same property that made classification
  and dedup re-runnable.
- The refresh gets slower and can now fail in a new way. Enrichment failure must not fail the
  refresh, for the same reason a dead board must not: the rest of the run is still worth keeping.
- The interface distinguishes vocabulary-only from enriched, because a student comparing two scores
  deserves to know one was read more thoroughly than the other.
- Demo mode reads with the vocabulary and labels it, rather than serving a recorded enrichment.
  That was the original plan and it does not survive contact with the index: a fixture can only
  answer for postings someone recorded, and the deployed index holds thousands nobody has.
  Returning a recorded answer anyway would label a vocabulary-only reading as a model reading,
  which is the deception non-negotiable 4 forbids. The keyless path shows real vocabulary scores
  and says what produced them; a deployment with a key shows the enriched ones.
