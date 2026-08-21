# 01 â€” Skill extraction: vocabulary floor, model enrichment

**What to build:** a deterministic vocabulary extractor, and a model-assisted enricher that runs
once per posting at refresh time and caches its result on the row. ADR 0011.

Skill overlap is 40% of the score, so an extractor that looks plausible while under-reading makes
every score wrong while appearing to work. That has already happened once here: Gemini returned 7
"skills" for a resume containing 46, each a whole category line, and nothing failed until the count
was checked by hand. Both halves of this ticket get counted by hand against real descriptions.

**Blocked by:** nothing for the vocabulary half. The enricher needs the LLM seam, which exists.

**Status:** done

## The vocabulary floor

- [x] Canonical skill names with aliases, held as data rather than as branching code
- [x] `extract_skills(text) -> set[str]` returning canonical names
- [x] **Whole-term matching only.** `R` must not match inside `React`; `Go` must not match inside
      `Django` or `Mongo`; `C` must not match inside an ordinary word
- [x] `C++`, `C#`, `.NET`, `Node.js` and `CI/CD` extract correctly despite punctuation, which is
      exactly where a naive `\b` regex fails
- [x] Aliases collapse: `JS` and `Javascript` both yield `JavaScript`, so a resume and a posting
      using different surface forms still match
- [x] Case-insensitive, but the ordinary word `it` must never produce `IT`
- [x] Multi-word skills are found: `machine learning`, `unit testing`, `infrastructure as code`
- [x] A skill named many times counts once â€” this is a set, and frequency is BM25's job
- [x] Fast enough over a real 6,500-character description to run on twenty postings in one render

## The model enrichment

- [x] `enrich_job_skills(jobs, *, llm)` sends **one request per batch of postings**, never one per
      posting, and returns skills keyed back to each posting
- [x] The result is **unioned onto** the vocabulary's output, never replaces it. The vocabulary is
      the floor, so enrichment can only add
- [x] Stored on the row with the time it was produced, so a posting's skills can be identified as
      predating a prompt change
- [x] **Only postings that survive the graduate filters are enriched** â€” 170 of 4,437. The rest are
      senior, outside the US and Canada, or in fields the student is not searching, and paying to
      read them would be paying for pages nobody opens
- [x] Bounded per run, so one refresh cannot exhaust a day's quota
- [x] **Enrichment failure must not fail the refresh.** Same rule as a dead board: the rest of the
      run is still worth keeping
- [x] A posting can be re-enriched without re-fetching it
- [x] The model is asked for skills **present in the description**, and anything it returns that
      does not appear in the description text is discarded â€” the same evidence rule as tailoring,
      because an invented requirement would lower a student's score against a demand nobody made
- [x] Demo mode serves recorded enrichments, so the deployed app shows enriched behaviour with no
      key (ADR 0010)
- [x] The stored set records **which basis produced it**, so the interface can tell a student that
      one posting was read more thoroughly than another
- [x] Verified live against real descriptions, with a small number of calls, and the extracted
      skills read by hand to confirm they are genuinely in the text

## What real data changed

The offline tests passed while the extractor was badly wrong, and only 400 real postings showed
it. The four most common "skills" in the index were not skills at all:

| Term | What actually matched |
|---|---|
| `Teaching` (186 of 400) | "paid training", "we will provide you with the training" — a benefit |
| `Security` (120) | `Security Officer` guard postings, "financial security" |
| `Compliance` (95) | "in compliance with the local wage requirements" — legal boilerplate |
| `Monitoring` (56) | "actively monitoring the premises" on a patrol route |

Every one is a domain word rather than a skill, and the effect was worse than noise: a student
with `Communication` and `Teamwork` on their resume would have matched nearly every posting in the
index for reasons no employer wrote. The vocabulary now carries only qualified forms —
`Cybersecurity`, `Regulatory compliance`, `Observability`, `Computer networking` — and `training`
is gone from `Teaching` entirely.

**A lone capital letter is not a language.** `C` was extracted from a SpaceX posting containing no
C anywhere: real descriptions use standalone capitals as list markers, section labels and grades.
Case-sensitivity is not enough. A one-letter skill now counts only in the company of another
skill within sixty characters, which is what "Python, C, and SQL" looks like and what "Exhibit C"
does not.

After the corrections, on the postings a graduate developer actually sees:

| Sample | Median skills | Empty |
|---|---|---|
| software / data / infrastructure, 150 postings | **8** | 13% |
| all graduate-reachable, 400 postings | 1 | 43% |

The second row is not a defect, it is the argument for ADR 0011. Those postings are care,
logistics and retail roles described in prose, and no vocabulary reaches them.

## Why the extractor is a tokeniser rather than a regex

The first version was one alternation of ~450 terms with boundary lookarounds. It was too slow —
2.15s for twenty real descriptions against a 1.0s page budget — and, more importantly, it needed a
different guard for every punctuation shape: `.NET` begins with the character the leading guard
forbids, and `C++` ends with characters that satisfy `(?![\w])` immediately after the `C`.

Tokenising the text once and looking tokens up makes containment structurally impossible.
`JavaScript` is one token, so `Java` cannot match inside it; `Django` is one token, so `Go`
cannot. Correctness stopped depending on getting 450 lookarounds right.

## What the live run proved, and what it cost

Four calls total, across two runs.

The first run failed, and the failure was mine rather than the model's. `Shipment coordination`
was discarded from a description reading "Coordinate inbound and outbound shipments", and
`Carrier negotiation` from "negotiate collection windows with carriers" — both genuinely present,
both rejected, because a suffix table does not reach coordinate/coordination. The evidence rule
now also accepts a shared six-character prefix, which covers the whole nominalisation family
without a rule per English form, and the posting's title counts as evidence alongside its body.

Second run: **11 of 11 returned skills evidenced across three postings, none discarded.** On the
care posting the vocabulary found nothing and the model added `electronic charting`,
`recording vital signs`, `patient lifting and transferring` and `escalating patient condition
changes` — all four present in the text. That is ADR 0011 demonstrated rather than asserted.

## Departure from the ticket

**Demo mode does not serve recorded enrichments.** The ticket and the ADR both said it would. A
fixture can only answer for postings someone recorded, and the deployed index holds thousands
nobody has — so serving one anyway would label a vocabulary-only reading as a model reading,
which is the deception non-negotiable 4 exists to prevent. Demo mode reads with the vocabulary
and the interface says so. ADR 0011's consequences were corrected rather than left aspirational.