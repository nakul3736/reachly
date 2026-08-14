# 04 — Resume upload, stored but not parsed

**What to build:** a student uploads a resume PDF. It is kept. Uploading again creates
a new version rather than replacing the old one, and exactly one version is current at
any moment. The student can see their versions and when each arrived.

Parsing is deliberately absent — this ticket proves storage and versioning are correct
before parsing complicates them.

**Blocked by:** 03 — needs a student to own the resume.

**Status:** done

- [x] A PDF upload is accepted and stored, and the student sees it listed
- [x] The original bytes are stored in Postgres, not on the filesystem, because free
      hosting has an ephemeral disk and a redeploy would silently destroy every upload
- [x] A file over the size cap is rejected before its body is read into memory
- [x] A non-PDF is rejected, including a file renamed to `.pdf` — content is identified
      by magic bytes, not by extension or the declared content type
- [x] A second upload creates version 2 and leaves version 1 retrievable
- [x] Exactly one version is active, enforced by a unique partial index in the database
      rather than by application logic alone
- [x] Activating a new version and deactivating the previous one happen in one
      transaction, so a failure cannot leave a student with no active resume
- [x] Versions list newest first with their upload timestamps
- [x] One student cannot read or list another student's resumes
- [x] `ruff check` and `mypy` pass

Verified: 79 tests pass, ruff clean, mypy clean across 37 files, migration `772d886c1fd2`
applies and reverses, `alembic check` reports no drift, and the index as Postgres stored
it reads `CREATE UNIQUE INDEX uq_resume_one_active_per_student ON public.resume_masters
USING btree (student_id) WHERE is_active`.

## Notes from implementation

**The size cap is enforced twice, on purpose.** The `Content-Length` header is checked
first so an oversized upload is refused without reading it at all, but the header is
client-supplied and can lie or be absent under chunked encoding. The authoritative
guard is a running total across a chunked read, which stops accumulating the moment the
cap is passed.

**Validation happens before anything is written.** Two consequences are tested
explicitly: a rejected upload leaves the previously active version active, and it does
not consume a version number. The first is the failure that would be worst to ship — a
student would keep a resume visible in the list that nothing actually uses, with no
error explaining it. The second matters because version numbers are shown to the
student, so a gap is a question they cannot answer.

**The partial index is scoped to `student_id`.** A global unique index on `is_active`
would permit exactly one student in the entire system to have an active resume. That
failure does not appear with one test account; it appears with the second user, which is
to say in front of a judge. There is a test for it specifically.

**The one-active test manipulates the database directly.** Deliberately. If it went
through the service it would pass because the service happens to deactivate first,
which is not the claim being made. The claim is that a future code path that forgets to
deactivate cannot produce two active resumes.

**Ownership is part of the query, not a check after it.** `get_owned` filters on
`student_id` in the same statement. A separate check is something that can be omitted at
one call site; a scoped query cannot return a row that fails it. Another student's
resume answers 404 rather than 403, because a refusal confirming the row exists still
tells them something.

## What is deliberately not checked yet

Content validation here is the five-byte `%PDF-` header and nothing more. That catches
the realistic mistakes — a `.docx` renamed to `.pdf`, a saved login page, an empty file
— because none of those carry the header, and it trusts neither the filename nor the
declared content type since both are chosen by the client.

It does **not** establish that the PDF is well-formed, unencrypted, or contains any
readable text. Demonstrated rather than assumed: `MINIMAL_PDF`, the fixture used
throughout these tests, passes `validate_pdf`, opens in pdfplumber, reports one page,
and extracts `''`.

That makes it the fixture for the *unreadable* branch in ticket 05, which is where the
distinction between unreadable (encrypted or scanned, no text layer) and parse-failed
gets made — they need different advice to the student. Ticket 06 needs a genuinely
different artifact: a real PDF with an actual text layer.

The layering is: bytes are a PDF (this ticket) → the PDF yields text (05) → the text
becomes structured experience with stable bullet ids (06).

## TDD discipline

Three slices. The first two were properly red first: 10 tests failing on a missing
model, then 8 failing on a missing constant.

The third, versioning, passed on its first run. Honest account of why: `store_new_version`
had to do something coherent when it was written in slice 1, and deactivating the
previous version was part of that. So those 7 tests characterise behaviour rather than
having driven it. The two partial-index tests are the ones I would have most wanted the
red phase for, since the student-scoped-versus-global mistake is easy to make and they
would have caught it.
