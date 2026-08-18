# 02 — The job index

## Problem statement

A new graduate looking for their first role has no good place to look.

Company career pages carry the real posting and the full description, but there are tens of
thousands of them and no way to search across them. Checking them by hand is the thing
nobody sustains past the second week.

The aggregators that do offer search have three failures that cost real time. They list
jobs that were filled weeks ago, because nothing removes a posting once it stops existing —
so applications go into a role that closed before the student found it. They list the same
job four times, once per site that syndicated it, so a feed of twenty rows is eight jobs.
And they lose the description, leaving a title and a link, which is not enough to decide
whether a role is worth an hour of tailoring.

Spike 001 measured a fourth problem that is specific to this user. On company ATS boards,
**under 3% of postings are entry-level**, and the ones that are skew heavily to Bengaluru,
Mexico City and Singapore, and to titles like Administrative Coordinator. A feed built by
pointing at company boards and showing whatever comes back is, for a graduating software
student in Canada, almost entirely noise.

## Solution

One shared index, built once and read by every student, rather than each student's session
fetching jobs on demand.

It draws from two kinds of source that fail in opposite directions, deliberately. Company
ATS boards — Greenhouse, Lever, Ashby — are **authoritative**: the company publishes them,
they carry the full description, and a posting disappearing from them is trustworthy
evidence the role is gone. The Muse is an **aggregator**, less authoritative, but spike 001
measured 96.7% entry-level density against under 3% on the boards, so it is where the roles
this product exists for actually are.

Three rules make the index worth trusting:

**A posting that vanishes from its board is closed.** Not hidden, not left to rot — marked
closed with a date, dropped from the feed, and kept so that an application made against it
still resolves.

**One row per real job.** The same role on a board and an aggregator collapses to a single
entry, with the board's copy kept as the truth and the aggregator's as an alias.

**Every row says where it came from and whether the company confirmed it.** A job seen on a
company's own board and a job seen only on an aggregator are not the same claim, and the
feed does not pretend otherwise.

## User stories

1. As a graduating student, I want one feed of openings drawn from many companies, so that I
   do not have to visit dozens of career pages to find out nothing has changed.
2. As a graduating student, I want to see only roles in countries where I am allowed to work,
   so that I do not spend an evening on a posting I could never accept.
3. As a graduating student, I want to see only roles in the kind of work I do, so that
   Administrative Coordinator does not sit between two engineering roles in my feed.
4. As a graduating student, I want to see only roles open to someone with little experience,
   so that I am not reading a Staff Engineer description wondering if I could stretch.
5. As a graduating student, I want to know when a job was posted, so that I can spend my
   effort on the ones where I am early rather than four hundredth.
6. As a graduating student, I want jobs that have been filled to leave my feed, so that I
   never write a tailored application for a role that closed last month.
7. As a graduating student, I want a job listed on four sites to appear once, so that a feed
   of twenty rows is twenty opportunities.
8. As a graduating student, I want to know which source each job came from, so that I can
   judge how much to trust it.
9. As a graduating student, I want to know whether a posting is confirmed on the company's
   own board or was only seen on an aggregator, so that I know whether it might already be
   stale.
10. As a graduating student, I want to read the full description inside Reachly, so that I
    can decide whether to apply without opening six tabs.
11. As a graduating student, I want a link to the original posting, so that I apply through
    the company's real process and my application actually arrives.
12. As a graduating student, I want to filter by location, so that I can separate roles I
    can commute to from roles that would mean moving.
13. As a graduating student, I want to find remote roles specifically, so that location stops
    being a constraint when it does not have to be.
14. As a graduating student, I want to search by keyword, so that I can find the roles
    mentioning a technology I actually know.
15. As a graduating student, I want to see how many jobs match my filters, so that I know
    whether to widen them.
16. As a graduating student, I want an empty result to tell me which filter emptied it, so
    that I can fix it instead of assuming Reachly is broken.
17. As a graduating student, I want the feed paginated, so that it stays usable when there
    are two thousand matches.
18. As a graduating student, I want to know when Reachly last checked each source, so that I
    can tell whether I am looking at today's jobs or last week's.
19. As a graduating student, I want a single company's forty openings not to bury everyone
    else's, so that the feed stays worth scrolling.
20. As a graduating student, I want to open a job and see everything known about it on one
    screen, so that deciding to apply does not require assembling information myself.
21. As a graduating student, I want a job's location shown as the posting wrote it, so that I
    am not misled by a tidy-up that guessed wrong.
22. As a returning student, I want jobs I have already seen to be distinguishable from new
    ones, so that checking back is quick.
23. As the operator, I want the set of company boards to be data rather than code, so that
    adding a company does not require a deployment.
24. As the operator, I want a board that starts failing to be retried and then backed off, so
    that one dead company does not consume the whole refresh window every day.
25. As the operator, I want one failing source not to abort the run, so that a Lever outage
    does not cost us Greenhouse, Ashby and The Muse as well.
26. As the operator, I want ingestion to be idempotent, so that re-running a refresh after a
    crash does not double every job.
27. As the operator, I want the refresh driven by an external trigger, so that it still runs
    on a host that suspends idle processes.
28. As the operator, I want to see how many jobs each source contributed and when it last
    succeeded, so that a silently broken adapter is visible rather than merely quiet.
29. As the operator, I want closed jobs kept rather than deleted, so that a student's
    application history does not develop holes.
30. As the operator, I want an expensive duplicate verdict cached permanently, so that we
    never pay twice to answer the same question.
31. As the operator, I want duplicate detection to fall back to treating jobs as distinct
    when inference is unavailable, so that the feed degrades to slightly redundant rather
    than to broken.
32. As the operator, I want aggregator-only rows to expire, so that unverified postings do
    not accumulate into the exact stale feed this product exists to replace.

## Out of scope

**Matching and scoring** — feature 03. This feature gets jobs into the index and onto a
screen; it does not rank them against a student. The feed is ordered by recency until
scoring exists.

**Tailoring and outreach** — features 04 and 05.

**LinkedIn and Indeed** — ADR 0001. Not a scope decision, a permanent one.

**JSearch** — verified at roughly 200 requests per *month*, which cannot support a refresh
loop. Reconsider only as a manual gap-filler.

**Salary data.** Present on some sources, absent on most, and inconsistent where present.
Showing it for a minority of rows invites comparison between numbers that are not
comparable.

**Company enrichment** — logos, headcount, funding. Pleasant, and none of it helps a student
decide whether to apply.

**Job alerts and email digests.** Requires a sending domain, which ADR 0004 already ruled
out for outreach.

**The demand heatmap and skill roadmap** — cut during design. The roadmap invented URLs and
fabricated hours-to-learn figures, which is the failure mode ADR 0006 exists to prevent.

**Full-text relevance search.** Keyword filtering is a substring match over title and
description. BM25 arrives in feature 03 as a scoring component, where it belongs.
