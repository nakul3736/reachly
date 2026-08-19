"""Lever boards.

`api.lever.co/v0/postings/{token}?mode=json`, keyless. Spike 001 reached only 3 of 20 plausible
slugs, which is why the board registry exists rather than company names being turned into URLs
at runtime.

Two things differ from every other provider here. The response is a **bare JSON array** rather
than an object with a `jobs` key, and `createdAt` is **epoch milliseconds**. Passed to a
seconds-based parser that timestamp lands in the year 58,000; read as ISO it fails and the
posting looks undated.
"""

from datetime import UTC, datetime
from typing import Any

from app.domain.job_posting import RawPosting

SOURCE = "lever"


def parse_lever_board(
    payload: list[dict[str, Any]], *, company_name: str
) -> list[RawPosting]:
    postings: list[RawPosting] = []

    for job in payload or []:
        title = (job.get("text") or "").strip()
        apply_url = (job.get("hostedUrl") or job.get("applyUrl") or "").strip()
        job_id = job.get("id")

        if not title or not apply_url or not job_id:
            continue

        categories = job.get("categories") or {}

        postings.append(
            RawPosting(
                source=SOURCE,
                source_job_id=str(job_id),
                company_name=company_name,
                title=title,
                description=_description(job),
                apply_url=apply_url,
                location_raw=_location(categories),
                posted_at=_from_epoch_millis(job.get("createdAt")),
            )
        )

    return postings


def _location(categories: dict[str, Any]) -> str | None:
    """Lever keeps location inside `categories`, sometimes as a list of several.

    All of them are joined rather than the first being taken, because a posting open in Toronto
    and New York is one the student should see under either — and `location_raw` is displayed as
    written, so dropping the rest would hide part of the offer.
    """
    all_locations = categories.get("allLocations")
    if isinstance(all_locations, list) and all_locations:
        joined = ", ".join(str(item).strip() for item in all_locations if str(item).strip())
        if joined:
            return joined

    single = categories.get("location")
    return str(single).strip() if single else None


def _description(job: dict[str, Any]) -> str:
    """Lever splits a posting into an opening blurb and the substance.

    `descriptionPlain` is the introduction; `additionalPlain` carries responsibilities and
    requirements. Storing only the first leaves out what a student needs to decide, and what
    feature 04 has to tailor against.
    """
    parts = [
        str(job.get("descriptionPlain") or "").strip(),
        str(job.get("additionalPlain") or "").strip(),
    ]
    return "\n\n".join(part for part in parts if part)


def _from_epoch_millis(value: object) -> datetime | None:
    """Milliseconds since the epoch, as Lever sends them.

    Guarded by a plausibility check rather than trusted: a value already in seconds would
    otherwise produce a date in 1970, which is silently wrong instead of loudly wrong.
    """
    if not isinstance(value, int | float) or value <= 0:
        return None
    try:
        parsed = datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return parsed if 2000 < parsed.year < 2100 else None
