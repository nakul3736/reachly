# 0004 — Reachly drafts outreach; the student sends it

Status: Accepted · 2026-08-11

## Context

The original specification sent cold emails through Resend, and located recruiter
addresses through Hunter.io using the company name.

Three problems. Resend's free tier cannot reach arbitrary recipients without a
verified custom domain — the default sending domain only delivers to the account
owner's own address — and caps at 100 per day. Hunter's free tier is 50 credits
per month for the entire application, not per user. And the chain from "a job at
this company" to "a named person with an inbox" was never specified: Hunter
returns addresses at a domain, not the owner of a particular requisition.

There is also a legal dimension. The hackathon host is a UK company under the law
of England and Wales. UK PECR does not require consent for email to corporate
subscribers, but UK GDPR still applies where an address identifies an individual:
a lawful basis is needed, transparency obligations attach within a month of
obtaining data from a third party, and the ICO's guidance is explicit that data
being publicly available does not imply agreement to its use for direct
marketing. An application that sends on a user's behalf, at scale, to addresses it
found for them, owns that exposure.

## Decision

Reachly does not send email. It produces a finished draft and hands it over —
copy to clipboard, or open in the student's own mail client. The student is the
sender, from their own address, having read what goes out under their name.

Contact discovery is a waterfall behind one `ContactFinder` interface, tried in
order of free allowance and stopping at the first hit: Hunter (50/month, filtered
to HR and recruiting, returning names with positions), then Prospeo (~100/month),
then Tomba (25–75/month). All three miss frequently, so the fall-through matters
more than the finders: Hunter's domain search also returns the detected address
pattern for a domain, which produces a candidate address that is then verified
against MailboxLayer's free tier of 1,000 verifications per month — the largest
free allowance in the entire stack, and therefore the leg that carries most
traffic.

Confidence is always shown. A guess is labelled a guess, because a bounced email
costs the student a real opportunity. The employer's own apply link is always
present as a path that cannot fail, and the student can override with an address
they found themselves.

## Rejected

**Sending via Resend.** Requires domain verification, caps at 100/day, and makes
Reachly the sender of unsolicited mail to third parties.

**"Send me a copy" to the student's own address.** Considered as a way to keep a
real email integration for the demo. Dropped as ceremony: it demonstrates an
integration the product does not need, in exchange for a dependency and a domain.

**Hunter alone as the contact path.** 50 credits per month for all users is a wall
reached on the first day of real use. Designing around it builds in a limit that
looks like a bug.

**Asking the student to find the address themselves.** Rejected on product
grounds. It breaks the single-surface promise, and it offloads work at exactly the
point where the student is most likely to abandon the flow.

## Consequences

- No email-sending dependency, one fewer API key for judges, and no send quota.
- `Contact` carries `provider`, `confidence`, and `verified_at`, because the
  interface must never present an inferred address as a confirmed one.
- Reachly retains no third-party contact data beyond what the student is actively
  working on, which keeps the data-protection surface small.
- The interface being a waterfall means adding a provider is roughly thirty lines,
  so free allowances can be pooled as they are found.
