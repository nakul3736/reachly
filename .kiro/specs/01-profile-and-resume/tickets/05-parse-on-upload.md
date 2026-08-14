# 05 — Parse on upload, behind the ResumeParser seam

**What to build:** an uploaded resume becomes a structured master resume — summary,
roles, bullets, skills, education — that the student can read back and check. When
parsing cannot succeed, the student is told which problem occurred and what to do about
it. The whole path works with no API key configured.

**Blocked by:** 04 — needs stored uploads to parse.

**Status:** done

- [x] A `ResumeParser` protocol exists with one operation taking PDF bytes and returning
      a parsed resume
- [x] A fixture implementation returns a recorded parsed resume, and `DEMO_MODE=true`
      selects it, so the feature works with no keys — this is the path judges use
- [x] Upload invokes the parser and stores the structured result against that version
- [x] The student can read the parsed result for their active version
- [x] Every experience entry and every bullet carries a stable identifier assigned at
      parse time, because provenance in ADR 0006 has nothing to reference without them
- [x] The full extracted text is retained, so the provenance validator can draw its
      entity set from the whole document rather than one bullet
- [x] Dates are stored as written and never normalised or inferred
- [x] An unreadable file and a failed structuring attempt produce **different** errors
      with different guidance, because the student's fix differs
- [x] The parser never returns an empty result to signal failure
- [x] A failed parse does not create an active version
- [x] `ruff check` and `mypy` pass

Verified: 114 passed and 5 skipped as a fresh clone sees it, 119 passed with a real
resume configured via `REACHLY_REAL_RESUME_PDF`, ruff clean, mypy clean across 49 files,
`alembic check` reports no drift.

## Notes from implementation

**Extraction and structuring are separate, and only structuring is substituted.**
Extraction is deterministic pdfplumber and runs even in demo mode, so an unreadable PDF
is detected for the real reason rather than by matching a known fixture hash. A judge who
uploads a scan gets the correct error and the correct advice. It also makes ticket 06 a
drop-in rather than a rewrite.

**Bullet ids are derived from content, not position.** A positional id — `experience-0`,
or a database sequence — still resolves after a role is inserted above it, while pointing
at the wrong bullet. Every stored `provenance_map` would then show evidence for a claim
it did not come from, and nothing would surface the error. Content-derived ids change
when the content changes, which is the honest behaviour.

**Parsing happens before any row is written.** Not inside the transaction and rolled
back — before it. Three properties follow and each is tested: a failed parse creates no
version, leaves the previous active version active, and does not consume a version
number. An active resume containing nothing would be worse than no resume, because
tailoring would draw on no evidence while appearing to work.

**Three failure modes stay distinguishable.** A `.docx` renamed to `.pdf` is 415
`unsupported_resume_format`; a scan with no text layer is 422 `resume_unreadable`; a
structuring failure is 502 `resume_parse_failed`. The first two are the student's to fix
and say so; the third is not, and its message does not blame their file. Collapsing these
into one message would leave students retrying the wrong thing.

**No active resume is distinct from a resume that parsed to nothing.** 404
`no_active_resume` versus 409 `resume_not_parsed`. One needs an upload prompt, the other
an explanation.

**A structuring failure had to be forced with monkeypatch.** The fixture parser cannot
fail that way on its own, and an error path with no test is an error path that has never
run.

## What adding parsing broke, and why that was good news

Wiring the parser into upload turned 16 previously passing tests red. `MINIMAL_PDF` had
been the happy-path fixture across tickets 04's tests, and it has no text layer — so once
upload parsed, it was correctly refused as unreadable.

That is the tests doing their job. Adding parsing genuinely changed what a valid upload
is, and the suite said so rather than quietly accepting a fixture that no longer
represented a real resume. The happy paths now use the readable generated resume, and
`MINIMAL_PDF` is used only where *unreadable* is the intent. `pdf_of_size` was rebased on
the readable fixture too, padding after `%%EOF` so the document still parses.

## TDD discipline

Two slices this ticket. The first, parse-on-upload and reading it back, was properly red:
8 failed, 1 passed — and that one pass was spurious, a missing route answering 404 where
the ownership test expected 404. It was strengthened to assert the owner gets 200 first,
which is the third time that shape has appeared and worth watching for.

The second slice, failure paths, passed on its first run. Ordering parse before the write
in slice 1 gave the behaviour for free. Those 7 tests characterise rather than drive,
though the two asserting *distinct* error codes and actionable wording do pin deliberate
design choices that a later refactor could plausibly undo.
