# 0010 — The deployed app runs in demo mode, on a pinned model

**Status:** Accepted
**Date:** 2026-08-18
**Supersedes nothing. Extends:** ADR 0002 (Reachly carries its own inference provider).

## Context

Reachly needs one model call per resume upload to structure extracted text, and will need
another per tailored resume. ADR 0002 settled *whose* model: Gemini's free tier, because
Kiro built this project and does not run inside it.

What ADR 0002 did not settle is what the **deployed, judged** instance does. Two facts
arrived on the same day and decided it between them.

**The free tier has a finite daily quota, and it is easy to exhaust.** Two runs of the
live parser test suite plus a handful of manual parses — roughly thirty large completions
— returned `429 RESOURCE_EXHAUSTED` for the rest of the day. Nobody was being careless with
a production budget; that was ordinary development.

**A pinned model went stale inside a few months.** `gemini-2.5-flash` now answers 404 with
"no longer available to new users". Separately, `gemini-flash-latest` — the obvious fix —
returned 503 in the same minute that two pinned models returned 200.

The judged window is Aug 24 to Sep 5. A judge who opens the app, uploads a resume and
receives "the writing service is busy" has seen the product fail, and will not know or care
that a quota reset would fix it tomorrow.

## Decision

**The deployed instance runs with `DEMO_MODE=true`.** Judges consume no quota and cannot
meet a rate limit.

This is only defensible because of what demo mode now is. It runs the **real** parser:
pdfplumber extraction actually executes, the evidence check actually runs, identifiers are
actually derived. Only the single inference call is served from a recorded response. An
earlier version returned a finished `ParsedResume` and skipped all of that — which meant
judges were exercising different code from production, and any bug in the evidence check
would have been invisible to them. That version is deleted.

**The model is pinned to a specific version, never to a moving alias.** `gemini-3.6-flash`
today. An alias that changes during judging changes the product during judging.

**Provider refusals are logged with the provider's own message.** Retries apply only to
conditions that can change — rate limits and server errors. A refused request is never
retried, because a bad key or a retired model refuses just as firmly the second time.

## Consequences

Good:

- Quota exhaustion cannot affect a judge. The failure mode with the worst timing is
  removed rather than mitigated.
- No API key is required to run Reachly at all, which makes the testing instructions
  short and the project genuinely reproducible by a stranger.
- Demo mode is the default rather than a special path, so it is exercised by every test
  run instead of being the branch nobody looks at.

Bad, and accepted:

- **A judge does not see live inference.** The recorded response for an unrecognised
  resume is the primary fixture's, so uploading a stranger's PDF produces a visibly thin
  result rather than a rich one — because the evidence check drops everything it cannot
  find in their text. That is the honest failure, but it is still a worse first impression
  than a real parse.
- Mitigation: the demo video is filmed with `DEMO_MODE=false` against the real model, and
  says so on screen. The live parser tests are the standing evidence that the real path
  works — they passed across three distinct layouts and a real resume.
- Anyone wanting live inference sets `DEMO_MODE=false` and supplies a key. Documented in
  `.env.example` and the README.

## Alternatives rejected

**Deploy with `DEMO_MODE=false` and hope the quota holds.** One enthusiastic judge, or one
scripted crawler, exhausts it. The cost of being wrong is a broken submission during the
only window that matters.

**Pay for a higher tier.** Rejected: the project should be reproducible by a student with
no budget, which is the same reason ADR 0002 chose a free tier in the first place.

**Cache aggressively and serve live until quota runs out, then fall back to fixtures.**
Rejected as the worst option: the product would behave differently for different judges
with nothing on screen explaining why, and a fixture served as though it were a real parse
is precisely the deception ADR 0006 exists to prevent.
