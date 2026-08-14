# 03 — Student profile

**What to build:** a student says what they are looking for — target role, locations,
years of experience, and the skills they already have — reads it back, and changes it
later. Another account cannot see it.

**Blocked by:** 02 — needs an authenticated user to own the profile.

**Status:** done

- [x] A student row is created when a user registers, so there is never an
      authenticated user without a profile to write to
- [x] The current student's profile can be read
- [x] Target role, locations, years of experience, and skills can be updated
- [x] Locations accept more than one value, so a student can search a city and remote
      roles together
- [x] A partial update leaves unsupplied fields unchanged, so editing one field does not
      silently clear the others
- [x] Years of experience rejects negative and implausibly large values
- [x] Empty strings in locations or skills are rejected or normalised away rather than
      stored, so they cannot become a filter matching nothing
- [x] The response states which fields are still missing for results to be useful
- [x] Profile routes act on the authenticated student, with no id in the path
- [x] One student cannot read or modify another student's profile
- [x] `ruff check` and `mypy` pass

Verified from an empty database: three migrations apply in order, `alembic check`
reports no drift between models and migrations, 54 tests pass, ruff clean, mypy clean
across 28 files, `students` table shape confirmed in Postgres.

## Notes from implementation

**The profile is created inside the registration transaction.** `flush` assigns the
user id without ending the transaction, so a failure creating the profile rolls back
the account too. Both or neither. Creating it lazily on first write would mean every
later feature has to cope with an authenticated user who has no student row.

**`exclude_unset` is what makes partial update correct.** Without it, a field absent
from the request body arrives as None and overwrites a real value — the bug where a
form that submits only the touched field wipes everything else. An explicit null is
still honoured, because clearing a field is a legitimate thing to want; the distinction
is between *absent* and *null*, not between *null* and *value*.

**Null years of experience is not zero.** Zero is a claim about the student; null is the
honest statement that they have not said. The distinction has to survive into scoring,
where treating unstated as a confirmed zero would silently misrank every incomplete
profile. This is the same principle as ADR 0006 applied to the profile rather than the
resume.

**List entries are trimmed, blanks dropped, duplicates collapsed case-insensitively.**
A stored empty string becomes a filter matching nothing, and does it silently — the
student sees an empty feed with no reason for it. Duplicates would double a skill's
weight in overlap scoring. The spelling the student chose is kept; only later
occurrences are dropped.

**No id in the path.** A route shaped `/students/{id}` invites an ownership check that
can be forgotten. With no id, the token is the only thing selecting a row, so there is
nothing to forget and nothing to tamper with.

## A hazard found and fixed

Running `alembic revision --autogenerate` after the test suite produced a migration
that recreated the `users` table. The test fixture drops every table between tests, so
against the development database it left `alembic_version` claiming head with no tables
present — and autogenerate compared the models to an empty schema.

Committing that migration would have failed on any database with real rows.

Fixed by giving tests their own database rather than by remembering the ordering:
`reachly_test`, created by `docker/postgres-init/01-create-test-database.sql` on first
volume initialisation. Verified by destroying the volume and bringing it back up.
`alembic check` is now part of the gate, since it catches exactly this class of drift.

## TDD discipline this time

Better than ticket 02. Two slices, each red before green:

1. Profile exists on registration and can be read — 4 tests red with 404, then green,
   and I stopped before writing the update route.
2. Update, validation, and isolation — 19 tests red, then green.

No test passed on its first run.
