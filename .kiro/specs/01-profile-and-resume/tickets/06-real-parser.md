# 06 — Real parser: pdfplumber extraction and model structuring

**What to build:** a genuine resume PDF, in a real-world layout, parses into a correct
master resume. A scanned or encrypted PDF is refused with an explanation rather than
producing something empty.

This is the ticket that makes the feature work on an actual student's file rather than
on a fixture.

**Blocked by:** 05 — needs the parser seam and the parsed-resume shape.

**Status:** done

- [x] An `LLMClient` adapter exists with a real implementation and a fixture one,
      selected by `DEMO_MODE`, per ADR 0002 — Reachly carries its own inference provider
      because Kiro's terms cover building software, not serving end users
- [x] The real parser extracts text with pdfplumber, then structures it with one model
      call — one call per upload, cached permanently
- [x] A real resume PDF is committed as a test fixture and parses into populated
      experience entries with stable bullet identifiers
- [x] Seam-2 tests exercise real extraction offline, with no model call, so they stay
      fast and work without network
- [x] A PDF with no extractable text layer, such as a scan, raises the unreadable error
- [x] An encrypted PDF raises the unreadable error
- [x] A model response that is malformed or missing required fields raises the parse
      failure error rather than storing partial output
- [x] Extracted text is not truncated in a way that silently drops later roles

### Generality — the parser must not be tuned to one layout

Added after spike 002. That spike examined a single real resume, produced by LaTeX. Any
parser validated only against it is tuned to LaTeX whether or not that was intended, and
the tuning is invisible: every test passes, and the first failure is a real student whose
resume came out of Word. These criteria exist to make that failure loud and early.

- [x] Parses all three committed variants — `sample_resume` (title-case headings, bullet
      glyphs, date on the title line), `sample_resume_word_like` (upper-case headings,
      hyphen bullets, employer before title, date on its own line), and
      `sample_resume_plain` (no bullet markers at all) — into populated experience entries
- [x] A wrapped bullet is one bullet in every variant, never split with its tail promoted
      to a bullet of its own
- [x] No rule keys on a specific employer, institution, or wording found in any fixture
- [x] Passes against a real resume supplied via `REACHLY_REAL_RESUME_PDF`, and those tests
      skip rather than fail when it is unset, so a fresh clone and CI both pass
- [x] Nothing in the parsed result is absent from `raw_text` — the parse-time form of
      ADR 0006, since structuring is where a model could invent a skill the student does
      not have, and everything downstream would then trust it

## Verification

Offline: 150 passed, 14 skipped, ruff clean, mypy clean across 60 files.

Live, against the real model: **`9 passed in 255.95s`** — all three layout variants plus a
real resume supplied via `REACHLY_REAL_RESUME_PDF`. On the real resume: 3 roles, 11 bullets,
longest 214 characters where extraction caps a line at 120 — so wrapped bullets were
genuinely joined. Dates came back as `January 2026 - Present`, `September 2023 - August
2024`, and `January 2023 - Aug 2023`, the last mixing a full month name with an abbreviated
one inside a single range. The evidence check dropped nothing, meaning the model copied
verbatim.

## Notes from implementation

**Demo mode runs the real parser.** Only the inference call is recorded. The earlier fixture
returned a finished `ParsedResume` and skipped extraction, evidence checking and identifier
derivation — the code most likely to be wrong — so a judge running `DEMO_MODE=true` was
testing a different program. That fixture is deleted. See ADR 0010.

**The fabrication rule splits by stakes.** An invented skill, bullet, date or summary is
dropped, because removing it leaves the resume correct and merely less complete. An invented
employer or title fails the parse outright. A resume missing a job is something the student
notices and questions; a job they never had, presented as parsed from their own document,
they might believe.

**Whitespace-normalised containment lives in `app/domain/evidence.py`**, not in the parser,
because the ADR 0006 tailoring validator needs the identical check. Normalisation is
required rather than cosmetic: a wrapped bullet appears in extracted text with a newline
where the joined bullet has a space, so literal comparison would flag every wrapped bullet
as fabricated — the longest and most detailed ones.

## Three bugs the live run found that reading the code would not

**The pinned model had gone stale.** `gemini-2.5-flash` returns 404, "no longer available to
new users". Repinned to `gemini-3.6-flash` rather than `gemini-flash-latest`, because the
moving alias returned 503 in the same minute two pinned models returned 200. The 404 also
exposed a real deficiency: the provider's message was being swallowed, so a retired model
was indistinguishable from a bad key and diagnosing it needed a throwaway script rather than
a log line.

**Skill extraction was broken invisibly.** Gemini returned 7 skills for a resume containing
46, because each entry was a whole category line — `"Languages: Java, JavaScript,
TypeScript, Python, SQL, C, C++"`. Skill overlap is 40% of the match score under ADR 0003,
so comparing a job's `Python` requirement against that blob matches nothing: every score
wrong, nothing visibly broken. Grouped lines are now split deterministically rather than by
asking the model more firmly, since relying on prompt compliance for a structural
requirement is one model revision from silent breakage. Commas inside brackets are not
separators, so `AWS (lambda, IAM, VPC)` survives as one skill, and each split token is
evidence-checked independently so splitting cannot smuggle an invention through. Verified on
a real resume: 7 became 43.

**The live suite exhausted a day's quota.** It parsed each document twice — once to check
the layout parsed, again to check bullets were joined — and both are properties of the same
parse. Documents are now parsed once per session and reused: six calls per run instead of
nine. This is what prompted ADR 0010.

- [x] `ruff check` and `mypy` pass
