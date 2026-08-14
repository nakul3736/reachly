# 03 — Student profile

**What to build:** a student says what they are looking for — target role, locations,
years of experience, and the skills they already have — reads it back, and changes it
later. Another account cannot see it.

**Blocked by:** 02 — needs an authenticated user to own the profile.

**Status:** ready-for-agent

- [ ] A student row is created when a user registers, so there is never an
      authenticated user without a profile to write to
- [ ] The current student's profile can be read
- [ ] Target role, locations, years of experience, and skills can be updated
- [ ] Locations accept more than one value, so a student can search a city and remote
      roles together
- [ ] A partial update leaves unsupplied fields unchanged, so editing one field does not
      silently clear the others
- [ ] Years of experience rejects negative and implausibly large values
- [ ] Empty strings in locations or skills are rejected or normalised away rather than
      stored, so they cannot become a filter matching nothing
- [ ] The response states which fields are still missing for results to be useful
- [ ] Profile routes act on the authenticated student, with no id in the path
- [ ] One student cannot read or modify another student's profile
- [ ] `ruff check` and `mypy` pass
