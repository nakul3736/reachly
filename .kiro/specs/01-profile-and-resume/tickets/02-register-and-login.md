# 02 — Register and log in

**What to build:** a student creates an account with an email and password, logs in,
and receives a token that grants access to their own data. A protected route proves
the token works and that its absence is refused.

**Blocked by:** 01 — needs the app, settings, and migrations.

**Status:** done

- [x] Registration creates a user and returns a token, so the student is not asked to
      log in immediately after signing up
- [x] Email is stored lowercased and is unique; registering an existing email returns a
      distinct, actionable error rather than a generic failure
- [x] Password below the minimum length is rejected with the requirement stated
- [x] Passwords are hashed with bcrypt and the hash is never returned by any endpoint
- [x] Login with correct credentials returns a token
- [x] Login with an unknown email and login with a wrong password return the **same**
      error, so registration is not disclosed by probing
- [x] A protected route returns the current user with a valid token
- [x] A protected route rejects a missing token, a malformed token, a token signed with
      the wrong secret, and an expired token
- [x] `is_verified` and a reset-token column exist and are unused, as seams for later
- [x] An `EmailSender` protocol exists with only a no-op implementation
- [x] `ruff check` and `mypy` pass

Verified: 31 tests pass, ruff clean, mypy clean across 22 files, migration
`0308b4a26e14` applies and reverses, table shape confirmed in Postgres.

## Notes from implementation

**Duplicate email is caught by the unique constraint, not a prior SELECT.** Checking
first and inserting after leaves a window where two simultaneous registrations of the
same address both pass the check. The `IntegrityError` is translated to a 409.

**Failed login verifies a password even when no user was found.** Against a dummy
hash, so the response time does not differ between an unknown email and a wrong
password. Returning identical status and body is not sufficient on its own — timing is
observable too.

**Every token failure collapses to one refusal.** Missing header, wrong scheme, forged
signature, expired token, and a validly signed token naming a deleted user all produce
the same 401. The caller has no legitimate use for the distinction, and exposing it
leaks information.

**Passwords are capped at 72 bytes.** bcrypt silently truncates there, so without a cap
two different long passwords would authenticate the same account.

## Where TDD discipline slipped

Honest record, since the point of the loop is the feedback and I did not get it
everywhere.

The registration tests were genuinely test-first: they went red with a 404, then green.
But while implementing them I wrote the login and `/me` routes in the same pass, so
`test_login.py` passed on its first run. Those tests characterise behaviour rather than
having driven it — the same slip flagged on `test_config.py` in ticket 01.

One test also passed spuriously before being fixed:
`test_register_never_returns_the_password_hash` asserted only that the response body
contained neither "hash" nor "password", which is true of a 404 body. It now asserts
the 201 first. Worth noting as the exact shape of a test that cannot fail for the right
reason.

Next ticket: write the tests for one slice, watch them go red, and stop before writing
the next slice's implementation.
