"""Reading a country and a remote flag out of a location string.

There is no standard here. The ten boards ingested so far produce, among others:

    'CA-Toronto, CA-Montreal, CA-Vancouver '
    'San Francisco, CA • New York, NY • United States'
    'US-Remote, US-San Francisco, US-Chicago'
    'San Francisco, CA; Chicago, IL & New York, NY'
    'US-West Coast (Remote) '
    'Toronto, Ontario, Canada'
    'Bengaluru, India'

`CA` carries two meanings in that list. `CA-Toronto` is Canada, because these boards prefix a
location with an ISO country code. `San Francisco, CA` is California, because American
addresses suffix a state code. A two-letter match would put every Bay Area job in Canada, or
every Toronto job in the United States, depending which way it guessed.

The derived country never replaces `location_raw`, which is stored and displayed as written.
Story 21, and the same principle as keeping resume dates verbatim: a derived value that guessed
wrong should be visibly wrong rather than quietly authoritative.
"""

import re
from dataclasses import dataclass

# Both the bullet Greenhouse uses and the ordinary punctuation the others do.
_SEPARATORS = re.compile(r"[;•|/]|\s+&\s+|\s+and\s+", re.IGNORECASE)

_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\bdistributed\b", re.IGNORECASE)

# `US-Chicago`, `CA-Toronto`. Anchored to the start of a segment so it cannot match the tail
# of an address.
_COUNTRY_PREFIX = re.compile(r"^\s*([A-Z]{2})\s*-\s*\S", re.MULTILINE)

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_CA_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}

_US_NAMES = re.compile(
    r"\bunited states\b|\bu\.s\.a?\b|\busa\b|\bamerica\b", re.IGNORECASE
)
_CA_NAMES = re.compile(r"\bcanada\b|\bcanadian\b", re.IGNORECASE)

# A bare country code, as in 'Remote - US'. Case-sensitive and deliberately US-only.
#
# No equivalent exists for Canada, and that asymmetry is the point: no American state is
# abbreviated `US`, so a bare `US` is unambiguous, whereas a bare `CA` is California far more
# often than Canada. Canada is recognised by its provinces, its cities, and the `CA-` prefix
# instead, all of which are unambiguous.
_US_BARE = re.compile(r"\bUS\b|\bUSA\b")

_CA_CITIES = re.compile(
    r"\btoronto\b|\bmontreal\b|\bvancouver\b|\bottawa\b|\bcalgary\b|\bedmonton\b"
    r"|\bhalifax\b|\bwinnipeg\b|\bquebec\b|\bwaterloo\b|\bmississauga\b|\bvictoria\b",
    re.IGNORECASE,
)

# Full province and state names, which appear in 'Toronto, Ontario, Canada' style strings.
_CA_PROVINCE_NAMES = re.compile(
    r"\bontario\b|\bquebec\b|\bbritish columbia\b|\balberta\b|\bmanitoba\b"
    r"|\bsaskatchewan\b|\bnova scotia\b|\bnew brunswick\b|\bnewfoundland\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Location:
    """A country code and a remote flag, or honest absence of both."""

    country: str | None
    is_remote: bool


def _segments(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in _SEPARATORS.split(raw):
        if chunk and chunk.strip():
            parts.append(chunk.strip())
    return parts or [raw.strip()]


def _country_of(segment: str) -> str | None:
    """The country a single location segment names, if it names one at all."""
    # Prefix form first, because it is unambiguous and settles the CA problem. A segment
    # beginning `CA-` is Canada regardless of what follows.
    prefix = _COUNTRY_PREFIX.match(segment)
    if prefix:
        code = prefix.group(1).upper()
        if code in {"US", "CA", "GB", "UK", "DE", "FR", "IE", "IN", "SG", "JP", "AU", "NL"}:
            return "US" if code == "US" else code

    if _CA_NAMES.search(segment) or _CA_PROVINCE_NAMES.search(segment):
        return "CA"
    if _US_NAMES.search(segment) or _US_BARE.search(segment):
        return "US"

    # Trailing two-letter code, the American and Canadian address convention. Read as a state
    # or province rather than a country, which is what makes `San Francisco, CA` California.
    tail = re.search(r",\s*([A-Za-z]{2})\s*$", segment)
    if tail:
        code = tail.group(1).upper()
        if code in _CA_PROVINCES and code not in _US_STATES:
            return "CA"
        if code in _US_STATES:
            return "US"

    if _CA_CITIES.search(segment):
        return "CA"
    return None


def extract_location(raw: str | None) -> Location:
    """Derive a country and remote flag from a posting's location text.

    A posting listing several countries gets one column, so US or Canada wins when either is
    present — those are the two countries this product serves, and dropping such a posting
    would lose a real opportunity a student could take. Everything else keeps its own code so
    the hard location filter can exclude it.
    """
    if not raw or not raw.strip():
        return Location(country=None, is_remote=False)

    remote = bool(_REMOTE.search(raw))

    found: list[str] = []
    for segment in _segments(raw):
        country = _country_of(segment)
        if country and country not in found:
            found.append(country)

    if "US" in found:
        return Location(country="US", is_remote=remote)
    if "CA" in found:
        return Location(country="CA", is_remote=remote)

    # A bare "Remote" names no country at all, and inventing one would be a guess the hard
    # filter would then act on.
    return Location(country=None, is_remote=remote)
