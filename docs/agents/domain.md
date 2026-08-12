# Domain docs

Layout: **single-context**. One `CONTEXT.md` at the repo root, one decision log.

## Locations

| Doc | Path | Note |
|---|---|---|
| Glossary | `CONTEXT.md` | repo root |
| Decision log | `.kiro/decisions/` | **not** the default `docs/adr/` |

The decision log sits in `.kiro/decisions/` because hackathon Rule 15 requires the
`.kiro` directory to hold the materials judges inspect. Duplicating it into
`docs/adr/` would create two copies that diverge invisibly. See ADR 0009.

## Consumer rules

**Read `CONTEXT.md` before working in this repo.** It is short and it is the
vocabulary used in code, tests, specs, and commit messages. Names in code should be
the names in the glossary — `ResumeMaster`, `provenance_map`, `dedup_key`,
`closed_at`, `warm set` — so a reader does not have to translate.

**Read the relevant ADR before changing behaviour in its area.** Several decisions
reversed the original product specification, and each records what was rejected and
why. A proposal that has already been considered and declined will say so, with the
reasoning — which is faster than rediscovering it.

The index is `.kiro/decisions/README.md`.

## Producer rules

**Add a glossary entry** when a term starts carrying weight — when it is doing work
in more than one place and the short form is clearer than the long one. Do not add
entries for terms used once.

**Write an ADR** when a decision closes off an alternative someone might reasonably
propose later. The test is whether a future reader would otherwise ask "why not just
do X?" — if so, X belongs in the Rejected section.

Format is `NNNN-kebab-title.md` with Context, Decision, Rejected, Consequences.
Rejected is not optional; it is usually the most useful section.

Spike reports live alongside the ADRs as `spike-NNN-<slug>.md` when empirical
findings drive a decision. Spike 001 is the example: it measured entry-level density
across job sources and changed the source strategy before any code depended on it.
