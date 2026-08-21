# 02 â€” Experience requirement parsing

**What to build:** `parse_experience_requirement(title, description) -> ExperienceRequirement`,
returning the years demanded and the basis on which that was decided.

This carries 30 of the 100 points, second only to skills, and it earns that weight because "5+
years required" is the most common reason a graduate's application is discarded â€” and it is
invisible from the title. A posting called `Software Engineer` with "5+ years" in the body passes
every filter feature 02 has.

**Full test rigour.** The parser has to separate four things that look nearly identical in text,
and both directions of error cost the student something specific.

**Blocked by:** nothing. Text in, structure out.

**Status:** done

- [x] `5+ years of experience required` yields 5, as a requirement
- [x] `Minimum 3 years`, `at least 4 years`, `3-5 years`, `three years` all parse â€” providers write
      this every way English allows, including as words
- [x] **`3+ years preferred` is a preference, not a requirement**, and a graduate may still be
      competitive. Reading it as a hard requirement makes the feed pessimistic and buries workable
      jobs
- [x] **A programme length is not a requirement.** `Bachelor's degree (4 years)` and `4-year degree`
      demand no work experience
- [x] **A year is not a duration.** `Graduating in 2026`, `since 2019`, `founded in 2015` and
      `Summer 2026` yield nothing
- [x] **A stipend, headcount or metric is not a duration.** `$120,000 per year`, `40 hours per week`
      and `grew 30% year over year` yield nothing
- [x] When several requirements appear, the **lowest** is taken. Descriptions commonly say "3+ years
      required, 5+ preferred", and the lower number is the bar the student must clear
- [x] `0-2 years`, `no experience required`, `new graduate`, `entry level` yield an explicit zero,
      which is different from silence
- [x] **Nothing found is `unstated`, not zero.** A description that never mentions experience has
      not said the student qualifies, and the score must be able to tell those apart â€” story 35
- [x] The requirement's **basis is returned** â€” the matched phrase â€” so the interface can show the
      student the words it read rather than only the number it produced
- [x] Title is searched as well as body: `Senior Engineer (5+ yrs)` states it in the title
- [x] Run over the real stored index and the distribution reported, because a parser that finds a
      requirement in 2% of postings and one that finds it in 60% cannot both be right, and only
      real data says which
- [x] Generality checked on descriptions from boards outside the seed set, asserting properties
      rather than per-posting answers

## The bug real data found, and why it mattered most of all

Running the parser over 773 graduate-reachable postings produced a distribution that looked
reasonable until one bucket: **31 postings appeared to require eighteen years of experience.**

They were `Per Diem Associate Patient Care Coordinator`, `Customer Service Representative` and
`PCA/HHA`. The phrase was "must be at least 18 years of age or older" — hourly-role legal
boilerplate that carries every marker a genuine requirement has: the words "at least", a number,
and the unit "years".

This was the worst possible failure for this product. Those postings are the most accessible jobs
in the entire index, and the parser was about to score them as demanding eighteen years of
experience and bury them at the bottom of the feed — for precisely the reader Reachly is built
for. Nothing in the offline tests would ever have caught it, because nobody writing tests invents
that sentence.

The guard needs two halves, because the marker sits on either side of the number:

- after the unit — `18 years of age`, `18 years old`, `19 years or older`
- before the number — `the legal working age of 16 years`

Distribution after the fix, over the same 773 postings:

| Basis | Count | Share |
|---|---|---|
| required | 348 | 45% |
| unstated | 379 | 49% |
| preferred | 46 | 6% |

Nothing above thirteen years survives except two genuine senior roles (`15+ years of sales
experience`, a Field CTO posting). **A quarter of the postings that pass every feature 02 filter
demand three or more years** — which is the number that justifies this component carrying 30 of
the 100 points.

## Two further judgements

**Basis is decided clause-locally, never from a fixed window.** A seventy-character window crosses
a full stop, and `2+ years required. 5+ years preferred.` then read its first number as a
preference — inverting the answer for one of the commonest phrasings there is. The tail capture
cannot cross a full stop, a semicolon or a newline, which is what makes it safe to read.

**A heading carries the basis for the lines beneath it.** Real descriptions put the basis in the
heading and not in the bullet: `Nice to have` followed by `3+ years of experience with Kubernetes`
is optional, and reading that bullet alone would hide a job a graduate could get. The lookback is
three lines, because a heading twenty bullets above is no longer describing this line.

## Generality

268 postings from three boards the parser has never seen (Duolingo, Reddit, Discord): zero age
false positives, zero calendar years read as durations. The single flagged item was a genuine
`VP of Strategy and Corporate Development` asking for 20+ years, which is a correct read.