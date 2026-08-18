# 05 — Closure detection

**What to build:** dead postings leave the feed. When a board refresh succeeds, any job from
that board that is no longer listed is marked closed, dropped from the feed, and kept so that
an application made against it still resolves.

This is the rule that separates Reachly from the aggregators it exists to replace. Applying to
a role that closed weeks ago is the single most demoralising way to waste an evening, and no
aggregator prevents it because none of them can tell the difference between a job being gone
and their own crawler having a bad day.

**Full test rigour** — every guard below is a way to destroy the index, and each needs its own
test.

**Blocked by:** 02 — needs one source ingesting on a repeatable schedule. Does not need the
other three.

**Status:** ready-for-agent

- [ ] After a **successful** board fetch, non-closed jobs from that board absent from the
      response get `closed_at` set
- [ ] **A failed fetch closes nothing.** A 500, a timeout or a connection error is not
      evidence about any job. Treating an outage as mass closure would empty the feed
- [ ] **An empty response where there were previously many closes nothing**, and is recorded
      as suspicious. It is far more likely a changed API shape or a revoked token than every
      role at a company being filled at once
- [ ] One board's refresh never closes another board's jobs, or another source's
- [ ] A closed job is still retrievable by id, so history does not develop holes
- [ ] A closed job is excluded from the feed by default and reachable only when explicitly
      requested
- [ ] A job that reappears in a later refresh is **reopened** rather than duplicated — roles
      are reposted, and a second row for the same job would defeat ticket 06 before it starts
- [ ] `closed_at` records when absence was first observed, not when the sweep ran
- [ ] **Aggregator rows expire rather than being swept.** The Muse does not enumerate a
      complete set, so absence proves nothing about it. Unverified rows get a 14-day expiry
- [ ] Closure counts are reported per source, so a rule or adapter change that starts closing
      everything is visible immediately rather than after the feed empties
- [ ] The job detail screen shows a closed job as closed, with its date, rather than 404ing —
      a student who bookmarked it deserves to know what happened
