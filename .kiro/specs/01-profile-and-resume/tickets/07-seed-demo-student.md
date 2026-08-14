# 07 — Seeded demo student with a parsed resume

**What to build:** a documented account that already has a profile and a parsed master
resume, so anyone opening the project sees a populated product rather than an empty form.

Rule 17 requires judges to be given working test credentials, and Round One screening
rewards a project that demonstrably works on first contact.

**Blocked by:** 05 — needs parsing to seed a master resume. Independent of 06; the
fixture parser is sufficient.

**Status:** done

- [x] Seeding is idempotent — running it twice does not duplicate the account or its
      resume versions
- [x] The seeded student has a realistic new-graduate profile: target role, locations,
      years of experience, and skills
- [x] The seeded student has an active master resume with parsed experience and bullets
- [x] Seeded credentials come from configuration, not hardcoded, and the values used for
      the deployed demo are documented in the README
- [x] Seeding is safe to run against a database that already has real data
- [x] The seed can be invoked as a command, not only at startup, so redeploying does not
      depend on boot-time side effects
- [x] `ruff check` and `mypy` pass

Verified against the development database, not only in tests: first run printed
`demo account created`, second printed `demo account already present` with one resume
version, and an unset password printed `seed failed: Set DEMO_STUDENT_PASSWORD…` with
exit code 1 and no traceback. The row reads `demo@reachly.app | Backend Engineer |
version 1 | active | 1804 pdf_bytes | parsed`.

Suite: 122 passed and 5 skipped as a fresh clone sees it, 127 passed with a real resume
configured, ruff clean, mypy clean across 52 files, `alembic check` reports no drift.

> **README still owes this.** The criterion above is satisfied on the configuration side,
> but the README does not exist yet — it is Aug 21 work. The published credentials must
> match `DEMO_STUDENT_EMAIL` and whatever password the deployment is given.

## Notes from implementation

**The password has no default and seeding refuses without one.** A fallback would ship a
known credential to every deployment that forgot to configure one, including any that
later holds a real person's data. The email does have a default, since it is published in
the README anyway. The application still boots without either, because seeding is a
separate command rather than a startup hook — which is also what the "not only at startup"
criterion is protecting: a boot-time side effect runs on every container start, including
ones that are only being health-checked.

**Reseeding does not overwrite an existing demo account.** If a judge has been clicking
around, resetting the account underneath them mid-session would be more confusing than
leaving it alone. Starting over is a database reset, which is a decision for a human
rather than a side effect of deploying.

**Safety beside real data is structural.** There is no truncate, no reset, and no "clean
first" step. The seed selects one account by email and touches nothing else — there is a
test that a separately registered student's profile is byte-for-byte unchanged afterwards.

**The seeded profile only claims what the resume evidences.** Every skill in
`DEMO_PROFILE` appears in the fictional resume the same account is seeded with. A demo
account asserting skills its own resume cannot support would be a live example of the
thing ADR 0006 exists to prevent, sitting on the page a judge opens first.

**The demo resume moved out of the test package.** It is used by the demo parser and by
the seed, which makes it a product asset; app code importing from `app.tests` would be
backwards. It now lives at `app/adapters/fixtures/demo_resume.pdf`, and the two
overfitting variants stay under tests where they belong.

## TDD discipline

One slice, properly red: collection failed on `No module named 'app.seed'`, then 8 tests
went green. No test passed on its first run, and no spurious pass this time — the
`created is True` / `created is False` pair could not have passed against a missing
module.
