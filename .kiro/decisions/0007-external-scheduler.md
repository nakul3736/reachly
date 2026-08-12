# 0007 — The daily job runs from an external trigger

Status: Accepted · 2026-08-11

## Context

Follow-up drafting needs something to notice that five or ten days have passed
since an application was sent. No user action coincides with that moment — the
student may not open Reachly for a week.

The original specification used APScheduler inside the FastAPI process, on the
reasoning that it needs no extra infrastructure. That reasoning holds on a server
that is always running. It does not hold on free hosting, where the process is
stopped during inactivity. A timer inside a stopped process does not fire, and
does not report that it failed to fire. Follow-ups would simply never appear.

The nightly job-board refresh in [0005](0005-shared-job-index.md) has the same
requirement.

## Decision

Scheduled work is exposed as `POST /internal/cron/{task}`, authenticated by a
shared secret, and invoked by an external scheduler. Two independent triggers are
configured — a GitHub Actions scheduled workflow and cron-job.org — because
GitHub's cron can be delayed well past its nominal time under load.

Handlers are idempotent. Duplicate invocation is expected, not exceptional, and
running the follow-up sweep twice in a day must not produce two drafts.

The same request keeps the service awake, so one mechanism covers both the
scheduled work and the keep-alive that free hosting requires.

## Rejected

**APScheduler in-process.** Silently stops when the process is stopped.

**Both, with APScheduler locally and cron in production.** Two code paths for one
behaviour, and it hides the failure: the developer sees follow-ups working every
time while production quietly does nothing.

**A separate always-on worker process.** Correct at scale, and unjustified here —
it doubles the hosting requirement to run a few seconds of work per day.

## Consequences

- Every scheduled task is reachable by hand, which makes it testable and
  demonstrable rather than something that only happens overnight.
- The shared secret is configuration, never committed, and the endpoint returns
  404 rather than 401 on a bad secret so the route is not discoverable.
- The README documents that scheduled work needs an external trigger, so a judge
  running locally understands why nothing happens overnight and how to invoke it.
