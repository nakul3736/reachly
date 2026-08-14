# 06 — Real parser: pdfplumber extraction and model structuring

**What to build:** a genuine resume PDF, in a real-world layout, parses into a correct
master resume. A scanned or encrypted PDF is refused with an explanation rather than
producing something empty.

This is the ticket that makes the feature work on an actual student's file rather than
on a fixture.

**Blocked by:** 05 — needs the parser seam and the parsed-resume shape.

**Status:** ready-for-agent

- [ ] An `LLMClient` adapter exists with a real implementation and a fixture one,
      selected by `DEMO_MODE`, per ADR 0002 — Reachly carries its own inference provider
      because Kiro's terms cover building software, not serving end users
- [ ] The real parser extracts text with pdfplumber, then structures it with one model
      call — one call per upload, cached permanently
- [ ] A real resume PDF is committed as a test fixture and parses into populated
      experience entries with stable bullet identifiers
- [ ] Seam-2 tests exercise real extraction offline, with no model call, so they stay
      fast and work without network
- [ ] A PDF with no extractable text layer, such as a scan, raises the unreadable error
- [ ] An encrypted PDF raises the unreadable error
- [ ] A model response that is malformed or missing required fields raises the parse
      failure error rather than storing partial output
- [ ] Extracted text is not truncated in a way that silently drops later roles

### Generality — the parser must not be tuned to one layout

Added after spike 002. That spike examined a single real resume, produced by LaTeX. Any
parser validated only against it is tuned to LaTeX whether or not that was intended, and
the tuning is invisible: every test passes, and the first failure is a real student whose
resume came out of Word. These criteria exist to make that failure loud and early.

- [ ] Parses all three committed variants — `sample_resume` (title-case headings, bullet
      glyphs, date on the title line), `sample_resume_word_like` (upper-case headings,
      hyphen bullets, employer before title, date on its own line), and
      `sample_resume_plain` (no bullet markers at all) — into populated experience entries
- [ ] A wrapped bullet is one bullet in every variant, never split with its tail promoted
      to a bullet of its own
- [ ] No rule keys on a specific employer, institution, or wording found in any fixture
- [ ] Passes against a real resume supplied via `REACHLY_REAL_RESUME_PDF`, and those tests
      skip rather than fail when it is unset, so a fresh clone and CI both pass
- [ ] Nothing in the parsed result is absent from `raw_text` — the parse-time form of
      ADR 0006, since structuring is where a model could invent a skill the student does
      not have, and everything downstream would then trust it

- [ ] `ruff check` and `mypy` pass
