# Feature 04 — Evidence-locked tailoring

## The problem this solves

A graduate is told to tailor their resume to each posting. Doing it by hand takes an hour and they
have forty applications to send. Every tool that offers to do it for them will, when asked to make
a resume fit a job, quietly add the things the job wanted — a framework the student has never
used, a metric nobody measured, a team size nobody counted.

That is not a rough edge, it is a career risk. A fabricated line survives until an interviewer asks
about it, and then the student is a liar in a room they worked months to reach. They cannot audit
the output either, because they have no idea which parts came from their own resume and which the
model supplied.

## What it is

Reachly rewrites bullets to use the posting's vocabulary, and **cannot** introduce anything absent
from the student's master resume — enforced by a validator that runs after generation and before
anything is displayed, not by asking the model nicely.

Every tailored bullet shows the original beside it. Every change is attributable.

## Non-negotiables carried in from steering

- **No fabricated content, enforced by a validator rather than a prompt.** Non-negotiable 1 and
  ADR 0006. Prompt instruction alone is what every competitor does; it fails silently and gives the
  student nothing to check.
- **The permitted transformation is rephrasing, reordering and emphasis.** Nothing else.
- **A requirement the student does not meet belongs in the gap list, not in the resume.**
- **Failure falls back to the original bullet, unchanged.** A tailoring that cannot be verified is
  not shown; the student's own words are always a safe answer.

## User stories

**Story 40** — As a student, I get a version of my resume rewritten for one specific posting, in
seconds rather than an hour.

**Story 41** — As a student, I see every bullet that changed with its original beside it, so I can
approve each one rather than trusting the whole.

**Story 42** — As a student, I am certain nothing was invented, because the product tells me what
it checked and shows me the evidence rather than asking me to trust it.

**Story 43** — As a student, when a rewrite fails its check I still get a usable resume — my
original bullet — and I am told that bullet was left alone and why.

**Story 44** — As a student, I see which of the posting's requirements my resume genuinely does not
support, stated as a gap rather than silently written in.

**Story 45** — As a student, I can copy the tailored text out, because the point is to use it.

## Acceptance boundaries

- Generation is one request for the whole resume, not one per bullet: a resume has fifteen to
  thirty bullets and per-bullet calls would be the most expensive operation in the product.
- The validator is deterministic and runs on every bullet, including on the retry.
- Validation compares the generated bullet against **its own source bullet**, not against the whole
  resume. Otherwise a rewrite could import a technology from an unrelated job and pass.
- Bullet identity is content-derived, as established in feature 01 — never positional.
- A tailored version is stored, so a student can return to what they sent.
- Demo mode produces a real tailoring from recorded responses, because this is the feature judges
  will look at hardest.
