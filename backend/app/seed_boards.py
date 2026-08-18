"""The curated set of company boards Reachly fetches.

These tokens are not guesses. Spike 001 probed every one of them against the live API:
Greenhouse returned 10 of 10, Ashby 6 of 6, and Lever only 3 of 20 plausible slugs — which
is the measurement that turned the registry from a nice-to-have into a requirement. A
company's board slug cannot be derived from its name, so it has to be stored.

A curated subset rather than the full ~63k-company dataset from `kalil0321/ats-scrapers`
(ADR 0009). The binding constraint is how long a refresh takes inside a free host's request
window, not how many rows Postgres can hold. Widening this list is a data change.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board_token import BoardToken


@dataclass(frozen=True)
class SeedBoard:
    provider: str
    token: str
    company_name: str


# Verified reachable by spike 001. Ten of ten responded.
_GREENHOUSE = [
    ("stripe", "Stripe"),
    ("airbnb", "Airbnb"),
    ("dropbox", "Dropbox"),
    ("coinbase", "Coinbase"),
    ("figma", "Figma"),
    ("databricks", "Databricks"),
    ("gitlab", "GitLab"),
    ("robinhood", "Robinhood"),
    ("instacart", "Instacart"),
    ("affirm", "Affirm"),
]

# Six of six responded.
_ASHBY = [
    ("openai", "OpenAI"),
    ("linear", "Linear"),
    ("vanta", "Vanta"),
    ("notion", "Notion"),
    ("cohere", "Cohere"),
    ("posthog", "PostHog"),
]

# Only the slugs spike 001 actually saw respond. Twelve of twenty guesses 404'd, so nothing
# goes in this list on the strength of a company being famous.
_LEVER = [
    ("matchgroup", "Match Group"),
    ("leverdemo", "Lever Demo"),
]

SEED_BOARDS: list[SeedBoard] = [
    *[SeedBoard("greenhouse", t, n) for t, n in _GREENHOUSE],
    *[SeedBoard("ashby", t, n) for t, n in _ASHBY],
    *[SeedBoard("lever", t, n) for t, n in _LEVER],
]


@dataclass
class BoardSeedResult:
    created: int
    already_present: int


async def seed_boards(session: AsyncSession) -> BoardSeedResult:
    """Register every curated board that is not already registered.

    Idempotent, and deliberately non-destructive. An existing row is left completely
    alone — including its failure counters and its active flag. Re-seeding must not
    silently reactivate a board somebody switched off, and must not reset the failure
    history that drives backoff, or every deploy would restart the retry cycle for boards
    that have been dead for a week.
    """
    existing = {
        (provider, token)
        for provider, token in (
            await session.execute(select(BoardToken.provider, BoardToken.token))
        ).all()
    }

    created = 0
    for board in SEED_BOARDS:
        if (board.provider, board.token) in existing:
            continue
        session.add(
            BoardToken(
                provider=board.provider,
                token=board.token,
                company_name=board.company_name,
            )
        )
        created += 1

    await session.commit()
    return BoardSeedResult(created=created, already_present=len(SEED_BOARDS) - created)
