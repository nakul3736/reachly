# 07 — Seeded demo student with a parsed resume

**What to build:** a documented account that already has a profile and a parsed master
resume, so anyone opening the project sees a populated product rather than an empty form.

Rule 17 requires judges to be given working test credentials, and Round One screening
rewards a project that demonstrably works on first contact.

**Blocked by:** 05 — needs parsing to seed a master resume. Independent of 06; the
fixture parser is sufficient.

**Status:** ready-for-agent

- [ ] Seeding is idempotent — running it twice does not duplicate the account or its
      resume versions
- [ ] The seeded student has a realistic new-graduate profile: target role, locations,
      years of experience, and skills
- [ ] The seeded student has an active master resume with parsed experience and bullets
- [ ] Seeded credentials come from configuration, not hardcoded, and the values used for
      the deployed demo are documented in the README
- [ ] Seeding is safe to run against a database that already has real data
- [ ] The seed can be invoked as a command, not only at startup, so redeploying does not
      depend on boot-time side effects
- [ ] `ruff check` and `mypy` pass

**Deferred from this feature:** the guest entry point that skips signup entirely. It
belongs with the job index — a guest door onto an empty feed demonstrates nothing.
