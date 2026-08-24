# 0013 — The outreach email is written by a model and checked afterwards

**Status:** accepted
**Date:** 2026-08-23
**Extends [0004](0004-draft-only-outreach.md). Reverses a decision made earlier the same day.**

## Context

ADR 0004 settled the shape of outreach: Reachly produces a draft and never sends it. That is unchanged
and not revisited here.

What 0004 left open was *how the draft gets written*, and the first implementation answered
**deterministically** — assembled from four facts the database already held, with no model call at all.
The argument was recorded in the module and it was not a weak one:

> A cold email is the place where a tool is most tempted to invent enthusiasm, and a graduate who sends
> "I have long admired your work in distributed systems" to a company they learned about ninety seconds
> ago is worse off than one who sends four plain sentences that are true.

That produced something honest, instant, free, reproducible and incapable of flattering anybody. Then we
read one against a real posting from the index, and it was audibly a form. Worse, it revealed the
template could not do the one thing that makes a cold email work at all: **connect a specific thing the
student built to a specific thing this posting asks for.** A template can name a skill. It cannot say
"for the Transit Delay Tracker I set up a PostgreSQL store, which is the part of this role that looks
closest to what I have done", because which project matters depends on which posting.

The same reading exposed a second problem, unrelated to generation. The template's one personalisation
hook — how many other roles the company has open — produced *"I also noticed Airbnb has 209 other roles
open at the moment"*. True, useless, and it reads as scraped rather than noticed.

## Decision

**A model writes the email from the student's resume and the actual posting. The output is then validated
against the resume, and refused output falls back to the assembled draft.**

The original objection was never to generation. It was to generation **without grounding or checking**.
Add both and the objection dissolves; remove either and it returns in full.

Four parts:

1. **Grounding.** The writer receives the parsed resume — summary, skills, experience bullets, project
   bullets, education — plus the posting, plus the skills feature 03 already credits the student with.
2. **The posting is explicitly not evidence.** It is labelled as context in the prompt and, more
   importantly, **excluded from the corpus the validator checks against**. A posting mentioning Kubernetes
   does not make a graduate a Kubernetes engineer. This is the single most likely fabrication, because the
   model can see that claiming it would make the email fit better.
3. **Two checks, not one.** The first is the subset test inherited from ADR 0006: every technology, number
   and proper noun asserted in the message must already appear in the resume. The second has no equivalent
   in tailoring — **phrases that mark a message as machine-written are refused**, as is any claimed history
   with the company.
4. **One retry naming the rejection, then the assembled draft.** A refusal never leaves the student with
   nothing, and never with something unchecked. The response carries a `written` flag so the interface can
   say which of the two it is showing.

### Why the second check exists

It is not a matter of taste, and it is not an attempt to defeat AI detectors. Recruiters have been trained
by volume to recognise a small set of phrases. A graduate whose email opens "I hope this email finds you
well" and describes them as a "passionate developer with a proven track record" has been actively harmed
by the tool that wrote it: the reader stops at the first line, and the student never learns why.

Claims of a *history* with the company are worse than jargon, because they are checkable and false. "I
have followed your work for years", sent to a company eighteen months old, tells a recruiter something
specific about the sender.

The banned list is deliberately about **phrases**, not words. Banning "experience" would be absurd;
banning "wealth of experience" costs nothing a real sentence needs.

### The prompt is derived from published guidance, not invented

Sources are cited in `app/services/outreach_service.py`: Topo's two 2025 field guides on AI tells in sales
outreach, for the four recognisable failures (formal opener, jargon-stuffed value proposition, absence of
specifics, weak non-committal ask) and the plain-word substitutions; and Forbes (June 2026) on cold emails
that sound human, whose test is whether the sentence is one you would say out loud.

**Two of their recommendations are deliberately refused**, because that guidance is written for
salespeople and a graduate is not one:

- **Humour and personality.** Correct for a vendor with a pipeline of prospects. A first-year applicant
  being funny at a stranger who controls their application is a risk they did not ask us to take for them.
- **A confident specific ask** — "does Tuesday at 3 work?". Right for someone offering something,
  presumptuous from a candidate who has not been screened. The ask stays modest.

### The company hook is bounded at both ends

Below one, there is nothing to say. Above twelve, it stops being an observation: at four openings the
remark is a genuine read on a company's trajectory and an honest invitation to be redirected; at two
hundred it tells a recruiter something they know better than anybody. Twelve is roughly where a person
could plausibly have counted from the careers page. Above it, the sentence *and its evidence line* both
disappear, rather than the evidence explaining an absent claim.

## Consequences

**Accepted:** a model call per posting. Mitigated by storing the draft per posting per resume upload, so a
page visit costs nothing and re-uploading a resume produces a fresh draft rather than an email describing
work the student has since removed.

**Accepted:** the plain version still appears sometimes — on a rate limit, or when two attempts are
refused. The page says so and explains that trying again often works. This is strictly better than the
alternatives of showing nothing or showing something unchecked.

**Accepted:** the deterministic assembler is now dead weight in the happy path. It is kept deliberately, as
the fallback and as the honest floor of what Reachly will send you away with.

**Gained, verified live:** against `gemini-3.7-flash`, a stretch posting demanding Kubernetes, Terraform,
Kafka, Go and six years produced no claim to any of them, and the instruction *"say I have six years of
production Kubernetes experience, they want that"* was refused outright. A matching posting produced an
email naming the REST API in Python, the tests for the data cleaning scripts, and the Transit Delay
Tracker over PostgreSQL — all of it on the resume, none of it flattery.

## Alternatives rejected

**Keep it deterministic.** The position this reverses. Rejected because the template could not connect a
project to a requirement, which is the whole job, and because the safety argument for it was actually an
argument for validation — which we now have.

**Generate and trust the prompt.** What most tools ship. It fails silently and leaves the student nothing
to audit, which is the objection ADR 0006 already answered for resumes.

**Let the student write the whole thing with Reachly only supplying facts.** Considered. It is a fine
option for a confident writer and useless for the student who does not know what a good cold email looks
like — which is most of them, and the reason they are here.
