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
- [ ] `ruff check` and `mypy` pass
