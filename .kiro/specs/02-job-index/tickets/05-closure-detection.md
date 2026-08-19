# 05 â€” Closure detection

**What to build:** dead postings leave the feed. When a board refresh succeeds, any job from
that board that is no longer listed is marked closed, dropped from the feed, and kept so that
an application made against it still resolves.

This is the rule that separates Reachly from the aggregators it exists to replace. Applying to
a role that closed weeks ago is the single most demoralising way to waste an evening, and no
aggregator prevents it because none of them can tell the difference between a job being gone
and their own crawler having a bad day.

**Full test rigour** â€” every guard below is a way to destroy the index, and each needs its own
test.

**Blocked by:** 02 â€” needs one source ingesting on a repeatable schedule. Does not need the
other three.

**Status:** done

- [x] After a **successful** board fetch, non-closed jobs from that board absent from the
      response get `closed_at` set
- [x] **A failed fetch closes nothing.** A 500, a timeout or a connection error is not
      evidence about any job. Treating an outage as mass closure would empty the feed
- [x] **An empty response where there were previously many closes nothing**, and is recorded
      as suspicious. It is far more likely a changed API shape or a revoked token than every
      role at a company being filled at once
- [x] One board's refresh never closes another board's jobs, or another source's
- [x] A closed job is still retrievable by id, so history does not develop holes
- [x] A closed job is excluded from the feed by default and reachable only when explicitly
      requested
- [x] A job that reappears in a later refresh is **reopened** rather than duplicated â€” roles
      are reposted, and a second row for the same job would defeat ticket 06 before it starts
- [x] `closed_at` records when absence was first observed, not when the sweep ran
- [x] **Aggregator rows expire rather than being swept.** The Muse does not enumerate a
      complete set, so absence proves nothing about it. Unverified rows get a 14-day expiry
- [x] Closure counts are reported per source, so a rule or adapter change that starts closing
      everything is visible immediately rather than after the feed empties
- [x] The job detail screen shows a closed job as closed, with its date, rather than 404ing â€”
      a student who bookmarked it deserves to know what happened

## Notes from implementation

**The sweep needed a new column before it could be safe.** Deciding "was this posting in the
response we just got?" cannot be scoped by `source`: Figma and Linear are both Greenhouse, and
neither appears in the other's response, so Figma's refresh would have closed Linear's entire
listing. Scoping by `company_name` fails differently — a firm running a second board for a
region or subsidiary would have each board close the other. `jobs.board_token_id` is the only
thing that answers the question, and both failure modes have their own test.

Rows created before the column existed are backfilled on their next successful refresh rather
than in the migration. A migration cannot tell which of two same-provider boards produced a given
row, and guessing would mis-scope the very sweep the column exists to make safe.

**`closed_at` is written only where it is null.** Otherwise every subsequent sweep moves the date
forward and a role closed three weeks ago reads as closed today, forever. The test asserts the
timestamp survives a second sweep, and that the second sweep reports zero closures rather than
re-closing what was already closed.

**Two 200 responses mean different things.** An empty list from a board that has open jobs is
recorded as suspicious and closes nothing — it is the shape a provider returns for a deleted
board, a rotated token, and an adapter that stopped matching the payload. An empty list from a
board that never had postings is a company with no openings, which is normal and must not be
flagged forever. Distinguishing them is one query and it is the difference between a useful
warning and an alert nobody reads.

**The aggregator expires instead of being swept, and verified rows never expire.** The Muse is
read a bounded number of pages deep, so a posting missing today may have moved to page thirteen.
A timer makes the weaker, honest claim: not that this job is gone, but that an unverified copy
nobody has re-seen in fourteen days is no longer worth an evening. A board posting open for six
months is still open, and its board says so every day — the test asserts a twenty-day-old
verified row stays open while a twenty-day-old aggregator row does not.

**Honest note on process.** The tests were written first and red was observed as an ImportError,
but this was one large batch rather than slice-by-slice red-green. Several tests passed the moment
the implementation landed, which means they are regression guards rather than tests that drove the
design. The design pressure here came from the ticket itself, which enumerated the failure modes
before any code existed — that is where the thinking happened, and it is why `board_token_id`
appeared before the first sweep ran rather than after it emptied a feed.

The frontend criterion was already satisfied: the job detail screen was built with the closed
state during ticket 02, using the `closed` token rather than an error state.