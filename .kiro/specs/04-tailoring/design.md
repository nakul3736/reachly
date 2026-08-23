# Feature 04 — Design

## Shape

```
domain/claims.py              what a piece of text asserts: technologies, numbers, proper nouns
domain/tailoring.py           the validator: is this rewrite supported by its source?
services/tailoring_service.py generate, validate, retry once, fall back
models/resume_version.py      the tailored output and its provenance map
api/tailoring.py              POST /api/v1/jobs/{id}/tailor
```

## The validator is the feature

Everything else is plumbing. The rule from ADR 0006: extract the claims from the source bullet and
from the generated bullet, and require the generated set to be a **subset** of the source set.

A claim is anything a reader would take as a fact about the student:

| Claim kind | Why it is checked |
|---|---|
| Technologies | The commonest fabrication. A posting wants Kubernetes, so the rewrite adds it. |
| Numbers | "Reduced latency by 40%" is unfalsifiable and unforgettable in an interview. |
| Proper nouns | Employers, products, institutions. Adding one invents a relationship. |

Ordinary words are deliberately **not** checked. Rephrasing is the entire permitted transformation,
so requiring word-level containment would reject every useful rewrite and leave the feature doing
nothing while appearing to work — the failure mode this project has hit twice.

**Validation is per bullet, against that bullet's own source.** Comparing against the whole resume
would let a rewrite of a retail job import Python from a different job's bullet and pass. The claim
would be true of the student and false of that role, which is exactly the kind of error an
interviewer finds.

## What happens when a bullet fails

Generate → validate → **retry once** with the rejected claims named in the prompt → validate again
→ on second failure, **keep the original bullet unchanged** and record why.

Falling back rather than dropping the bullet: the student's own sentence is always safe, so a
failed rewrite costs polish and never costs content. Recording the reason is what makes story 43
possible — the interface can say which bullets it left alone and what it caught.

## Numbers need normalising before comparison

`40%`, `40 percent` and `forty percent` are one claim written three ways, and a rewrite legitimately
changes the form. Comparing surfaces would reject a correct rewrite; comparing normalised values
accepts the rephrasing and still catches an invented `45%`.

Years are excluded from the numeric check. Dates are stored as written (feature 01) and a rewrite
that keeps `2024–2025` is not asserting a new quantity.

## Storage

`ResumeVersion` holds the tailored bullets, the job it was tailored for, and a provenance map from
each tailored bullet id to the source bullet id plus the validator's verdict. Stored rather than
regenerated because a student needs to see what they actually sent, and because a second render must
not cost another model call.

## The gap list

Requirements the posting states and the resume does not support. This is the honest home for
everything tailoring is forbidden from inventing — it comes free from feature 03's
`missing_skills`, which is already computed and already shown on the job. Read-only, per the scope
boundary: a skill roadmap with progress state is out.

## Rejected

**Prompt instruction alone.** What every competitor ships. Fails silently and gives the student
nothing to audit.

**Rewriting whole sections rather than bullets.** A section-level rewrite has no source span to
validate against, so the guarantee evaporates precisely where it matters.

**Blocking the whole tailoring when one bullet fails.** Punishes the student for the model's
mistake, when their own bullet was always an acceptable answer.
