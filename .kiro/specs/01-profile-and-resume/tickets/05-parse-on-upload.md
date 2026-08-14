# 05 — Parse on upload, behind the ResumeParser seam

**What to build:** an uploaded resume becomes a structured master resume — summary,
roles, bullets, skills, education — that the student can read back and check. When
parsing cannot succeed, the student is told which problem occurred and what to do about
it. The whole path works with no API key configured.

**Blocked by:** 04 — needs stored uploads to parse.

**Status:** ready-for-agent

- [ ] A `ResumeParser` protocol exists with one operation taking PDF bytes and returning
      a parsed resume
- [ ] A fixture implementation returns a recorded parsed resume, and `DEMO_MODE=true`
      selects it, so the feature works with no keys — this is the path judges use
- [ ] Upload invokes the parser and stores the structured result against that version
- [ ] The student can read the parsed result for their active version
- [ ] Every experience entry and every bullet carries a stable identifier assigned at
      parse time, because provenance in ADR 0006 has nothing to reference without them
- [ ] The full extracted text is retained, so the provenance validator can draw its
      entity set from the whole document rather than one bullet
- [ ] Dates are stored as written and never normalised or inferred — turning
      "Summer 2025" into a date range is the invention ADR 0006 exists to prevent
- [ ] An unreadable file and a failed structuring attempt produce **different** errors
      with different guidance, because the student's fix differs
- [ ] The parser never returns an empty result to signal failure; an empty resume and a
      failed parse are different facts
- [ ] A failed parse does not create an active version, so a student is never left with
      an active resume containing nothing
- [ ] `ruff check` and `mypy` pass
