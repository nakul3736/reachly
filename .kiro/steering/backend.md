# Backend steering

FastAPI · Python 3.13 · SQLAlchemy 2.0 · Alembic · PostgreSQL

## Layout

```
backend/app/
  main.py            FastAPI app, router registration, lifespan
  config.py          Settings via pydantic-settings, env-driven
  db.py              Engine, session factory, Base
  models/            SQLAlchemy models, one module per aggregate
  schemas/           Pydantic request/response models
  api/               Routers, one module per resource
  services/          Business logic — no FastAPI imports here
  adapters/          External boundaries (llm, jobs, contacts, verify)
  fixtures/          Recorded responses for DEMO_MODE
  tests/
```

Rule: `services/` never imports from `api/`, and never imports FastAPI. Business
logic must be callable from a test or a script without an HTTP layer.

## Adapters and DEMO_MODE

Every external dependency sits behind an interface in `adapters/` with at least two
implementations: the real one, and a fixture one that replays recorded JSON.

`DEMO_MODE=true` selects fixtures for all of them. This is not test scaffolding —
it is how judges run the project with no API keys, so it must stay working. Any new
external call requires a fixture in the same commit.

Adapters return domain objects, never raw provider payloads. A provider's response
shape must not reach `services/`.

Adapter failures raise `AdapterError` subclasses. Services decide the fallback;
adapters never silently return empty results, because an empty list and a failed
call are different things to the user.

## Database

SQLAlchemy 2.0 declarative with `Mapped[]` annotations. Every schema change gets an
Alembic migration in the same commit — never `create_all` outside tests.

Timestamps are `timezone=True` and stored UTC. Naive datetimes are a bug.

Postgres-specific types are used deliberately: `JSONB` for parsed resumes and
provenance maps, `ARRAY` for skills and locations. This is why local development
runs Postgres rather than SQLite.

Connection pool is sized conservatively — the hosted free tier's connection limit
is undocumented. See ADR 0008.

## API conventions

Plural resource paths, `/api/v1` prefix. Response models declared explicitly on
every route; never return an ORM object directly.

Errors use a consistent envelope with a stable machine-readable `code`, because the
frontend distinguishes "no results" from "provider unavailable" in the interface.

Pagination is limit/offset with a returned total.

## Async

Route handlers are `async`. Outbound HTTP uses a shared `httpx.AsyncClient` from
app state — never a client per request. Blocking work (PDF parsing, `.docx`
generation) goes through `run_in_threadpool`.

## Money and quota discipline

External calls that consume a metered quota are cached in Postgres, and the cache
is checked before the call. Aggregator job search is never invoked on a page render
— only from a scheduled or explicit refresh. See ADR 0005.

## Security

Passwords hashed with bcrypt via passlib. JWT in an `Authorization` header.
Settings come from the environment with no defaults for secrets. Never log a
request body containing a password, token, or a third party's email address.

`/internal/*` routes require a shared secret and return 404 on mismatch, so they
are not discoverable. See ADR 0007.

## Testing

pytest with `httpx.AsyncClient` against the app. Tests run with `DEMO_MODE=true`
and must never touch the network — a test that fails without internet is a broken
test. Deterministic logic (scoring, normalisation, dedup, the provenance
validator) is unit-tested directly, and the validator gets adversarial cases.
