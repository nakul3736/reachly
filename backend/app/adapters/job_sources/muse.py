"""The Muse.

`themuse.com/api/public/jobs?page=N&level=Entry%20Level`, keyless.

This is the source the product needs most, and the least trustworthy one it has. Spike 001
measured **96.7% entry-level density** here against 2.8% on company boards — so this is where a
graduating student's openings actually are. But The Muse is an aggregator: it does not own the
posting, it does not enumerate a complete set, and it does not remove a job promptly when the
role closes. Everything from here is therefore stored **unverified**, expires on a timer rather
than being swept by absence, and loses to a company board record during dedup.

Its entry-level filter is also not a software filter. The first result on page one is a
Securitas security officer, which is genuinely entry level and genuinely useless to a
graduating developer — which is why the role-family classifier does the second half of the job.
"""

from datetime import UTC, datetime
from typing import Any

from app.domain.job_posting import RawPosting
from app.domain.markup import html_to_text

SOURCE = "muse"

# Bounded deliberately. The API reports 4,493 pages, which is roughly ninety thousand postings —
# far more than a free host can ingest in a request window, and most of them irrelevant to this
# product. Pages are ordered newest first, so a bounded read gets the freshest slice.
MAX_PAGES = 12


def parse_muse_page(payload: dict[str, Any]) -> list[RawPosting]:
    postings: list[RawPosting] = []

    for job in payload.get("results") or []:
        # The title is `name` here, not `title`.
        title = (job.get("name") or "").strip()
        job_id = job.get("id")

        company = job.get("company") or {}
        company_name = str(company.get("name") or "").strip()

        refs = job.get("refs") or {}
        apply_url = str(refs.get("landing_page") or "").strip()

        if not title or not job_id or not company_name or not apply_url:
            continue

        postings.append(
            RawPosting(
                source=SOURCE,
                source_job_id=str(job_id),
                company_name=company_name,
                title=title,
                description=html_to_text(str(job.get("contents") or "")),
                apply_url=apply_url,
                location_raw=_locations(job),
                posted_at=_parse_timestamp(job.get("publication_date")),
                # An aggregator's copy, never presented as the employer's own statement.
                is_verified=False,
                seniority_hint=_level(job),
            )
        )

    return postings


def _locations(job: dict[str, Any]) -> str | None:
    """Locations arrive as a list of objects, each with a `name`."""
    raw = job.get("locations")
    if not isinstance(raw, list):
        return None

    names = [
        str(item.get("name") or "").strip()
        for item in raw
        if isinstance(item, dict) and item.get("name")
    ]
    return ", ".join(names) or None


def _level(job: dict[str, Any]) -> str | None:
    """The Muse states the experience level, and its claim beats our inference.

    `Security Officer` contains no seniority word, so reading the title returns unknown while
    the source is explicitly saying entry level. Discarding that would throw away the one thing
    this provider is genuinely better at than the company boards.

    Only entry is taken. A senior claim from an aggregator is not needed — the title rules catch
    those, and they are not what this source is here for.
    """
    levels = job.get("levels")
    if not isinstance(levels, list):
        return None

    for item in levels:
        if not isinstance(item, dict):
            continue
        short = str(item.get("short_name") or "").strip().lower()
        name = str(item.get("name") or "").strip().lower()
        if short == "entry" or name == "entry level":
            return "entry"
    return None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
