# 04 — Resume upload, stored but not parsed

**What to build:** a student uploads a resume PDF. It is kept. Uploading again creates
a new version rather than replacing the old one, and exactly one version is current at
any moment. The student can see their versions and when each arrived.

Parsing is deliberately absent — this ticket proves storage and versioning are correct
before parsing complicates them.

**Blocked by:** 03 — needs a student to own the resume.

**Status:** ready-for-agent

- [ ] A PDF upload is accepted and stored, and the student sees it listed
- [ ] The original bytes are stored in Postgres, not on the filesystem, because free
      hosting has an ephemeral disk and a redeploy would silently destroy every upload
- [ ] A file over the size cap is rejected before its body is read into memory
- [ ] A non-PDF is rejected, including a file renamed to `.pdf` — content is identified
      by magic bytes, not by extension or the declared content type
- [ ] A second upload creates version 2 and leaves version 1 retrievable
- [ ] Exactly one version is active, enforced by a unique partial index in the database
      rather than by application logic alone
- [ ] Activating a new version and deactivating the previous one happen in one
      transaction, so a failure cannot leave a student with no active resume
- [ ] Versions list newest first with their upload timestamps
- [ ] One student cannot read or list another student's resumes
- [ ] `ruff check` and `mypy` pass
