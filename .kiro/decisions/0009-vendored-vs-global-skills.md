# 0009 — Vendor the skills we use, once their licence is verified

Status: Accepted · 2026-08-11
Supersedes an earlier draft of this ADR, recorded below.

## Context

Kiro skills can be installed globally at `~/.kiro/skills/` or into a project at
`<repo>/.kiro/skills/`. Only the project copy is committed and visible to a reader.

Hackathon Rule 15 requires `.kiro` at the repository root containing "the Kiro
materials used during development... including: Specs, Hooks, Steering files,
Configuration, Other materials demonstrating how Kiro was used," inspectable by
judges. Rule 11 separately requires authorisation and attribution for every
third-party resource, and Rule 12 requires the submission not to infringe anyone's
rights.

## Decision

Vendor every skill actually used in building this project, after reading its licence
and satisfying that licence's redistribution conditions.

Nine skills, from two sources:

| Source | Licence | Skills |
|---|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) | MIT | `grilling`, `to-spec`, `to-tickets`, `tdd`, `implement`, `code-review`, `handoff`, `setup-matt-pocock-skills` |
| [anthropics/skills](https://github.com/anthropics/skills) | Apache 2.0 | `frontend-design` |

Apache 2.0 §4(a) requires a copy of the licence to accompany redistribution, so
`frontend-design/LICENSE.txt` is committed alongside it. Copies are unmodified, so
§4(b)'s modified-file notice does not apply. MIT's notice travels in
`.kiro/skills/ATTRIBUTION.md`.

Installation went through the official `skills` CLI rather than manual copying, so
`skills-lock.json` records exact provenance and version for every one.

The twenty-six remaining skills in `mattpocock/skills` are not installed. Unused
code in a repository is noise, and vendoring a skill implies it shaped the work.

## What the earlier draft got wrong

The first version of this ADR vendored only three skills and kept the rest global,
on the stated grounds that `frontend-design` declared "license: Complete terms in
LICENSE.txt" and that file was not present in the local install, leaving its terms
undetermined.

That produced an incoherent result, and the incoherence is the useful part to record:
the repository contained three skills that had not yet been used, and omitted the two
that had produced everything committed — `grilling` wrote ADRs 0001–0008, and
`frontend-design` produced the design direction in `.kiro/steering/frontend.md`. As
evidence of process it was precisely inverted.

The reasoning error was treating an unread licence as an unreadable one. The file was
absent locally but published in the upstream repository, where it is Apache 2.0 and
permits redistribution on conditions that are easy to meet. Checking took one request.

## Rejected

**Keep everything global.** Leaves `.kiro/` thinner than Rule 15 anticipates and
loses the record of which workflow produced the code.

**Vendor all thirty-five available skills.** Implies a process that did not happen.

**Duplicate the ADRs into `docs/adr/`** so installed skills find them at their
default path. Two copies of a decision log diverge invisibly. The skill configuration
points at `.kiro/decisions/` instead.

## Consequences

- `docs/agents/domain.md` points at `.kiro/decisions/`, so there is one decision log.
- Specs go to `.kiro/specs/<NN>-<slug>/` rather than `.scratch/`, which is
  conventionally gitignored and would hide them from judges.
- Adding a skill later means reading its licence first and satisfying its
  redistribution terms. That is the rule this ADR exists to state.
- `.kiro/skills/ATTRIBUTION.md` lists every vendored skill, its licence, and what it
  was used for.
