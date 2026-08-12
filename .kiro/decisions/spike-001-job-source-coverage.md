# Spike 001 — Job source coverage

Run 2026-08-11 · `python scripts/spike_sources.py` · raw output in `scripts/spike_results.json`

Purpose: validate the job sources before any feature depends on them. Run before
writing ingestion code, on the principle that a wrong source assumption is cheap to
fix on day one and expensive on day eight.

## Results

| Source | Boards reachable | Jobs | Full description | Entry-level | Entry % |
|---|---|---|---|---|---|
| Greenhouse | 10 / 10 | 2,571 | yes, median 6,731 chars | 73 | **2.8%** |
| Ashby | 6 / 6 | 1,139 | yes, median 6,585 chars | 28 | **2.5%** |
| Lever | 3 / 20 slugs | 471 | yes | — | — |
| The Muse (`level=Entry Level`) | n/a, keyless | 60 | yes, median 6,885 chars | 58 | **96.7%** |

## The finding that matters

**Entry-level density on company job boards is under 3%.**

Greenhouse returned 2,571 jobs across ten well-known employers. Seventy-three were
plausibly open to a new graduate. Worse, the entry-level results skew away from the
target user on two axes at once:

- **Geography.** Samples were dominated by Bengaluru, Mexico City, Singapore,
  Tokyo, and Dublin rather than the US and Canada.
- **Role family.** "Administrative Coordinator", "Operations Associate", "Credit
  Risk Operations Associate" — entry-level, and irrelevant to a software graduate.

The Muse, filtered with `level=Entry Level`, inverts this: 96.7% entry-level, full
description text, no API key, and US locations throughout the sample (Redmond WA,
Lockhart TX, El Segundo CA).

## Consequences for the design

**The experience-fit filter is load-bearing, not a scoring refinement.** ADR 0003
weights experience fit at 30 points on the reasoning that "3+ years required" is
what kills a new graduate's application. The spike shows it is stronger than that:
it is the mechanism that converts a 2.8% signal into a usable feed. Without it, the
student sees 2,571 jobs of which 2,498 are a waste of their time.

Two point five percent of a large number is still worth having. Scaled to a warm set
of ~300 boards, the same rate yields roughly two thousand entry-level roles with
full description text, direct employer apply links, and the closure detection that
only whole-board reads make possible. The boards stay — they need aggressive
filtering, not replacement.

**A role-family filter is needed alongside seniority filtering.** Seniority alone
admits "Administrative Coordinator" for a software candidate. Filtering must consider
the student's target role, not only their experience level. This was not in the
original specification.

**Location must be a hard filter, as ADR 0003 already specified.** The spike
confirms why: the entry-level slice of a global board is disproportionately outside
North America.

**The Muse is promoted from breadth to co-primary.** Q19 treated it as filler for
non-tech roles. On this evidence it is the highest-density source of exactly the
roles Reachly exists to surface, and it is keyless — so it also carries the
`DEMO_MODE`-free path for judges.

**Board slugs cannot be guessed.** Twelve of twenty plausible Lever slugs returned
404 while `matchgroup` (83 jobs) and `leverdemo` (388) succeeded, confirming the
adapter is correct and the guesses were not. This validates ADR 0005's decision to
seed the token registry from the MIT-licensed public dataset rather than curating by
hand.

## Method caveats

The entry-level classifier is a regex over titles and description bodies, checking
seniority markers, graduate markers, and the lowest stated years-of-experience
requirement. It produced at least one visible false positive ("Performance Modeling
Engineer ~2"). Percentages are therefore indicative, not precise — but the gap
between 2.8% and 96.7% is far too large to be an artefact of classifier noise.

The North-America location share is likely understated for The Muse, since several
entries use "Flexible / Remote" phrasing the location regex does not match.
