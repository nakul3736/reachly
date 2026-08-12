# 0008 — Hosting chosen for uptime across a fixed judging window

Status: Accepted · 2026-08-11

## Context

Reachly must be reachable, free, and responsive from 24 August to 5 September
2026 — a thirteen-day window during which judging happens and nobody is watching
the service. Rule 17 requires judges to be able to access a working demo free of
charge throughout that period.

The original specification chose Railway for backend and database, and Vercel for
frontend. Both have problems that only appear under this specific constraint.

Railway's free plan provides $1 per month of non-rollover credit. Managed Postgres
alone consumes roughly $0.67 per day, giving about a day and a half of runway
against thirteen days. Railway's free plan is also non-commercial only.

Vercel's Hobby plan states that "Hobby teams are restricted to non-commercial
personal use only," defining commercial usage as "any Deployment that is used for
the purpose of financial gain of anyone involved in any part of the production of
the project." An entry competing for a cash prize is at best ambiguous.

The most dangerous option was one not in the original plan: Render's free Postgres
is **deleted after 30 days**. Provisioned early, it would expire mid-judging,
returning connection errors at a time when no one is looking.

## Decision

| Layer | Service | Reason |
|---|---|---|
| Frontend | Cloudflare Pages | Unlimited bandwidth, no sleep, no commercial-use clause |
| Backend | Render free web service | 750 instance-hours/month against 312 needed |
| Database | Aiven free Postgres | Always on: no suspend, no pause, no expiry |
| Triggers | GitHub Actions + cron-job.org | Two independent schedulers |

Aiven is the load-bearing choice. Neon is otherwise excellent but autosuspends
after five minutes with a sub-second wake; Supabase pauses entirely after seven
days of inactivity. Aiven's free tier neither sleeps nor expires, which removes the
failure mode that cannot be observed while it is happening.

Render's free service does stop after fifteen minutes of inactivity with a 30–60
second cold start, which is why the keep-alive from
[0007](0007-external-scheduler.md) is a requirement rather than an optimisation,
and why there are two independent triggers.

Deployment happens on day two, against a near-empty application. Every subsequent
feature ships onto infrastructure already proven to work. The common failure is
deploying for the first time on the final night, when there is no time to react to
surprises.

## Rejected

**Railway plus Vercel as originally specified.** Credit exhaustion and a
non-commercial restriction, as above.

**Render's free Postgres.** Deleted after thirty days.

**Fly.io.** No longer offers a free tier, only a short trial.

**A single Oracle Cloud always-free VM.** Technically the best answer — no cold
start, no sleep, real cron — and rejected on schedule risk. Free ARM capacity is
frequently unavailable, and the fallback is hours of VM administration, reverse
proxy configuration, and certificate management during a twelve-day build.

## Consequences

- The database is a single connection string, so a provider swap is configuration
  rather than a rewrite. Aiven's free connection limit is undocumented, so the
  connection pool is sized conservatively and verified on first connect.
- The deployed demo carries a seeded account and a guest entry point so a judge
  reaches a working feed without signing up. Rule 17 requires working test
  credentials, so password login is also kept functional.
- A health endpoint exists for the keep-alive triggers to call cheaply, without
  touching the database on every ping.
