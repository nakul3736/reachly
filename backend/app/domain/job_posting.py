"""What every job source produces, before anything is stored.

One shape for four providers whose JSON agrees on almost nothing. Adapters translate into
this and do nothing else — no HTTP policy, no database access, no filtering — so the
awkwardness of each provider stays in one small module instead of leaking into the index.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawPosting:
    """One posting as a single source published it.

    Frozen because ingestion classifies and dedups afterwards; a posting that could be
    edited in place would make it impossible to tell what the source actually said from
    what Reachly decided.
    """

    source: str
    source_job_id: str
    company_name: str
    title: str
    description: str
    apply_url: str

    # As written by the posting, and kept unchanged. A derived country goes in a separate
    # column later, so a wrong guess is visibly wrong rather than quietly authoritative.
    location_raw: str | None = None

    # Frequently absent, and distinct from when Reachly first saw the posting.
    posted_at: datetime | None = None

    # False for aggregators. Decides which record wins during dedup, and whether absence
    # from a refresh is evidence of anything.
    is_verified: bool = True

    # What the provider itself says, where it says anything.
    #
    # Both are hints rather than values because they are only consulted when Reachly's own
    # deterministic rules come back unknown. A provider's own statement is better evidence than
    # a regex over a title — The Muse marking "Security Officer" as entry level is a fact we
    # cannot derive — but a provider is also not allowed to override a rule that did fire, or
    # an aggregator could quietly reclassify a senior role into a graduate's feed.
    seniority_hint: str | None = None
    is_remote_hint: bool | None = None
