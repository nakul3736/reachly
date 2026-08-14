# 01 — Design

Companion to `requirements.md`. Carries the Implementation Decisions, Testing
Decisions and Further Notes sections of the `/to-spec` template; the Problem,
Solution, User Stories and Out of Scope sections are in `requirements.md`, following
Kiro's spec layout and `docs/agents/issue-tracker.md`.

## Implementation decisions

### Modules

Four areas, following the layout in `.kiro/steering/backend.md`:

- **Core** — settings from the environment, database session factory, password hashing
  and token issue/verify. No business logic.
- **Models** — `User`, `Student`, `ResumeMaster`. Only these three; the remaining nine
  tables designed earlier arrive with the features that read them. A migration that
  creates tables nothing queries is a guess awaiting correction.
- **Adapters** — `ResumeParser` as a protocol with a real and a fixture implementation,
  and the `LLMClient` the real parser depends on. `EmailSender` exists as a protocol
  with only a no-op implementation, purely as the seam for later verification email.
- **Services** — registration, login, profile update, resume version creation. No
  FastAPI imports; callable from a script or a test without an HTTP layer.

### Schema

`User` holds identity and credentials: email (unique, lowercased on write),
password hash, `is_verified` and a reset-token column as unused seams, timestamps.

`Student` holds the search profile, one row per user: target role, an array of
locations, years of experience, an array of self-declared skills. Separate from `User`
because it is domain data with a different lifecycle, and because the remaining
features key off `student_id` rather than `user_id`.

`ResumeMaster` holds one row per upload: student, an integer version, the original PDF
bytes, the parsed JSON, an `is_active` flag, and a created timestamp. Versions are
never updated after creation except for `is_active`.

**Exactly one active version per student is enforced in the database**, by a unique
partial index on `student_id` where `is_active` is true, not by application logic
alone. Activation and deactivation happen in one transaction.

**The original PDF is stored as bytes in Postgres, not on disk.** Render's free tier has
an ephemeral filesystem — a redeploy or restart would silently lose every uploaded
resume, and the loss would only surface when a student tried to re-parse. Aiven's 1GB
free tier holds thousands of resumes. Object storage would mean another provider and
another key for judges.

### The parsed resume shape

This shape is a decision rather than an implementation detail, because ADR 0006 depends
on it. The provenance validator has to compare a generated bullet against *the specific
original bullet* it derives from, so bullets need stable identifiers assigned at parse
time. Without them, `provenance_map` has nothing to point at and evidence-locked
tailoring is unenforceable.

```
ParsedResume
  summary        str | None
  experience     [ExperienceEntry]
  education      [EducationEntry]
  skills         [str]
  raw_text       str            # full extracted text, for the validator's entity set

ExperienceEntry
  id             str            # stable, assigned at parse time — provenance target
  employer       str
  title          str
  start_date     str | None     # as written; not normalised, not invented
  end_date       str | None
  bullets        [Bullet]

Bullet
  id             str            # stable — what provenance_map references
  text           str
```

Dates are kept as written rather than normalised. A parser that turns "Summer 2025"
into a date range is inventing precision, which is the same failure mode ADR 0006
exists to prevent.

`raw_text` is retained deliberately: the validator needs the entity set of the whole
original document, not just the bullet being rewritten, or a student's genuine skill
mentioned only in their summary would be treated as fabricated.

### The `ResumeParser` interface

`parse(pdf_bytes) -> ParsedResume`, raising a typed error the API layer can translate:

- **Unreadable** — encrypted, corrupt, or no extractable text layer (a scanned image).
  Distinct because the student's fix is different: export a text PDF rather than scan.
- **Parse failed** — text extracted but structuring failed or returned unusable output.

Returning an empty result on failure is forbidden. Per `.kiro/steering/backend.md`, an
empty result and a failed call are different facts and must not be conflated.

The real implementation extracts text with pdfplumber, then structures it with one
`LLMClient` call. This is the one model call in the feature and a deliberate exception
to ADR 0003's deterministic-first rule — heuristic parsing of arbitrary layouts fails
silently and would corrupt the master resume everything downstream depends on. One call
per upload, cached permanently.

The fixture implementation returns a recorded `ParsedResume` and can be configured to
raise either error, so failure paths are testable without malformed input at the HTTP
layer.

### API contract

Registration and login return a token. Profile and resume routes act on the
authenticated student — `me` rather than an id in the path, so there is no object
reference a caller could tamper with.

- Register, login
- Read and update the current student's profile
- Upload a resume, list versions, read the active version's parsed result

Uploads are multipart with a size cap enforced before reading the body into memory,
and content sniffed by magic bytes rather than trusting the declared content type or
file extension.

Errors use the envelope from `.kiro/steering/backend.md` with a stable machine-readable
code, because the interface distinguishes "unreadable file" from "provider unavailable"
and shows the student different guidance for each.

### Auth

bcrypt for hashing, used directly rather than through passlib, which breaks against
bcrypt 4.1+ on current Pythons. JWT signed HS256 with the secret from the environment
and no default. Bearer token in the `Authorization` header.

Login returns the same error for unknown email and wrong password, so registration is
not disclosed by probing.

### DEMO_MODE

`DEMO_MODE=true` selects the fixture parser and the no-op sender, so the entire feature
works with no keys. This is the path judges use, so it is a first-class requirement
rather than test scaffolding.

## Testing decisions

### What makes a good test here

Tests assert behaviour observable through a public interface, never internal structure.
A test that inspects a service's private method, or asserts on database rows instead of
reading through the API, breaks under refactoring while the behaviour is unchanged —
and tells us nothing a user would notice.

Expected values come from an independent source: a known-good literal, or the spec.
A test that recomputes the expected value the way the code does passes by construction
and can never disagree with the code.

All tests run with `DEMO_MODE=true` and must not reach the network.

### Seams under test

Confirmed with the developer before writing this spec. Two, not one.

**Seam 1 — the HTTP API.** Everything user-facing: registration, duplicate email,
password rules, login success and failure, unauthenticated and tampered-token
rejection, profile read and update, upload acceptance and rejection, the parsed result
read back, versioning across a second upload, and one student's inability to read
another's resume.

**Seam 2 — the `ResumeParser` protocol.** The adapter contract: a real PDF produces a
populated `ParsedResume` with stable bullet ids; an encrypted or image-only PDF raises
the unreadable error rather than returning something empty.

Seam 2 exists because without it every test would parse through a fixture, leaving the
pdfplumber path — the code that meets real, messy PDF bytes — unexercised. That path is
the most likely thing to fail on an actual student's resume. A test at this seam runs
real extraction against a committed sample PDF with no model call, so it stays fast and
offline.

It is also not new architecture: `.kiro/steering/backend.md` already requires every
external dependency to sit behind an adapter with a real and a fixture implementation.

**Deliberately not seams.** Text extraction was considered as a third seam and rejected —
it always runs together with structuring, so it adds a boundary without adding coverage
the parser seam lacks. Auth and ownership get no seam of their own; they are behaviour,
asserted at the HTTP layer.

### Priority

Per `.kiro/steering/testing.md`, ownership isolation ranks above convenience paths:
a student reading another student's resume is the most damaging defect this feature
could ship. Versioning is next, because silent loss of a master resume is unrecoverable
for the user.

### Prior art

None — this is the first tested code in the repository, so these tests set the
conventions later specs follow: `httpx.AsyncClient` against the ASGI app, transactional
fixtures rolled back per test, factory helpers rather than fixture files, and
parametrised table-driven cases.

## Further notes

Auth lands here rather than late, reversing the original specification's plan to add it
in week six. Every table in the remaining nine keys off `student_id`, so deferring
authentication would mean either fake identifiers throughout or a retrofit at the point
in the schedule with the least slack.

The seeded judge account and guest entry from user stories 7 and 8 depend on this
feature and are built with it, not bolted on later. They are how a judge reaches a
working product in seconds, which Rule 17 requires and Round One screening rewards.
