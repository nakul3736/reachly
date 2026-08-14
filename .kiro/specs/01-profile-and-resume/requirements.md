# 01 — Profile and master resume

Status: ready-for-agent
Produced by `/to-spec` · seams confirmed with the developer before writing

## Problem statement

A student arrives with a resume PDF and nothing else. Before Reachly can score a job,
tailor anything, or draft an email, it has to know two things: who the student is, and
what they have actually done.

The second is the hard part. A resume PDF is unstructured text in an arbitrary layout —
two columns, tables, unlabelled sections, inconsistent dates. Nothing downstream can
work against that. Tailoring needs to know which bullets belong to which role. Scoring
needs a skill list. The provenance validator needs the exact original text to compare
generated output against, or the central promise in ADR 0006 cannot be enforced.

Replacing a resume must also be safe. If a new upload parses badly, the previous
version has to survive — and any match score computed from the old version must not
silently be presented as applying to the new one.

## Solution

A student registers, says what they are looking for, and uploads a resume once. Reachly
parses it into a structured **master resume**, which becomes the source of truth about
their real experience.

Uploading again creates a new version rather than overwriting. Exactly one version is
active at a time. The student sees what was parsed, so a bad parse is visible rather
than quietly wrong.

Nothing here touches jobs. Per ADR 0005 the **job index** is populated independently, so
a student can browse before uploading anything — the resume unlocks scoring and
tailoring, not discovery.

## User stories

**Account**

1. As a student, I want to register with an email and password, so that my resume and
   applications persist between visits.
2. As a student, I want to be told when my email is already registered, so that I try
   logging in instead of assuming registration is broken.
3. As a student, I want a stated minimum password length, so that the account holding
   my employment history is not trivially guessable.
4. As a student, I want to stay logged in for a working session, so that I am not
   re-authenticating while job hunting.
5. As a student, I want a failed login to not reveal whether the email exists, so that
   my presence on the site is not disclosed to someone guessing addresses.
6. As a student, I want my password stored so that it cannot be recovered from a
   database leak, so that a breach here does not compromise my other accounts.
7. As a judge evaluating this project, I want a pre-seeded account with documented
   credentials, so that I can evaluate the product without registering.
8. As a judge, I want to enter the product without signing up at all, so that I can see
   it working within seconds of opening the link.

**Profile**

9. As a student, I want to state my **target role**, so that Reachly filters for the kind
   of work I want rather than every entry-level opening — spike 001 showed seniority
   filtering alone surfaces administrative roles to software candidates.
10. As a student, I want to give more than one location, so that I can search my city
    and remote roles together.
11. As a student, I want to state my years of experience, so that postings demanding
    more than I have are scored down rather than wasting my time.
12. As a student, I want to list skills myself, so that scoring works before I have
    uploaded a resume.
13. As a student, I want to edit my profile whenever, so that I can widen a search that
    returned too little.
14. As a student, I want to see my profile as Reachly understands it, so that a wrong
    field is visible rather than quietly distorting results.
15. As a student, I want to be told which profile fields are required before results
    will be useful, so that I am not left with an empty feed and no explanation.

**Resume upload**

16. As a student, I want to upload my resume as a PDF, so that I do not retype what I
    already have.
17. As a student, I want a non-PDF or oversized file rejected immediately, so that I am
    not waiting on a request that cannot succeed.
18. As a student, I want a file that claims to be a PDF but is not to be rejected, so
    that a renamed file fails honestly rather than half-parsing.
19. As a student, I want a clear explanation when my PDF cannot be read — a scanned
    image with no text layer, or an encrypted file — with a suggestion of what to do, so
    that I know the problem is my file and not the site.
20. As a student, I want to see the structured parse — summary, roles, bullets, skills,
    education — so that I can judge whether it understood me.
21. As a student, I want to upload a corrected resume without losing the previous one,
    so that a bad parse is recoverable.
22. As a student, I want exactly one resume treated as current, so that I am never
    unsure which version a tailored document came from.
23. As a student, I want my original PDF retained, so that the parse can be redone later
    without me re-uploading.
24. As a student, I want to see when each version was uploaded, so that I can tell them
    apart.
25. As a student, I want the upload to work with no API keys configured, so that the
    project can be run and evaluated by someone who has none.

**Isolation**

26. As a student, I want my resume unreadable by any other account, so that my
    employment history is not exposed.
27. As a student, I want an unauthenticated request rejected, so that my data is not
    reachable by guessing a URL.
28. As a student, I want a request carrying a tampered or expired token rejected, so
    that a stale session cannot be replayed.

## Out of scope

- **Email verification and password reset.** Columns and an `EmailSender` interface exist
  as seams with no implementation. Per ADR 0004 Reachly has no email sender, so building
  these means reintroducing that dependency. Documented as a known limitation.
- **OAuth or social login.**
- **Resume editing inside Reachly.** The master resume reflects the uploaded document.
  It is not an editor.
- **DOCX or plain-text upload.** PDF only.
- **Re-parsing an existing version on demand.** The original bytes are retained so this
  becomes possible later; no endpoint for it now.
- **Multiple profiles per account.**
- **Any job, scoring, tailoring, outreach, or tracker behaviour.** Later specs. This one
  deliberately ends at a parsed master resume.
