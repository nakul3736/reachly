# Issue tracker

Issues for this repo are **local markdown files inside `.kiro/specs/`**.

Not `.scratch/`, which is the usual default: that directory is conventionally
gitignored, and hackathon Rule 15 requires judges to be able to inspect this
project's specs. Keeping them under `.kiro/specs/` means one artefact satisfies both
the workflow and the rule. See ADR 0009.

## Layout

One directory per feature, numbered in build order:

```
.kiro/specs/
  01-profile-and-resume/
    requirements.md      problem, solution, user stories
    design.md            implementation decisions, seams, testing decisions
    tickets/
      01-<slug>.md        one file per ticket, numbered in dependency order
      02-<slug>.md
  02-job-index/
    ...
```

## Ticket format

```markdown
# NN — Title

**What to build:** the end-to-end behaviour this makes work, from the student's
perspective — not a layer-by-layer implementation list.

**Blocked by:** ticket numbers that gate this one, or "None — can start immediately".

**Status:** ready-for-agent | in-progress | done

- [ ] Acceptance criterion
- [ ] Acceptance criterion
```

Tickets are **tracer bullets**: each cuts a narrow but complete path through every
layer it touches, and each is demoable on its own. A ticket that only adds a
database table is a horizontal slice and is wrong.

Avoid file paths and code snippets in tickets — they go stale within a day. The
exception is a schema or type shape that encodes a decision more precisely than
prose can.

## Working the frontier

A ticket is startable when every ticket it declares as a blocker is done. Work the
frontier, not the numbering.

## Triage

Not in use. The `triage` skill is not installed, so there is no label vocabulary.
Ticket state is the `Status` line.

## Pull requests

Not in use. Solo repo, work lands on `main`. Merge requests are a team coordination
device and would be ceremony here.

## If this moves to GitHub Issues

A public GitHub repository is required for submission regardless, so the remote will
exist. If tickets move to Issues later, publish in dependency order so blocking edges
can reference real issue numbers, and use GitHub's native sub-issue relationship for
the edges. The specs stay in `.kiro/specs/` either way.
