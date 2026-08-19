# Reachly

**A job application pipeline for new graduates in the US and Canada.** It finds relevant
openings, tailors a resume to a posting without inventing anything, works out who to contact,
drafts the outreach, and tracks what you sent.

Built for the Ready, Spec, Ship hackathon. Kiro wrote the code; the reasoning behind it is in
[`.kiro/`](.kiro/), which is the more interesting half of this repository.

- **Live app:** https://reachly-b4q.pages.dev
- **API:** https://reachly-api-82u2.onrender.com
- **Demo account:** `demo@reachly.app` / `reachly-demo-2026` — the sign-in screen fills these
  for you, so you never need to come back here for them

---

## The problem this solves

A graduating student's job search fails in four specific ways, and every one of them is a
measurement rather than an opinion.

**Company career pages hold the real posting and the full description, and there is no way to
search across them.** Greenhouse, Lever and Ashby serve thousands of boards with no
cross-company search, so checking them by hand is the thing nobody sustains past week two.

**The aggregators that do offer search list jobs that were filled weeks ago.** Nothing removes
a posting once the role stops existing, because a crawler cannot tell the difference between a
job being gone and its own request having failed.

**The same job appears four times**, once per site that syndicated it, so twenty rows are eight
opportunities.

**And almost nothing on those boards is for a new graduate.** We measured this rather than
assuming it: across 2,571 postings from ten well-known company boards, **2.8% were entry
level**, and those skewed heavily to Bengaluru, Mexico City and Singapore, and to titles like
Administrative Coordinator. Full findings in
[spike 001](.kiro/decisions/spike-001-job-source-coverage.md).

Then there is the part that actually costs a student their evening. Tailoring a resume by hand
takes an hour per application. Tailoring it with a general-purpose chatbot takes two minutes and
produces a resume containing things you did not do — a framework you never used, a percentage
you never measured — which you then either send, or spend twenty minutes auditing.

## What Reachly does differently

**It never presents a guess as a fact.** That single rule shapes every screen.

A posting on a company's own board and a posting seen only on an aggregator are different
claims, so they are labelled `confirmed` and `inferred` and never styled alike. A posting shows
both when it was published *and* when its board was last read, because a date alone cannot tell
you whether the role still exists. When a posting disappears from its board, it is marked closed
and dropped from the feed rather than left to rot.

**Tailoring is evidence-locked.** Every generated line is checked against your uploaded resume
before you ever see it, and anything that cannot be traced back to your own document is dropped.
The interface shows you the identifier of the bullet each rewrite came from. This is
[ADR 0006](.kiro/decisions/0006-evidence-locked-tailoring.md) and it is the reason this project
exists rather than a prompt.

**Matching is deterministic.** Skill overlap 40, experience fit 30, keyword relevance 20,
freshness 10 — arithmetic, not a model's opinion, and every score is shown with its four parts
rather than as a bare number you have to trust.
([ADR 0003](.kiro/decisions/0003-deterministic-scoring-over-llm.md))

---

## Trying it

### The fastest path

Open https://reachly-b4q.pages.dev, click **Sign in**, then **Fill the demo credentials**. The
demo account already has a profile and a parsed resume, so every screen has real content.

The API sleeps when idle on the free tier. **The first request can take up to a minute** while
the container wakes; the interface says so rather than showing a spinner forever.

### What to look at

**The feed** is public — browsing jobs needs no account. It currently holds real openings pulled
from ten live company boards. Try the **open to graduates** and **technical roles** toggles
together: they take the index from thousands of postings to the small number a graduating
software student could actually apply to. Each toggle's tooltip states exactly what it excludes,
because a filter that silently reshapes your feed is worse than no filter.

Notice the small monospace line along the bottom of every card. That is the receipt: the source,
the posting's age, and when that board was last read.

**The profile screen** shows what Reachly read out of the demo resume. The grey hash under each
bullet is derived from that bullet's own text, and it is what tailored output resolves back
against. Dates appear exactly as the resume wrote them — `Aug 2023` is not tidied into
`August 2023`, because normalising is itself a small invention.

Upload your own resume if you like. Failures are advised separately: a scan needs re-exporting, a
`.docx` renamed to `.pdf` needs converting, and the interface says which.

---

## Running it locally

**You need** Python 3.13+, Node 20+, and Docker. No API keys are required — Reachly runs in demo
mode by default, which serves recorded model responses through the real parsing code.

```bash
git clone https://github.com/nakul3736/reachly.git
cd reachly

# 1. Postgres
docker compose up -d          # postgres:17-alpine on port 55432

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"
cp .env.example .env          # works as-is for local development
alembic upgrade head
python -m app.seed            # registers the job boards and the demo account
uvicorn app.main:app --reload  # http://127.0.0.1:8000
```

```bash
# 3. Frontend, in a second terminal
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

The dev server proxies `/api` to the backend, so no frontend configuration is needed.

`python -m app.seed` needs `DEMO_STUDENT_EMAIL` and `DEMO_STUDENT_PASSWORD` in your `.env` to
create the demo account. Board registration happens either way.

### Filling the job index

The seed registers eighteen real company boards but does not fetch from them. To pull live
postings:

```bash
curl -X POST http://127.0.0.1:8000/internal/cron/refresh-jobs \
  -H "X-Cron-Secret: $CRON_SECRET"
```

This reads every registered board, normalises the postings, classifies them, and folds them into
the index. Expect a few thousand jobs and about a minute. The endpoint returns **404** rather
than 401 when the secret is wrong, and fails closed when it is unset — an unauthenticated
endpoint should not announce that it exists.

### Running the tests

```bash
cd backend
pytest -q                     # ~290 tests
ruff check . && mypy app
```

Two groups of tests skip by default, each naming the variable that enables it:

| Variable | What it unlocks |
|---|---|
| `REACHLY_REAL_RESUME_PDF` | Parses a real resume from **outside** the repository. This project is public and a real resume carries a name, phone number and email address, so it is never committed and these tests assert structure only, never content. |
| `GEMINI_LIVE_TESTS=1` plus `GEMINI_API_KEY` | Calls the real model. Two variables rather than one, so having a key configured does not silently start spending quota on every test run. |

---

## How it is built

```
backend/          FastAPI · SQLAlchemy 2 async · Alembic · Postgres 17
frontend/         React 19 · TypeScript · Vite · Tailwind 4 · TanStack Query
.kiro/            steering, decisions, specs — the reasoning
```

**Layering that is enforced rather than aspirational.** `services/` never imports FastAPI or
anything from `api/`; adapters never import services; domain logic is pure functions with no
database access. Provider-specific awkwardness stays inside one small adapter module each.

**Three test seams, chosen deliberately and no more.** The inbound HTTP API, the `ResumeParser`
protocol, and the outbound HTTP transport. A fourth was rejected on purpose: a `JobSource`
protocol with a fixture implementation would have replaced the provider-JSON normalisation that
is the likeliest thing in this codebase to be wrong. Substituting at the transport instead means
that code always runs for real, including in demo mode.

That lesson was learned the hard way. An earlier fixture resume parser returned a finished
result and skipped extraction, evidence checking and identifier derivation — so anyone running
in demo mode was exercising a different program from production. It was deleted.

### Deployment

Cloudflare Pages, Render free tier, and Aiven free Postgres — chosen for surviving a fixed
judging window rather than for elegance. Render's own free Postgres is **deleted after 30 days**,
which would have removed the database mid-judging.
([ADR 0008](.kiro/decisions/0008-hosting-for-a-judged-window.md))

The daily refresh runs from an **external** trigger, because Render suspends idle processes and
an in-process timer would stop silently. Silently is the problem.
([ADR 0007](.kiro/decisions/0007-external-scheduler.md))

The deployed instance runs in demo mode. Ordinary development exhausted a day's free model quota
in an afternoon, and a reviewer who uploads a resume and reads "the service is busy" has seen the
product fail. Demo mode runs the real parser with only the single inference call recorded, so the
evidence check, the identifier derivation and every classification still execute.
([ADR 0010](.kiro/decisions/0010-demo-mode-is-the-deployed-default.md))

---

## `.kiro/` — how this was actually built

The interesting part of this repository is not the code.

### [`.kiro/decisions/`](.kiro/decisions/) — 10 ADRs and 2 spikes

Written when each decision was made, not reconstructed afterwards, and each records what was
**rejected** and why. Several reversed the original product plan:

| | |
|---|---|
| [0001](.kiro/decisions/0001-no-linkedin-scraping.md) | **LinkedIn was cut entirely.** The API that made the original plan possible breaches LinkedIn's user agreement, and LinkedIn litigates — it killed Proxycurl in July 2025. The GitHub API is excluded too: its privacy statement forbids using profile data to email people. |
| [0002](.kiro/decisions/0002-kiro-is-not-the-inference-backend.md) | Kiro built this; it does not run inside it. |
| [0003](.kiro/decisions/0003-deterministic-scoring-over-llm.md) | Matching is arithmetic, and every score is shown decomposed. |
| [0006](.kiro/decisions/0006-evidence-locked-tailoring.md) | Tailoring is provenance-checked and cannot invent experience. |
| [0010](.kiro/decisions/0010-demo-mode-is-the-deployed-default.md) | Why the deployed app serves recorded inference. |

Two features from the original plan were **deleted during design** rather than shipped badly: a
skill roadmap that invented URLs and fabricated hours-to-learn figures, and a demand heatmap
that added no decision a student could act on.

### [`.kiro/steering/`](.kiro/steering/) — the standing rules

Product, backend, frontend and testing conventions that every ticket was held to, including the
design language: monospace for machine evidence, humanist sans for prose, and a score never
displayed as a bare number.

### [`.kiro/specs/`](.kiro/specs/) — requirements, design and tickets per feature

Every ticket records its acceptance criteria **and an honest note on what went wrong**,
including where test-driven discipline slipped and what that cost. A few worth reading:

- **[Feature 01, ticket 06](.kiro/specs/01-profile-and-resume/tickets/06-real-parser.md)** — the
  model returned 7 "skills" for a resume containing 46, because each was a whole category line
  like `Languages: Java, Python, SQL`. Skill overlap is 40% of the match score, so every score
  would have been wrong while everything looked fine.
- **[Feature 01, ticket 08](.kiro/specs/01-profile-and-resume/tickets/08-the-screens.md)** — a
  guard meant to prevent a blank deployed page became the cause of one. It threw at module
  scope, the bundler proved the condition statically, and eliminated the entire application as
  unreachable code. The build reported success.
- **[Feature 02, ticket 04](.kiro/specs/02-job-index/tickets/04-classification-and-filters.md)** —
  `Sr.` appears 205 times against `Senior` 513, and `CA` means Canada in `CA-Toronto` but
  California in `San Francisco, CA`.

---

## Status

Reachly is a hackathon build with a fixed deadline, so this is where it genuinely stands.

**Working:** accounts and profiles · resume upload, parsing and provenance · the shared job
index across live company boards · deterministic classification and filtering · the feed and job
detail screens.

**In progress:** additional job sources, closure detection, deduplication, match scoring,
evidence-locked tailoring, contacts and outreach drafting, application tracking.

## Licence

MIT. See [LICENSE](LICENSE).
