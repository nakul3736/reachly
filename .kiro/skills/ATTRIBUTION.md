# Skills — provenance and attribution

## Written for this project

`.kiro/steering/` and `.kiro/decisions/` are original to Reachly. So are
`CONTEXT.md`, `AGENTS.md`, `docs/agents/`, and `scripts/spike_sources.py`.

## Vendored skills

Every skill used to build this project is committed here, installed through the
official `skills` CLI so that `skills-lock.json` records exact provenance. See
ADR 0009 for why.

### From [mattpocock/skills](https://github.com/mattpocock/skills) — MIT

Copyright (c) Matt Pocock. Copies are unmodified.

| Skill | What it was used for |
|---|---|
| `grilling` | Produced ADRs 0001–0008 through a multi-round design interview |
| `to-spec` | Turns settled decisions into a feature spec |
| `to-tickets` | Slices a spec into tracer-bullet tickets with blocking edges |
| `tdd` | Red-green loop at seams agreed in advance |
| `implement` | Drives `tdd`, then closes with `code-review` |
| `code-review` | Two-axis review before commit |
| `handoff` | Compacts a session when context runs long |
| `setup-matt-pocock-skills` | Configures the tracker and domain-doc layout the above read |

> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in the
> Software without restriction, including without limitation the rights to use, copy,
> modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
> and to permit persons to whom the Software is furnished to do so, subject to the
> following conditions: The above copyright notice and this permission notice shall
> be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
> INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
> PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
> HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
> OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
> SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### From [anthropics/skills](https://github.com/anthropics/skills) — Apache 2.0

| Skill | What it was used for |
|---|---|
| `frontend-design` | Produced the design direction in `.kiro/steering/frontend.md` — the receipt device, the mono-for-evidence typographic rule, and the palette |

The full licence is committed at `frontend-design/LICENSE.txt`, as Apache 2.0 §4(a)
requires. The copy is unmodified, so no §4(b) modification notice applies.

## Not vendored

Twenty-six further skills exist in `mattpocock/skills` and are not installed —
`domain-modeling`, `grill-with-docs`, `prototype`, `research`, `diagnosing-bugs`,
`codebase-design`, `triage`, `wayfinder` and others. They were considered and
skipped: the design interview and the decision records were done by hand,
research runs through sub-agents directly, and vendoring a skill implies it shaped
the work.
