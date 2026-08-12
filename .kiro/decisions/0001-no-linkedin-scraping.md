# 0001 — No LinkedIn scraping, and no third-party credentials

Status: Accepted · 2026-08-11

## Context

The original specification built two features on LinkdAPI, an unofficial LinkedIn
data API sold through RapidAPI:

- Feature 2, scanning recruiter posts for "we are hiring" signals
- Feature 4b, extracting a personalisation hook from a recruiter's recent posts

The hook was the product's stated differentiator, so this was not a peripheral
dependency.

Two facts settled it. LinkedIn's User Agreement §8.2 prohibits "bots, scrapers,
crawlers, or other unauthorized automated methods" for accessing the platform or
copying profiles. And LinkedIn enforces: it sued Proxycurl, a company selling
exactly this kind of API, which shut down in July 2025.

A later proposal was to collect the student's own LinkedIn username and password
and use their session to read recruiter data. This is worse, not better. It
requires storing credentials in a recoverable form, since they must be replayed —
so hashing is impossible and the store becomes a breach liability. It also puts
the student's account at risk of restriction, which is the one asset a job-seeker
cannot afford to lose.

GitHub was evaluated as a substitute for finding engineers at a target company.
It is also prohibited: GitHub's privacy statement forbids using information from
the service, "whether scraped, collected through our API, or obtained otherwise,"
for "sending unsolicited emails to users," naming recruiters and job boards
explicitly.

## Decision

No LinkedIn data, obtained by any means. Reachly never asks for a credential to a
service it does not own.

Personalisation is preserved by changing its source. The strongest hook available
turned out to be one Reachly can derive from data it already holds: because the
job index ingests entire company job boards, it knows every open role at a
company. "Four backend roles open alongside two SRE positions" is a specific,
verifiable, genuinely useful observation about a company's trajectory, and it
costs one SQL query. Secondary sources are the job description itself and, when
time allows, the company's own engineering blog.

## Rejected

**LinkdAPI, accepting the risk.** Hackathon Rule 11 requires authorisation for
every third-party resource and compliance with all applicable terms; Rule 26
lists intellectual property infringement and violation of applicable laws as
disqualification grounds. Building the differentiator on a terms violation risks
the entire submission.

**Collecting user LinkedIn credentials.** Rule 13 forbids exposing real
passwords; Rule 14 forbids credential-stealing functionality. A form that
collects a third-party password and replays it server-side is that, regardless of
intent.

**GitHub commit-email mining.** Explicitly prohibited for contact purposes by
GitHub's own terms.

## Consequences

- No `RecruiterPost` entity. Feature 2's third source is dropped.
- Hook generation depends on the job index being board-complete, which raises the
  value of ingesting whole boards rather than individual postings.
- Recruiter contact discovery needs a different mechanism entirely — see
  [0004](0004-draft-only-outreach.md).
- The constraint is recorded in `.kiro/steering/product.md` as a non-negotiable,
  so it holds for code generated later in the build.
