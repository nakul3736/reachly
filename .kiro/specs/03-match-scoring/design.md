# Feature 03 — Design

## Shape

```
domain/skills_vocabulary.py   curated skill terms + aliases, data not logic
domain/skill_extraction.py    description text -> set of canonical skills
domain/experience.py          description text -> ExperienceRequirement(years, basis)
domain/scoring.py             the four components and their arithmetic
services/scoring_service.py   lazy compute, persistence, invalidation
models/match_score.py         MatchScore, unique on (student, job, resume_master)
```

`domain/` stays free of the database and of FastAPI, as in every previous feature, so each
component can be tested against text rather than against fixtures.

## Why a vocabulary rather than a model

Skill extraction is the obvious place to reach for inference, and ADR 0003 rules it out for the
feed path. A curated vocabulary is not merely the cheap option — it is the inspectable one. When a
posting scores 12/40 on skills, the student can be shown exactly which terms matched and which did
not, and that list is the same on every load. A model would give a different set of skills for the
same description on two runs, and there would be nothing to show for the difference.

The vocabulary carries aliases, because the same skill has many surface forms: `JS`, `Javascript`,
`ECMAScript`. Aliases collapse to one canonical name so `JS` in a description matches `JavaScript`
on a resume. This is the same normalisation problem as dedup, and it is solved the same way — with
explicit rules over shapes, not a list of every company's phrasing.

**Skills are matched as whole terms, never substrings.** `R` must not match inside `React`, and
`Go` must not match inside `Django` or `Mongo`. This is the mistake that would make skill scores
look plausible while being nonsense, and it is the same word-boundary problem `role_family.py`
already solved for `I` inside `IT`.

## The experience component, and why it carries 30

"3+ years required" is the most common reason a graduate application is discarded, and it is
detectable with a regular expression. The parser has to separate three things that look alike:

- `5+ years of experience required` — a requirement, and the student fails it
- `3+ years preferred` — a preference, and a graduate may still be competitive
- `Bachelor's degree, 4 years` — a programme length, not a requirement
- `Graduating in 2026` — a date, not a duration

Getting this wrong in the safe direction (reading a preference as a requirement) makes the feed
pessimistic and hides workable jobs. Getting it wrong in the unsafe direction (missing a real
requirement) is worse, because it puts the student's evening into an application that was never
going to be read. When the parser finds nothing, the component scores as **unstated rather than
satisfied**, and says so — that is the difference story 35 asks for.

## Scoring arithmetic

Each component returns a value in its own weight, as an integer:

```
skills        0..40    matched_profile_skills / required_skills, when the posting states any
experience    0..30    30 when the requirement is met or unstated, tapering as the gap grows
keywords      0..20    BM25 of the description against the resume text, normalised
freshness     0..10    10 for today, tapering to 0 across a month
total         0..100   the sum, no separate rounding
```

Summing integers computed in their own weight avoids the drift that comes from scoring each
component 0–1 and multiplying at the end, where four roundings can put the visible parts one point
away from the visible total. The student would have no way to read that as anything but a bug.

**A posting that states no skills does not score 0 on skills.** It scores the neutral share and
labels the component `unstated`. Zero would rank a description that simply omitted its
requirements below one that listed requirements the student fails, which is backwards.

## Persistence and invalidation

`MatchScore` is unique on `(student_id, job_id, resume_master_id)`. Including the resume version in
the key is what makes invalidation free: uploading a new resume does not delete anything, it simply
stops matching the key, and the next render computes fresh scores. The old rows remain and stay
correct about the resume they describe.

Computed lazily for the twenty postings on the page being viewed, then written. A full pass over
4,437 postings per student would be the most expensive thing in the application, and almost all of
it would be for postings nobody scrolls to.

## What the interface shows

The design brief specifies a four-segment bar on every card, never a bare number. The segments are
proportional to their weights, so a card where experience is the missing piece looks visibly
different from one where skills are — the shape of the bar carries the diagnosis before any text is
read.

The signature device from feature 02 continues here: the receipt line. A score gets a receipt too —
which skills matched, what experience was found and on what basis, in mono, as machine evidence
rather than prose.

Two states need copy rather than a number: **no resume uploaded**, where the feed still works and
the score area explains what uploading would add (story 34), and **requirement unstated**, where
the component is neutral and labelled as such rather than silently full marks.

## Rejected

**Scoring the whole index on upload.** Predictable cost, and the wrong cost: it prices every
student's upload at 4,437 rows to make the first twenty fast.

**A single 0–100 number with a tooltip.** The decomposition is the product, not a detail. A tooltip
is where information goes to be ignored.

**Hiding postings under a threshold.** Rejected in ADR 0003 and again here. A student whose profile
scores badly against every posting they want needs to see that pattern, because it is the finding
that changes what they do next.
