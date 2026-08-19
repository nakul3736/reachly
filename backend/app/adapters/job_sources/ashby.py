"""Ashby boards.

`api.ashbyhq.com/posting-api/job-board/{token}`, keyless. Spike 001 reached 6 of 6.

Ashby is the most cooperative of the four providers: it supplies `descriptionPlain` already
stripped, and states `isRemote` rather than leaving it to be read out of prose.
"""

from datetime import UTC, datetime
from typing import Any

from app.domain.job_posting import RawPosting
from app.domain.markup import html_to_text

SOURCE = "ashby"


def parse_ashby_board(payload: dict[str, Any], *, company_name: str) -> list[RawPosting]:
    postings: list[RawPosting] = []

    for job in payload.get("jobs") or []:
        # `isListed: false` means the employer has taken the posting down while the API still
        # returns it. Storing it would put a withdrawn role in the feed, which is the exact
        # failure closure detection exists to prevent — no reason to create it on the way in.
        if job.get("isListed") is False:
            continue

        title = (job.get("title") or "").strip()
        apply_url = (job.get("jobUrl") or job.get("applyUrl") or "").strip()
        job_id = job.get("id")

        if not title or not apply_url or not job_id:
            continue

        postings.append(
            RawPosting(
                source=SOURCE,
                source_job_id=str(job_id),
                company_name=company_name,
                title=title,
                description=_description(job),
                apply_url=apply_url,
                location_raw=_location(job),
                posted_at=_parse_timestamp(job.get("publishedAt")),
                # Taken from the provider rather than inferred. A posting Ashby marks remote
                # with a location of "Europe" would read as not remote if we guessed from the
                # text, and the provider's own statement is better evidence than our regex.
                is_remote_hint=(
                    job["isRemote"] if isinstance(job.get("isRemote"), bool) else None
                ),
            )
        )

    return postings


def _location(job: dict[str, Any]) -> str | None:
    primary = str(job.get("location") or "").strip()

    secondary = job.get("secondaryLocations")
    extras: list[str] = []
    if isinstance(secondary, list):
        for item in secondary:
            # Ashby sends these as objects in some responses and strings in others.
            name = item.get("location") if isinstance(item, dict) else item
            text = str(name or "").strip()
            if text and text != primary:
                extras.append(text)

    joined = ", ".join([part for part in [primary, *extras] if part])
    return joined or None


def _description(job: dict[str, Any]) -> str:
    """Prefer the plain text Ashby already provides.

    Falling back to stripping the HTML only when it is absent, rather than always stripping,
    because the provider's own plain rendering keeps list structure our stripper has to
    reconstruct.
    """
    plain = str(job.get("descriptionPlain") or "").strip()
    if plain:
        return plain
    return html_to_text(str(job.get("descriptionHtml") or ""))


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
