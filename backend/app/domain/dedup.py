"""Deciding whether two postings are the same job.

Identity is content-derived. It cannot be a provider id, because no two providers share one —
the
same Shopify role is `4283910` on Greenhouse and `9182734` on The Muse, and neither number means
anything to the other. So the fingerprint is a hash over what a human would read: who is hiring,
for what, and where.

**The two mistakes here are not equally bad, and the thresholds reflect that.** A duplicate
shown
twice is an annoyance the student can see and dismiss. A real job wrongly collapsed is an
opportunity that never reaches the screen, and no part of the interface can hint at what is
missing — the student cannot dismiss something they were never shown. Every rule below therefore
errs toward keeping two rows apart, and the ambiguous band is resolved by asking rather than
guessing.
"""

import hashlib
import re

from rapidfuzz import fuzz

# --- company --------------------------------------------------------------------------

# Anchored at the end, and only as a whole word. `Include Health` keeps its `Inc`, because the
# rule is about a legal suffix rather than about the letters appearing anywhere.
_LEGAL_SUFFIX = re.compile(
    r"[,\s]+(?:inc|inc\.|incorporated|llc|l\.l\.c\.|ltd|ltd\.|limited|corp|corp\."
    r"|corporation|co|co\.|company|plc|gmbh|ag|se|s\.a\.|sa|nv|bv|pty|pte|ab|oy)\.?$",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")


def normalise_company(value: str) -> str:
    """Casefold, collapse whitespace, drop one trailing legal suffix.

    One suffix, not all of them: repeating the strip would turn `Acme Co Ltd` into `Acme` and
    also turn a genuine `Systems Limited Company` into something it is not. One pass covers the
    real variation between a board and an aggregator.
    """
    text = _WHITESPACE.sub(" ", value or "").strip()
    text = _LEGAL_SUFFIX.sub("", text)
    return text.casefold().strip(" ,.")


# --- title ----------------------------------------------------------------------------

# Requisition identifiers. Each pattern requires something that marks it as an identifier — a
# bracket, a hash, or four or more digits — because a bare small number in a title is usually a
# level and stripping it would be the expensive mistake this module exists to avoid.
_REQ_PATTERNS = (
    # (REQ-4821) / [12345] / (JR-9182)
    re.compile(r"[\(\[]\s*(?:req|jr|r|id|job|ref)?[-\s#:]*\d{3,}\s*[\)\]]", re.IGNORECASE),
    # #4821
    re.compile(r"#\s*\d+"),
    # - R12345 / JR0093822, a letter prefix followed by four or more digits.
    # The en dash is intentional in these character classes, not a typo for a hyphen: providers
    # genuinely publish requisition ids behind a typographic dash, and matching only the ASCII
    # hyphen would leave the id in the title on those postings.
    re.compile(r"[-–,\s]+[a-z]{1,3}\d{4,}\b", re.IGNORECASE),  # noqa: RUF001
    # - 12345, a bare number of four or more digits behind a separator
    re.compile(r"[-–,\s]+\d{4,}\b"),  # noqa: RUF001
)

# Remote markers, which one surface appends and another does not. Only stripped from the end,
# where they are a tag on the posting rather than part of what the job is.
_REMOTE_TAIL = re.compile(
    r"[\(\[\-–,]\s*(?:fully\s+)?remote(?:\s+\w+)?\s*[\)\]]?\s*$",  # noqa: RUF001
    re.IGNORECASE,
)

_PUNCTUATION = re.compile(r"[^\w\s]+")


def normalise_title(value: str) -> str:
    """Casefold, drop requisition ids and trailing remote tags, collapse the rest.

    Level markers survive deliberately. `Engineer II` and `Engineer III` are different jobs with
    different pay and different requirements, and a rule that ate the numerals would collapse a
    graduate opening into a senior one and delete it from the feed.
    """
    text = _WHITESPACE.sub(" ", value or "").strip()

    for pattern in _REQ_PATTERNS:
        text = pattern.sub("", text)
    text = _REMOTE_TAIL.sub("", text)

    text = _PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).casefold().strip()


# --- level markers --------------------------------------------------------------------

_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}

_LEVEL_PATTERNS = (
    # Trailing roman numeral: Engineer II
    re.compile(r"\b(i{1,3}|iv|v)\s*$", re.IGNORECASE),
    # L3 / L-3 / Level 3
    re.compile(r"\b(?:l|lvl|level)[-\s]?(\d)\b", re.IGNORECASE),
    # A trailing single digit: Analyst 3. Bounded to one digit so a cohort year is not a level.
    re.compile(r"\b(\d)\s*$"),
)


def level_marker(title: str) -> str | None:
    """The job level a title states, as a digit, or None.

    Extracted separately because token similarity cannot see it. `Software Engineer II` and
    `Software Engineer III` differ by one character and score far above any useful fuzzy
    threshold, so the level has to be compared on its own rather than left to be averaged away
    among the words that do match.

    A four-digit number is never a level — `Software Engineer Intern 2027` is a cohort.
    """
    text = (title or "").strip()

    for pattern in _LEVEL_PATTERNS:
        found = pattern.search(text)
        if found:
            token = found.group(1).casefold()
            return _ROMAN.get(token, token)
    return None


# Ranks a title can state, each mapped to a canonical name. Ordered most specific first, since a
# title stating two of them is described by the narrower one.
#
# These are separate values rather than one "senior" bucket, and that distinction was earned on
# unseen data: Discord lists `Senior Data Scientist, Causal Inference + Experimentation` and
# `Staff Data Scientist, Causal Inference & Experimentation`, whose titles are otherwise
# identical. Bucketing staff with senior made them one rank, so nothing separated them and they
# collapsed. Two adjacent rungs of a ladder are still two different jobs.
#
# Note the shape of these rules: they match vocabulary that any employer might use, not titles
# any particular employer does use. Nothing here names a company.
_SENIORITY_WORDS = (
    ("intern", re.compile(r"\b(?:intern|internship|co[-\s]?op)\b", re.IGNORECASE)),
    (
        "graduate",
        re.compile(r"\b(?:new[-\s]?grad(?:uate)?|graduate|entry[-\s]?level)\b", re.IGNORECASE),
    ),
    ("junior", re.compile(r"\b(?:junior|jr\.?)\b", re.IGNORECASE)),
    ("associate", re.compile(r"\bassociate\b", re.IGNORECASE)),
    ("principal", re.compile(r"\bprincipal\b", re.IGNORECASE)),
    ("staff", re.compile(r"\bstaff\b", re.IGNORECASE)),
    ("director", re.compile(r"\b(?:director|head)\b", re.IGNORECASE)),
    ("lead", re.compile(r"\blead\b", re.IGNORECASE)),
    ("senior", re.compile(r"\b(?:senior|snr|sr\.?)\b", re.IGNORECASE)),
)


def seniority_markers(title: str) -> frozenset[str]:
    """Every rank word a title states, canonicalised.

    A set rather than one value, because a title can legitimately contain two. `Retail Sales
    Associate` uses "associate" as the job itself, and `Senior Retail Sales Associate` adds a
    rank
    on top of it — asking which one "the" rank is has no correct answer, and any single-value
    version has to pick wrong for one of them.

    Comparing sets sidesteps the question entirely: `{associate}` against `{associate, senior}`
    differ, which is all the caller needs to know. It also fixes the case that motivated
    splitting
    ranks apart in the first place, `{staff}` against `{senior}`.

    Separate from `level_marker` because the words carry the same meaning as the numerals and
    are
    invisible to string similarity for the same reason. `Infrastructure Software Engineer` and
    `Senior Infrastructure Software Engineer` score 0.90 on sorted tokens — one word out of
    five —
    and collapsing them puts a senior role in a graduate's feed while removing the opening they
    could have applied for.
    """
    found = {label for label, pattern in _SENIORITY_WORDS if pattern.search(title or "")}
    return frozenset(found)


# --- location -------------------------------------------------------------------------

_COUNTRY_WORDS = {
    "canada": "ca",
    "united states": "us",
    "united states of america": "us",
    "usa": "us",
    "us": "us",
    "u.s.": "us",
    "u.s.a.": "us",
}

_REMOTE_WORDS = {"remote", "fully remote", "hybrid", "onsite", "on site", "in office"}

# `Remote - Toronto` and `Toronto - Remote`. Handled as an affix rather than by adding `-` to
# the
# separator list, because a dash is part of the name in Saint-Jean, Baie-Comeau and
# Berlin-Kreuzberg, and splitting on it would turn one place into two.
_REMOTE_AFFIX = re.compile(
    r"^\s*(?:fully\s+)?remote\s*[-–]\s*|\s*[-–]\s*(?:fully\s+)?remote\s*$",  # noqa: RUF001
    re.IGNORECASE,
)


def normalise_location(value: str | None) -> str:
    """Casefold, drop country and work-arrangement words, sort the remaining parts.

    Sorting is what makes multi-location postings comparable. Lever joins its locations in one
    order and The Muse in another, and an unsorted join would give the same set of cities two
    different identities.

    Country words are dropped **only when something else remains**, because a board usually
    writes the country and an aggregator usually does not — a difference in habit rather than in
    the job.

    That condition was a bug, found on real data rather than reasoned about. Dropping the
    country
    unconditionally turned a posting located `Canada` and one located `United States` into the
    same empty string, so Stripe's `Credit Risk Strategy and Analytics` in each country produced
    one identical fingerprint and collapsed into a single row. Erasing the only location a
    posting has is the opposite of what this function is for, and for a product about US and
    Canadian graduates it hid half of those postings.
    """
    text = _WHITESPACE.sub(" ", (value or "")).strip()
    if not text:
        return ""

    text = _REMOTE_AFFIX.sub("", text)

    parts = [part.strip().casefold() for part in re.split(r"[;,/|]|\band\b", text)]
    parts = [part for part in parts if part]

    specific = [
        part for part in parts if part not in _COUNTRY_WORDS and part not in _REMOTE_WORDS
    ]
    if specific:
        return ", ".join(sorted(set(specific)))

    # Nothing but a country or a work arrangement. Keep the country, canonicalised, so that two
    # different countries remain two different places.
    countries = {_COUNTRY_WORDS[part] for part in parts if part in _COUNTRY_WORDS}
    return ", ".join(sorted(countries))


_SHORT_CODE = re.compile(r"^[a-z]{2}$")


def location_similarity(left: str | None, right: str | None) -> float:
    """How alike two locations are, from 0 to 1.

    Returns 1.0 when either side says nothing. An absent location is not evidence of a
    difference, and requiring both sides to state one would stop an aggregator copy — which
    frequently omits it — from ever matching the board posting it came from.

    This exists because title similarity alone cannot decide a collapse, which real data made
    concrete: Stripe lists `Director, Sales Compensation` once for the US and again for Canada
    as two separate postings with identical titles, scoring a perfect title match. Same role,
    same company, different job, and only the location says so.

    Two-letter codes are compared separately from place names rather than mixed in with them,
    for two reasons that pull in opposite directions and both matter. A **shared** code inflates
    similarity between different places: `Wallingford, CT` and `Stonington, CT` are two towns
    and two different jobs, but the `CT` in common made them look alike enough to merge, which
    is how Masonicare's `Nursing Assistant` postings collapsed. A **differing** code is decisive
    on its own: `Portland, OR` and `Portland, ME` share a whole city name and are two thousand
    miles
    apart.
    """
    left_parts = {part for part in normalise_location(left).split(", ") if part}
    right_parts = {part for part in normalise_location(right).split(", ") if part}
    if not left_parts or not right_parts:
        return 1.0

    left_codes = {part for part in left_parts if _SHORT_CODE.match(part)}
    right_codes = {part for part in right_parts if _SHORT_CODE.match(part)}

    # Both name a state, province or country and they do not overlap. A different place,
    # whatever
    # the rest of the string says.
    if left_codes and right_codes and not (left_codes & right_codes):
        return 0.0

    left_places = ", ".join(sorted(left_parts - left_codes))
    right_places = ", ".join(sorted(right_parts - right_codes))

    # One side named only a region, and it agreed with the other's above.
    if not left_places or not right_places:
        return 1.0

    return fuzz.token_sort_ratio(left_places, right_places) / 100.0


# --- the fingerprint ------------------------------------------------------------------


def fingerprint(*, company: str, title: str, location: str | None) -> str:
    """Content-derived identity for a posting.

    Truncated to 32 hex characters. Collision resistance at that width is far beyond what a few
    hundred thousand postings need, and the shorter value keeps the index and the paired verdict
    keys small.

    The separator is a character that cannot appear in any of the normalised parts, so
    `company="ab", title="c"` cannot collide with `company="a", title="bc"`.
    """
    material = "\x1f".join(
        (
            normalise_company(company),
            normalise_title(title),
            normalise_location(location),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


# --- similarity -----------------------------------------------------------------------


def title_similarity(left: str, right: str) -> float:
    """How alike two titles are, from 0 to 1, with level differences forced apart.

    **`token_sort_ratio`, not `token_set_ratio` — a deliberate departure from the ticket.** The
    ticket specified token-set, and measuring it against the real cases showed it cannot be used
    here: it scores a subset as a perfect match, so on normalised titles it returns 100 for
    `data analyst` against `senior data analyst`, 100 for `software engineer` against `software
    engineer machine learning`, and 100 for `software engineer platform` against `platform
    engineer`. Every one of those is two different openings, and collapsing them is the failure
    the ticket itself calls the expensive one.

    `token_sort_ratio` keeps what token-set was chosen for — word order still does not matter,
    so
    `Software Engineer, New Grad` and `New Grad Software Engineer` both score 100 — while
    scoring
    those three subset cases 77, 67 and 79. Two of them land in the ambiguous band, which is
    where a genuinely uncertain pair belongs.

    A differing level marker returns zero regardless of how similar the words are. This is the
    one
    place the function deliberately contradicts its own metric, and it is the difference
    between a
    graduate seeing an `Engineer I` opening and having it collapsed into the `Engineer III`
    posting listed beside it.
    """
    left_level = level_marker(left)
    right_level = level_marker(right)
    if left_level != right_level and (left_level is not None and right_level is not None):
        return 0.0

    # A stated rank that disagrees is as decisive as a numeric level. Compared as sets, so
    # `{associate}` against `{associate, senior}` counts as a disagreement.
    left_ranks = seniority_markers(left)
    right_ranks = seniority_markers(right)
    if left_ranks and right_ranks and left_ranks != right_ranks:
        return 0.0

    # One side stating a level or a seniority while the other does not is weak evidence of
    # difference rather than proof, so it is discounted rather than zeroed — the ambiguous band
    # exists for exactly this. The discount is enough to pull an otherwise-perfect match below
    # the
    # collapse threshold, which is what `Infrastructure Software Engineer` against `Senior
    # Infrastructure Software Engineer` needs.
    penalty = 0.0
    if (left_level is None) != (right_level is None):
        penalty += 0.20
    if bool(left_ranks) != bool(right_ranks):
        penalty += 0.20

    score = fuzz.token_sort_ratio(normalise_title(left), normalise_title(right)) / 100.0
    return max(0.0, score - penalty)
