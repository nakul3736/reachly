# Decision log

Numbered records of the decisions that shaped Reachly, written when the decision
was made rather than reconstructed afterwards.

Each record states what was decided, what was rejected, and why. Several of these
reversed the original product specification — those reversals are the point. The
rejected options are kept deliberately, because the reasoning is the useful part.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-no-linkedin-scraping.md) | No LinkedIn scraping, and no third-party credentials | Accepted |
| [0002](0002-kiro-is-not-the-inference-backend.md) | Kiro builds Reachly; it does not run inside it | Accepted |
| [0003](0003-deterministic-scoring-over-llm.md) | Job matching is deterministic, not model-driven | Accepted |
| [0004](0004-draft-only-outreach.md) | Reachly drafts outreach; the student sends it | Accepted |
| [0005](0005-shared-job-index.md) | One shared job index, not per-student fetches | Accepted |
| [0006](0006-evidence-locked-tailoring.md) | Tailoring is provenance-checked and cannot invent experience | Accepted |
| [0007](0007-external-scheduler.md) | The daily job runs from an external trigger | Accepted |
| [0008](0008-hosting-for-a-judged-window.md) | Hosting chosen for uptime across a fixed judging window | Accepted |
| [0009](0009-vendored-vs-global-skills.md) | Vendor the skills we use, once their licence is verified | Accepted |
| [0010](0010-demo-mode-is-the-deployed-default.md) | The deployed app runs in demo mode, on a pinned model | Accepted |

## Spikes

Empirical findings that drove a decision.

| Spike | Question | Outcome |
|---|---|---|
| [001](spike-001-job-source-coverage.md) | Do the job sources actually carry entry-level roles? | Entry-level density on company boards is under 3%; the experience-fit filter is load-bearing and a role-family filter was added |
| [002](spike-002-real-resume-structure.md) | Is `pdfplumber.extract_text()` enough to structure a resume? | Yes for text, but wrapped bullets carry no marker on the continuation line — line-based splitting would have broken provenance silently. Geometry-based parsing rejected as layout-specific |

## Format

```
# NNNN — Title
Status / Date
## Context      — what forced the decision
## Decision     — what we chose
## Rejected     — what we did not choose, and why
## Consequences — what this commits us to
```
