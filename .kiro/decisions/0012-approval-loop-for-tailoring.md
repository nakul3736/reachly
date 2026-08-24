# 0012 — A suggestion is not a change: tailoring is an approval loop

**Status:** accepted
**Date:** 2026-08-23
**Supersedes nothing. Extends [0006](0006-evidence-locked-tailoring.md).**

## Context

ADR 0006 established that a tailored bullet may not introduce anything absent from its own source
bullet, and that the rule is enforced by a validator after generation rather than by asking a model
nicely. That holds. It answers *what may be written*.

It does not answer *what reaches the document*, and the first implementation answered that badly: a
rewrite that passed validation was simply applied. The student saw a finished tailored resume and could
read it, but the default was that generated text was in.

Two things were wrong with that, and neither is a matter of taste.

**A validated rewrite is not necessarily a rewrite the student wants.** The validator proves that no new
technology, number or name was introduced. It cannot prove that the sentence is *better*, that the
emphasis is right for this application, or that the phrasing sounds like the person sending it. A
graduate who is asked about a bullet in an interview has to own the sentence, and a sentence they never
agreed to is one they will fumble.

**Silence became consent for something sent under their name.** The document goes to an employer. Making
the absence of an objection into approval is the pattern that produces a student discovering in an
interview that their resume claimed an emphasis they would not have chosen. The cost lands entirely on
them, months later, in a room where they cannot correct it.

There is also a practical problem with applying rewrites automatically: the student has no way to push
back. Either they accept the model's judgement or they abandon the feature. A one-shot rewriter with no
argument is a worse tool than a slow human process, because at least the human process is theirs.

## Decision

**Nothing reaches the assembled document without explicit approval, and the student can argue with any
proposal as many times as they like.**

Concretely:

1. Every rewrite is a **proposal**. The document uses the student's own sentence unless they ticked the
   suggestion for that bullet. Empty is the meaningful default.
2. Approvals are stored as **bullet ids beside the payload**, not as a flag inside it, so regenerating
   the payload cannot silently carry a tick onto new text.
3. **A refused rewrite can never be approved.** There is nothing to approve: the text on offer is the
   student's own.
4. Feedback is **batched into one model call**. A student ticks three suggestions and writes instructions
   against two others; that is one request, not five.
5. **Every revision is validated against that bullet's own original**, never against the previous
   rewrite. This is the load-bearing part — see below.
6. Re-tailoring on the same upload **clears every approval**, because every sentence is newly generated.
   Re-uploading a resume carries an approval forward **only** when the new text is character-identical to
   what was approved.
7. The loop is **unbounded**. There is no revision limit, because a limit would be a limit on the
   student's ability to make their own resume say what they mean.

## Why validation targets the original, not the previous rewrite

This is the decision inside the decision, and getting it wrong would quietly destroy ADR 0006.

If each revision were compared with the draft before it, a claim could arrive **by degrees**. Pass one
adds nothing and passes. Pass two adds a mild quantifier — "several thousand records" — and passes,
because it is only compared with pass one. Pass three sharpens that into "12,000 records" and passes,
because it is only compared with pass two. No single step introduces a fabrication large enough to
catch, and the endpoint is a number the student never measured, on a resume they will be asked about.

Comparing every revision against the student's own sentence bounds total drift however many revisions are
requested. The tenth revision is judged exactly as strictly as the first.

The same reasoning governs the outreach email
([0013](0013-written-outreach-validated-afterwards.md)), where revisions are checked against the resume
rather than against the previous draft.

## Consequences

**Accepted:** more clicks. The student must tick each suggestion they want. This is the correct place to
spend their attention — it is a document about them, going to somebody deciding their future.

**Accepted:** a student may end up with a document that uses none of the suggestions. That is a success
condition, not a failure. They read four proposals, disagreed with all four, and sent their own writing.

**Gained:** the interface can state a guarantee that is actually true — nothing here was written by a
model unless you said so — and the assembled document is built server-side so a bullet cannot appear
twice or drift from the employer it belongs to.

**Cost discovered later:** three separate bugs, all reported from real use, came from approval state
being held in the wrong place — ticks vanishing when feedback was sent, applied suggestions still
labelled as waiting, and "start over" carrying approvals onto regenerated text. The lesson is that
approval state must have exactly one home, the query cache reading from the server, rather than being
reconstructed from whichever mutation ran most recently.

## Alternatives rejected

**Apply everything that validates, let the student edit afterwards.** The original behaviour. Rejected
because it makes silence consent, and because "edit afterwards" in practice means the student re-reads
four paragraphs looking for changes they did not make.

**Approve the whole tailoring in one action.** Simpler, and it collapses the useful distinction. A student
usually agrees with three suggestions and disagrees with one; a single accept/reject forces them to take
the bad one to get the good ones.

**Cap revisions at three.** Considered for quota reasons. Rejected: batching already means a revision
round is one call regardless of how many bullets it covers, and a cap would tell a student they have run
out of attempts at making their own resume say what they mean.
