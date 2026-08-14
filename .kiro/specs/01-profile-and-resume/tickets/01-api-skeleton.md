# 01 — API skeleton with health and database connectivity

**What to build:** the API starts, reads its configuration from the environment,
connects to Postgres, and answers a health request that says whether the database is
actually reachable. Migration machinery exists and runs against an empty database.

This is the prefactor. Nothing else in this feature can land until there is a running
application to land it in.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Settings load from the environment with no default for any secret; a missing
      required setting fails at startup with a message naming the setting
- [x] `GET /api/v1/health` returns a success status and reports database reachability
      as a distinct field, so a running API with a dead database is not reported healthy
- [x] The health check does not query application tables, so it stays cheap enough for
      the keep-alive triggers in ADR 0007 to call every ten minutes
- [x] An async SQLAlchemy engine and session factory exist, with a conservatively sized
      pool per ADR 0008
- [x] Alembic is initialised and configured to read the database URL from settings, with
      a baseline revision that applies cleanly to an empty database
- [x] `alembic upgrade head` and `alembic downgrade base` both succeed
- [x] Tests run against the ASGI app with `DEMO_MODE=true` and touch no network
- [x] `ruff check` and `mypy` pass

## Notes from implementation

**Health always answers 200.** A degraded database is reported in the body as
`status: degraded, database: down` rather than as a 5xx. The keep-alive pinger should
not treat a database problem as the service being down, and a human reading the body
learns more than a status code would tell them.

**Engine disposal was forced by the tests, and kept for production.** pytest-asyncio
gives each test a new event loop, and an asyncpg connection cannot outlive the loop it
was opened on — the first database test failed with `RuntimeError: Event loop is
closed`. `dispose_engine()` fixes that, and is also wired into FastAPI's lifespan
because the deployment target has a low connection ceiling and a leaking pool would
exhaust it after a few redeploys.

**The Alembic script template was rewritten.** The generated default produced ten lint
errors, so `script.py.mako` now emits modern union syntax and sorted imports. Future
revisions are lint-clean on generation rather than needing a fix pass each time.

**Two tests here were not genuinely test-first.** `test_config.py` passed on first run,
because making a pydantic-settings field required is automatic once it has no default —
the behaviour already existed from the previous slice. They are kept as a contract
lock, but they characterise rather than drive.

**`DEMO_MODE` defaults to true.** Forgetting to set it cannot cause the application to
start reaching for API keys it does not have. The keyless path is the default and the
opt-out is explicit.
