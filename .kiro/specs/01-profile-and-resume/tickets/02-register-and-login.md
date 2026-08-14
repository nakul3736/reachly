# 02 — Register and log in

**What to build:** a student creates an account with an email and password, logs in,
and receives a token that grants access to their own data. A protected route proves
the token works and that its absence is refused.

**Blocked by:** 01 — needs the app, settings, and migrations.

**Status:** ready-for-agent

- [ ] Registration creates a user and returns a token, so the student is not asked to
      log in immediately after signing up
- [ ] Email is stored lowercased and is unique; registering an existing email returns a
      distinct, actionable error rather than a generic failure
- [ ] Password below the minimum length is rejected with the requirement stated
- [ ] Passwords are hashed with bcrypt and the hash is never returned by any endpoint
- [ ] Login with correct credentials returns a token
- [ ] Login with an unknown email and login with a wrong password return the **same**
      error, so registration is not disclosed by probing
- [ ] A protected route returns the current user with a valid token
- [ ] A protected route rejects a missing token, a malformed token, a token signed with
      the wrong secret, and an expired token
- [ ] `is_verified` and a reset-token column exist and are unused, as seams for later
- [ ] An `EmailSender` protocol exists with only a no-op implementation
- [ ] `ruff check` and `mypy` pass
