# Product steering

## What Reachly is

A job application pipeline for new graduates in the US and Canada, 0–1 years
experience. It finds relevant openings, tailors a resume to a specific posting
without inventing anything, finds who to contact, drafts the outreach, and tracks
what happened.

## Who it is for

Someone twenty-two years old with a resume, a target role, a city, and no network.
They have sent forty applications and heard nothing, and they do not know why. They
are anxious and short on time. They do not know what an ATS is.

Design and copy decisions follow from that reader. Explain, do not reassure.
Specific beats encouraging.

## The thesis

The job search is defined by invisible rejection. Reachly's job is to make the
invisible legible — why a job matched, what changed in a resume and where it came
from, whether an address is confirmed or guessed, whether a posting is still open.

Every assertion the product makes carries its evidence.

## Non-negotiables

These are settled. Code that violates one is wrong regardless of how well it works.

1. **No fabricated resume content.** Tailoring may rephrase, reorder, and
   re-emphasise. It may never introduce a technology, employer, metric, or claim
   absent from the student's master resume. Enforced by a validator, not a prompt.
   See ADR 0006.

2. **No LinkedIn data, by any route.** No scrapers, no unofficial APIs, no
   third-party credentials. Reachly never asks for a password to a service it does
   not own. See ADR 0001.

3. **Reachly does not send email.** It drafts; the student sends. See ADR 0004.

4. **Inferred is never displayed as confirmed.** Addresses, freshness, and scores
   carry their provenance and confidence. See ADR 0004.

5. **No model calls in the feed path.** Matching is deterministic and inspectable.
   See ADR 0003.

6. **No secrets in the repository.** Configuration ships as `.env.example` with
   safe placeholders.

7. **`.kiro/` is committed.** Never add it to `.gitignore`.

## Scope boundaries

Not building: auto-apply, portfolio sites, mobile apps, multi-student or agency
modes, paid job board integrations, learning progress tracking.

The skill *gap list* is in scope as a read-only output of tailoring. A skill
roadmap with progress state is not.

## Voice

Plain and specific. Active voice. Sentence case. A control names what happens when
used, and keeps that name through the flow — "Copy email" produces "Copied".

Errors state what happened and what to do, and do not apologise. Empty states say
what to do next.

Never claim certainty the system does not have. "Address pattern inferred, not
verified" is better than silence, and much better than presenting a guess as fact.
