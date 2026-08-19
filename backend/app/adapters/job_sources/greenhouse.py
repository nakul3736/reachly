"""Greenhouse boards.

`boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`, keyless. Verified by spike
001: ten of ten boards responded, 2,571 jobs, full descriptions with a median of 6,731
characters. There is no cross-company search, which is why the board registry exists.
"""

from datetime import UTC, datetime
from typing import Any

from app.domain.job_posting import RawPosting
from app.domain.markup import html_to_text

SOURCE = "greenhouse"


def parse_greenhouse_board(payload: dict[str, Any], *, company_name: str) -> list[RawPosting]:
    """Turn one board response into postings.

    `company_name` is passed in from the registry rather than read from the payload.
    Greenhouse does expose `company_name`, but it is the board owner's display name and
    differs from the name we registered often enough that trusting it would fragment the
    same employer across several spellings — which would break dedup, since fuzzy matching
    is scoped to one company.
    """
    postings: list[RawPosting] = []

    for job in payload.get("jobs") or []:
        title = (job.get("title") or "").strip()
        apply_url = (job.get("absolute_url") or "").strip()
        job_id = job.get("id")

        # Skipped rather than stored empty. A row with no title is unusable in a feed and
        # unrankable in feature 03, and it would still occupy a slot in both.
        if not title or not apply_url or job_id is None:
            continue

        postings.append(
            RawPosting(
                source=SOURCE,
                source_job_id=str(job_id),
                company_name=company_name,
                title=title,
                description=html_to_text(job.get("content") or ""),
                apply_url=apply_url,
                location_raw=(job.get("location") or {}).get("name"),
                posted_at=_parse_timestamp(job.get("first_published")),
            )
        )

    return postings


def _parse_timestamp(value: object) -> datetime | None:
    """Greenhouse sends offset-aware ISO 8601, for example `2024-11-01T06:05:10-04:00`.

    The offset is kept rather than normalised away, because a posting date is only useful
    relative to now and a naive datetime would be compared against an aware one somewhere
    downstream and raise.

    `first_published` rather than `updated_at`: Greenhouse touches `updated_at` on any edit,
    so a two-year-old requisition would present as posted today. Story 5 exists so a student
    can prioritise being early, and that field would actively mislead them.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
