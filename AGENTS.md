# Reachly — agent guide

A job application pipeline for new graduates in the US and Canada. Finds relevant
openings, tailors a resume to a posting without inventing anything, finds who to
contact, drafts the outreach, and tracks what happened.

Read `CONTEXT.md` before working here — it carries the project's vocabulary, and
using it keeps names consistent across code, tests, and specs.

## Start here

| You need | Read |
|---|---|
| What the product is and what it refuses to do | `.kiro/steering/product.md` |
| Backend conventions | `.kiro/steering/backend.md` |
| Frontend conventions and the design direction | `.kiro/steering/frontend.md` |
| Testing conventions and priority order | `.kiro/steering/testing.md` |
| Why anything is the way it is | `.kiro/decisions/README.md` |
| Domain vocabulary | `CONTEXT.md` |

Several decisions reversed the original product specification. Read the relevant
ADR before proposing a change in that area — the rejected options are recorded
along with the reasoning, so a reversal that has already been considered will say so.

## Non-negotiables

Stated in full in `.kiro/steering/product.md`. In short: tailoring may never
introduce a claim absent from the student's resume; no LinkedIn data by any route
and no third-party credentials; Reachly drafts email but never sends it; an
inferred value is never displayed as a confirmed one; no model calls in the feed
path; no secrets committed; `.kiro/` is never gitignored.

## Development

```bash
docker compose up -d                              # Postgres on host port 55432
cd backend && .venv\Scripts\activate              # Windows
uvicorn app.main:app --reload                     # API on :8000
cd frontend && npm run dev                        # web on :5173
```

Tests run with `DEMO_MODE=true` and must never reach the network. `npm` on this
machine must be invoked as `npm.cmd` — PowerShell's execution policy blocks
`npm.ps1`.

## Agent skills

### Issue tracker

Local markdown, one directory per feature under `.kiro/specs/`. See
`docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` at the repo root, with the decision log at
`.kiro/decisions/` rather than the default `docs/adr/`. See `docs/agents/domain.md`.

### Skills

Every skill used to build this project is vendored in `.kiro/skills/` — eight MIT
from mattpocock/skills, one Apache 2.0 from anthropics/skills. See
`.kiro/skills/ATTRIBUTION.md` and ADR 0009.

## Workflow

Grill the design, spec it, slice it into tickets, then implement test-first:

```
/to-spec      →  .kiro/specs/<NN>-<slug>/requirements.md + design.md
/to-tickets   →  .kiro/specs/<NN>-<slug>/tickets/NN-<slug>.md
/implement    →  drives /tdd at seams agreed in advance
/code-review  →  before commit
```

Seams are confirmed with the user before any test is written. No test at an
unconfirmed seam.
