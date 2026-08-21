"""Reading the years of experience a posting demands.

This is the component the product exists to surface. Spike 001 established that filters answer
"could I apply?" and not "should I bother?", and the gap between those two questions is almost
always a number buried in the body: a posting titled `Software Engineer` asking for five years
passes every filter feature 02 has, and the student only discovers it after committing an
evening.

The parser's whole difficulty is that four things look nearly identical in running text:

- `5+ years of experience required` — a bar the student fails
- `3+ years preferred` — a preference a graduate may still clear
- `Bachelor's degree (4 years)` — a programme length, demanding no work at all
- `Graduating in 2026`, `$120,000 per year`, `40 hours per week` — not durations in any sense

Money, hours and calendar years outnumber genuine requirements in a typical description, so the
exclusions here are not edge-case polish; they are most of the work.
"""

# ruff: noqa: RUF001, RUF003
#
# Every pattern below is matched against text a company wrote, and companies write "3–5 years"
# with an en dash, "2—4 years" with an em dash and "two years' experience" with a curly
# apostrophe. Restricting these classes to ASCII would silently miss those postings, which is
# precisely the failure this module exists to prevent, so the ambiguous-character rules are
# switched off for the file rather than annotated line by line.

import re
from dataclasses import dataclass
from enum import StrEnum


class Basis(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"

    # The posting named no experience at all. Deliberately distinct from zero: a description
    # that
    # never mentions experience has not said the student qualifies, and the score must be able
    # to
    # tell "you meet this" from "nobody said". Story 35.
    UNSTATED = "unstated"


@dataclass(frozen=True)
class ExperienceRequirement:
    years: float | None
    basis: Basis

    # The words the number was read from, so the interface can show its evidence rather than
    # only its conclusion. Every assertion in this product carries the text it came from.
    phrase: str | None = None


_WORD_NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "fifteen": 15,
}

_NUMBER = r"(?:\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")"

# A duration must be followed by a time unit and then, within a short distance, something that
# means work. "3 years of experience" qualifies; "3 years of tenure is our average" does not,
# because tenure is a statistic about employees rather than a demand on the applicant.
_EXPERIENCE_WORDS = (
    r"(?:experience|exp\b|professional|industry|working|work|background|hands[- ]on)"
)

# The core shape: an optional lower bound, a number, a unit, and experience nearby.
_DURATION = re.compile(
    r"(?P<lead>minimum(?:\s+of)?|at\s+least|requires?|required|over|more\s+than|"
    r"ideally|preferably|bonus|plus)?"
    # Punctuation between the marker and the number. Real descriptions write "Bonus: 3 years"
    # and
    # "Minimum - 4 years", and without this the marker is lost and an optional line reads as a
    # bar.
    r"\s*[:\-–]?\s*"
    r"(?P<low>" + _NUMBER + r")"
    r"\s*"
    r"(?:\+|\s*(?:-|–|—|to)\s*(?P<high>" + _NUMBER + r"))?"
    r"\s*"
    r"(?P<unit>years?|yrs?\.?|months?|mos?\.?)"
    r"(?:['’]?s?)?"
    r"(?P<tail>[^.;\n]{0,60})",
    re.IGNORECASE,
)

# Phrases that mark the number as a preference rather than a bar.
_PREFERENCE = re.compile(
    r"\b(?:preferred|preferable|preferably|ideally|a\s+plus|nice\s+to\s+have|"
    r"bonus|desirable|advantageous|would\s+be\s+great)\b",
    re.IGNORECASE,
)

_REQUIREMENT = re.compile(
    r"\b(?:required|require|requires|must\s+have|minimum|at\s+least|需要)\b", re.IGNORECASE
)

# A programme length. `4-year degree` and `Bachelor's degree (4 years)` describe study, and a
# graduate has already done it — reading either as a work requirement would penalise exactly the
# qualification the student holds.
_EDUCATION_CONTEXT = re.compile(
    r"\b(?:degree|bachelor|master|diploma|b\.?s\.?c?\.?|m\.?s\.?c?\.?|"
    r"undergraduate|postgraduate|programme|program|study|studies|university|college)\b",
    re.IGNORECASE,
)

# Money, time off and rates. "$120,000 per year" and "20 days of vacation per year" both contain
# a
# number and the word year, and neither is a requirement.
_RATE_CONTEXT = re.compile(
    r"(?:[$£€]|\b(?:salary|compensation|base|bonus\s+target|equity|hour|hours|week|weeks|"
    r"day|days|vacation|pto|paid\s+time\s+off|per\s+annum|annually|revenue|growth|"
    r"tenure|average|median)\b)",
    re.IGNORECASE,
)

# An age, not a duration. "Must be at least 18 years of age" is in the legal boilerplate of most
# hourly postings, and it carries every marker a genuine requirement has — "at least", a number,
# the word years.
#
# This was found by running the parser over the real index, where 31 postings claimed to require
# eighteen years of experience: Patient Care Coordinator, Customer Service Representative,
# PCA/HHA. Those are the most accessible jobs in the index, and the bug buried them at the
# bottom
# of the feed for precisely the reader this product is built for.
_AGE_AFTER = re.compile(
    r"^\s*(?:old\b|of\s+age|or\s+older|or\s+above|and\s+older)",
    re.IGNORECASE,
)

# The marker can also precede the number: "the legal working age of 16 years".
_AGE_BEFORE = re.compile(
    r"\b(?:age\s+of|minimum\s+age|legal\s+working\s+age|aged)\s*$",
    re.IGNORECASE,
)

# A four-digit number is a calendar year, never a duration. Guarded separately from the main
# pattern because `2026` and `20` differ only in length, and `Class of 2025` is common.
_CALENDAR_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

_ZERO_PHRASES = re.compile(
    r"\b(?:no\s+(?:prior\s+|previous\s+|industry\s+)?experience(?:\s+is)?"
    r"(?:\s+necessary|\s+required|\s+needed)?"
    r"|new\s+grad(?:uate)?s?\s+(?:welcome|encouraged|only)?"
    r"|entry[- ]level\s+(?:position|role|opportunity)"
    r"|recent\s+grad(?:uate)?s?"
    r"|0\s*(?:\+|-|–|to)?\s*\d?\s*years?)\b",
    re.IGNORECASE,
)


def _to_number(token: str) -> float | None:
    token = token.strip().casefold()
    if token.isdigit():
        return float(token)
    if token in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[token])
    return None


def _window(text: str, start: int, end: int, radius: int = 70) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _clip(text: str, limit: int = 120) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


# Section headings under which everything is optional. Real descriptions carry the basis in the
# heading and not in the line: "Nice to have:" followed by a bullet saying "3+ years of Go" is a
# preference, and reading that bullet on its own would hide a job a graduate could get.
_PREFERENCE_HEADING = re.compile(
    r"(?:nice\s+to\s+have|preferred\s+(?:qualifications|skills|experience)|"
    r"bonus\s+points|pluses|it\s+would\s+be\s+(?:great|nice)|"
    r"desirable|optional|we.d\s+love|extra\s+credit)",
    re.IGNORECASE,
)

# How far back a heading is allowed to reach. Two lines of bullets, not a whole section: a
# heading twenty bullets above is not describing this line any more.
_HEADING_LOOKBACK = 220


def _preference_heading_above(text: str, position: int) -> bool:
    preceding = text[max(0, position - _HEADING_LOOKBACK) : position]
    # Only the nearest couple of lines. A full stop ends a sentence, not a section, so lines
    # rather than sentences are the unit here.
    recent = "\n".join(preceding.splitlines()[-3:])
    return bool(_PREFERENCE_HEADING.search(recent))


def parse_experience_requirement(title: str, description: str) -> ExperienceRequirement:
    """The lowest genuine requirement the posting states, and what it was read from.

    The lowest rather than the first or the highest: descriptions commonly say "3+ years
    required,
    5+ preferred", and the lower number is the bar the student actually has to clear. Taking the
    highest would hide jobs a graduate could get.
    """
    text = f"{title}\n{description}"
    if not text.strip():
        return ExperienceRequirement(None, Basis.UNSTATED)

    candidates: list[tuple[float, Basis, str]] = []

    for match in _DURATION.finditer(text):
        raw_low = match.group("low")

        # A calendar year is never a duration. Checked on the matched digits rather than the
        # window, so "Summer 2026" and "since 2019" drop out before anything else runs.
        if _CALENDAR_YEAR.search(raw_low):
            continue

        value = _to_number(raw_low)
        if value is None:
            continue

        if match.group("unit").lower().startswith(("month", "mo")):
            value = value / 12

        context = _window(text, match.start(), match.end())

        # An age is not experience. Two checks, because the marker sits on either side: "18
        # years
        # of age" puts it after the unit, and "the legal working age of 16 years" puts it before
        # the number. "at least 18 years of age" and "at least 18 years of experience" differ
        # only in the words following the unit, so the tail is where most of this is decided.
        tail_for_age = match.group("tail") or ""
        before = text[max(0, match.start() - 30) : match.start()]
        if _AGE_AFTER.search(tail_for_age) or _AGE_BEFORE.search(before):
            continue

        # A programme length is not work. This is checked before the experience requirement,
        # because "4-year degree required" contains the word required.
        if _EDUCATION_CONTEXT.search(context):
            continue

        # Money, hours and statistics. Checked on the near context so that a salary paragraph
        # elsewhere in the posting cannot suppress a genuine requirement.
        near = _window(text, match.start(), match.end(), radius=28)
        if _RATE_CONTEXT.search(near):
            continue

        tail = match.group("tail") or ""
        lead = match.group("lead") or ""

        # The number has to be about work at all, or "3 years ago we started" reads as a
        # requirement. Three things establish that it is:
        #
        # - an experience word nearby;
        # - a requirement or preference marker, because "5+ years required" and "3+ years
        #   preferred" are unambiguous without ever using the word experience — and those are
        #   the two commonest phrasings in the index;
        # - being in the title, where `Software Engineer (5+ yrs)` is the whole statement and
        #   brevity is the convention.
        in_title = match.start() < len(title)
        about_work = (
            re.search(_EXPERIENCE_WORDS, f"{tail} {lead}", re.IGNORECASE)
            or re.search(_EXPERIENCE_WORDS, context, re.IGNORECASE)
            or _REQUIREMENT.search(f"{lead} {tail}")
            or _PREFERENCE.search(f"{lead} {tail}")
        )
        if not (about_work or in_title):
            continue

        # Basis is decided from the clause the number sits in, never from a fixed window.
        #
        # A window of even seventy characters crosses a full stop, and "2+ years required. 5+
        # years preferred." then reads its first number as a preference — inverting the answer
        # for one of the most common phrasings there is. `tail` cannot cross a full stop, a
        # semicolon or a newline by construction, which is what makes it safe to read.
        clause = f"{lead} {tail}"

        if _PREFERENCE.search(clause):
            basis = Basis.PREFERRED
        elif _preference_heading_above(text, match.start()):
            # A heading carries the basis for everything under it: "Nice to have:" followed by
            # "3+ years of Kubernetes" is a preference, and nothing in that line says so.
            basis = Basis.PREFERRED
        else:
            basis = Basis.REQUIRED

        candidates.append((value, basis, _clip(match.group(0))))

    if candidates:
        # Requirements outrank preferences, then the lowest number within the winning basis.
        required = [c for c in candidates if c[1] == Basis.REQUIRED]
        pool = required or candidates
        years, basis, phrase = min(pool, key=lambda c: c[0])
        return ExperienceRequirement(years, basis, phrase)

    zero = _ZERO_PHRASES.search(text)
    if zero:
        return ExperienceRequirement(0.0, Basis.REQUIRED, _clip(zero.group(0)))

    return ExperienceRequirement(None, Basis.UNSTATED)
