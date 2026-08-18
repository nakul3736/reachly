# Production image for the Reachly API.
#
# Multi-stage so the runtime image carries no build toolchain. Slim rather than alpine:
# asyncpg and pdfplumber pull in C extensions, and alpine's musl means compiling them
# from source, which is slower to build and a different libc from what they are tested
# against.

FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Dependencies are installed from pyproject alone first, so this layer is reused when
# only application code changes.
COPY pyproject.toml ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && mkdir -p app && touch app/__init__.py README.md \
    && /opt/venv/bin/pip install .


FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Runs as a non-root user. Nothing here needs to write outside the app directory, and
# the deployment target has an ephemeral filesystem anyway — uploads go to Postgres.
RUN useradd --create-home --shell /usr/sbin/nologin reachly

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=reachly:reachly alembic.ini ./
COPY --chown=reachly:reachly migrations ./migrations
COPY --chown=reachly:reachly app ./app

USER reachly

EXPOSE 8000

# Render supplies $PORT. Migrations run in the start command rather than here, so a
# failed migration fails the deploy visibly instead of leaving a container that starts
# against the wrong schema.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
