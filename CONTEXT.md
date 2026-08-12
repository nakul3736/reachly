# CONTEXT

Reachly's vocabulary. These are the words used in code, tests, specs, commits, and
conversation. Using them precisely is what stops a five-word idea being re-explained
in twenty every session.

## The user

**Student** — a new graduate or final-year student, 0–1 years experience, in the US
or Canada. Has a resume, a target role, and a city. Has no network.

**Target role** — the job family a student is looking for. Distinct from a job
title: "backend engineer" is a target role, "Software Engineer II, Payments" is a
title. Needed because filtering on seniority alone surfaces entry-level roles in the
wrong field entirely — see spike 001.

## Resumes

**Master resume** — the student's real resume, parsed once into structured JSON and
never overwritten. The single source of truth about what the student has actually
done. Stored as `ResumeMaster`, versioned rather than replaced, so a bad parse can
never destroy a good one.

**Tailored version** — a per-job derivative of the master resume. Rephrases,
reorders, and re-emphasises. Never adds. Stored as `ResumeVersion`.

**Provenance map** — the record attached to a tailored version mapping each
rewritten bullet back to the span of the master resume it derives from. What makes
"evidence-locked" inspectable rather than merely asserted.

**Provenance validator** — the check that runs after generation and before the
student ever sees the output. Extracts entities, technologies, and numerals from
source and result, and rejects any bullet whose result set is not a subset of its
source set. **Fabrication** is what it exists to prevent: any claim in a tailored
version absent from the master resume.

## Jobs

**Job index** — the single shared table of postings, populated independently of any
student. Not per-student: one fetch of a company's board serves everyone.

**Board token** — a company's slug on an ATS, the `shopify` in
`boards.greenhouse.io/shopify`. There is no global search across boards, so tokens
are held in a **token registry** seeded from a public dataset. Tokens cannot be
guessed — twelve of twenty plausible Lever slugs 404'd in spike 001.

**Warm set** — the roughly 300 boards refreshed nightly so common searches are
instant. **Lazy fill** is the on-demand fetch for anything outside it.

**Dedup key** — the normalised identity of a posting: lowercased, seniority markers
and parentheticals stripped, company legal suffixes canonicalised. Two postings
sharing one are the same job.

**Canonical job** — the row that survives deduplication. When a company board and an
aggregator describe the same job the board wins, and the aggregator becomes an
**alias** on the canonical row. This is why the student gets full description text
and the employer's real apply link rather than a redirect.

**Closure detection** — treating a posting's absence from a board refresh as ground
truth that it closed, recorded as `closed_at`. Only whole-board reads make this
possible, and it is what lets Reachly avoid **ghost jobs**: postings still listed
after the role is filled.

## Matching

**Match score** — 0–100, computed in pure Python with no model call, from four
weighted **components**: skill overlap (40), **experience fit** (30), keyword
similarity (20), and freshness (10). Location is a **hard filter**, not a component —
a job in the wrong city is not a weak match, it is not a match.

**Experience fit** — how the years-of-experience requirement parsed from a posting
compares to the student's. Load-bearing rather than decorative: entry-level density
on company boards is under 3%, so this is the mechanism that turns a large index
into a usable feed.

**Skill gap** — a requirement in a posting that the student's master resume does not
evidence. Read-only output of tailoring, paired with a resource link from a curated
map. Not a roadmap; there is no progress tracking and no hours estimate.

## Outreach

**Contact waterfall** — the ordered attempt across contact providers, stopping at
the first hit, then falling through to **pattern inference**: constructing a
candidate address from a domain's detected pattern and verifying it.

**Confirmed** and **inferred** — the two states any value can be in, and they are
never displayed as one another. A verified address is confirmed; a pattern-inferred
one is inferred, and labelled so. The same distinction applies to posting freshness.

**Hook** — the specific, verifiable observation that opens a draft. Derived from the
job index itself: because whole boards are ingested, Reachly knows every open role at
a company, so "four backend roles open alongside two SRE positions" is available from
one SQL query. Never sourced from LinkedIn.

**Draft** — what Reachly produces. It does not send. The student sends, from their
own address, having read what goes out under their name.

## Interface

**Receipt** — the signature UI device. Any assertion the product makes carries a
small monospace annotation of where it came from: a score shows its components, a
tailored bullet shows its source span, an address shows provider and confidence.
Monospace for machine evidence, humanist sans for prose.

## Operating

**DEMO_MODE** — the mode in which every external call is served from a recorded
**fixture**, so the project runs with no API keys. Not test scaffolding: it is the
path judges use, and the reason tests never touch the network.

**Spine** — the five features that ship: profile and resume parse, job index,
tailoring with gaps and export, outreach drafting, tracker with follow-ups.
Everything else was cut deliberately.
