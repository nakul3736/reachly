# 02 — Experience requirement parsing

**What to build:** `parse_experience_requirement(title, description) -> ExperienceRequirement`,
returning the years demanded and the basis on which that was decided.

This carries 30 of the 100 points, second only to skills, and it earns that weight because "5+
years required" is the most common reason a graduate's application is discarded — and it is
invisible from the title. A posting called `Software Engineer` with "5+ years" in the body passes
every filter feature 02 has.

**Full test rigour.** The parser has to separate four things that look nearly identical in text,
and both directions of error cost the student something specific.

**Blocked by:** nothing. Text in, structure out.

**Status:** ready-for-agent

- [ ] `5+ years of experience required` yields 5, as a requirement
- [ ] `Minimum 3 years`, `at least 4 years`, `3-5 years`, `three years` all parse — providers write
      this every way English allows, including as words
- [ ] **`3+ years preferred` is a preference, not a requirement**, and a graduate may still be
      competitive. Reading it as a hard requirement makes the feed pessimistic and buries workable
      jobs
- [ ] **A programme length is not a requirement.** `Bachelor's degree (4 years)` and `4-year degree`
      demand no work experience
- [ ] **A year is not a duration.** `Graduating in 2026`, `since 2019`, `founded in 2015` and
      `Summer 2026` yield nothing
- [ ] **A stipend, headcount or metric is not a duration.** `$120,000 per year`, `40 hours per week`
      and `grew 30% year over year` yield nothing
- [ ] When several requirements appear, the **lowest** is taken. Descriptions commonly say "3+ years
      required, 5+ preferred", and the lower number is the bar the student must clear
- [ ] `0-2 years`, `no experience required`, `new graduate`, `entry level` yield an explicit zero,
      which is different from silence
- [ ] **Nothing found is `unstated`, not zero.** A description that never mentions experience has
      not said the student qualifies, and the score must be able to tell those apart — story 35
- [ ] The requirement's **basis is returned** — the matched phrase — so the interface can show the
      student the words it read rather than only the number it produced
- [ ] Title is searched as well as body: `Senior Engineer (5+ yrs)` states it in the title
- [ ] Run over the real stored index and the distribution reported, because a parser that finds a
      requirement in 2% of postings and one that finds it in 60% cannot both be right, and only
      real data says which
- [ ] Generality checked on descriptions from boards outside the seed set, asserting properties
      rather than per-posting answers
