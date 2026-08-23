"""What a piece of text asserts as fact about the student.

The input to the tailoring validator. Three kinds of claim are extracted, and the choice of three
is the whole design — ADR 0006 permits rephrasing, so anything checked at the level of ordinary
words would reject every useful rewrite and leave the feature silently doing nothing.

| Kind | Why |
|---|---|
| Technologies | The commonest fabrication: the posting wants Kubernetes, so the rewrite adds it. |
| Numbers | "Reduced latency 40%" is unfalsifiable, and unforgettable when an interviewer asks. |
| Proper nouns | Employers, products, institutions. Adding one invents a relationship. |

Technologies come from the same vocabulary feature 03 uses, deliberately: a single list means a
skill the product can score is a skill it can also police, and the two cannot drift apart.
"""

import re
from dataclasses import dataclass, field

from app.domain.skill_extraction import extract_skills

# Written numbers that appear in real bullets. Not exhaustive by design — a bullet saying
# "seventeen thousand" is vanishingly rare, and the numeric forms are what matter.
_WORD_NUMBERS: dict[str, float] = {
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
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "twenty-five": 25,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "thousand": 1000,
    "million": 1_000_000,
}

_NUMERIC = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD_NUMBER = re.compile(
    r"\b(" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")\b", re.IGNORECASE
)

# A four-digit number in the 19xx/20xx range is a date. Dates are stored as written (feature 01)
# and a rewrite that keeps one asserts no new quantity, so they are not metrics.
_YEAR = re.compile(r"^(?:19|20)\d{2}$")

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.'’-]*")

# Words that are capitalised for reasons other than being a name: sentence starts, months,
# and the vocabulary of a resume bullet. Without this list every bullet's first word becomes an
# invented employer and nothing ever validates.
_NOT_NAMES = frozenset(
    {
        "a",
        "an",
        "the",
        "i",
        "and",
        "or",
        "but",
        "for",
        "with",
        "to",
        "in",
        "on",
        "at",
        "by",
        "of",
        "from",
        "as",
        "into",
        "across",
        "using",
        "used",
        "built",
        "build",
        "developed",
        "develop",
        "designed",
        "design",
        "created",
        "create",
        "implemented",
        "implement",
        "led",
        "lead",
        "managed",
        "manage",
        "worked",
        "work",
        "wrote",
        "write",
        "improved",
        "improve",
        "reduced",
        "reduce",
        "increased",
        "increase",
        "automated",
        "automate",
        "analysed",
        "analyzed",
        "analyse",
        "analyze",
        "collaborated",
        "collaborate",
        "delivered",
        "deliver",
        "shipped",
        "ship",
        "owned",
        "own",
        "supported",
        "support",
        "maintained",
        "maintain",
        "tested",
        "test",
        "deployed",
        "deploy",
        "migrated",
        "migrate",
        "refactored",
        "refactor",
        "cut",
        "handled",
        "handle",
        "served",
        "serve",
        "coordinated",
        "coordinate",
        "authored",
        "presented",
        "present",
        "researched",
        "research",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "summer",
        "winter",
        "spring",
        "autumn",
        "fall",
    }
)


@dataclass(frozen=True)
class Claims:
    technologies: set[str] = field(default_factory=set)
    numbers: set[float] = field(default_factory=set)
    proper_nouns: set[str] = field(default_factory=set)


def normalise_number(text: str) -> float | None:
    """One value for a quantity however it was written.

    `40%`, `40 percent` and `forty percent` are the same claim, and a rewrite legitimately changes
    the form. Comparing surfaces would reject a correct rewrite while still missing an inflated
    one; comparing values does neither.
    """
    cleaned = text.strip().rstrip("%").strip()

    # "40 percent" and "40%" are one claim. The unit is dropped before parsing so the numeric and
    # the spelled-out forms converge, which is the point of normalising at all.
    cleaned = re.sub(r"\s*(?:percent|per\s*cent|pct)\.?$", "", cleaned, flags=re.IGNORECASE).strip()

    numeric = _NUMERIC.fullmatch(cleaned.replace(" ", ""))
    if numeric:
        return float(numeric.group(0).replace(",", ""))

    lowered = cleaned.casefold()
    if lowered in _WORD_NUMBERS:
        return _WORD_NUMBERS[lowered]

    # "forty percent" and the like: take the leading word number.
    match = _WORD_NUMBER.match(lowered)
    if match:
        return _WORD_NUMBERS[match.group(1).casefold()]
    return None


def _numbers_in(text: str) -> set[float]:
    found: set[float] = set()

    for raw in _NUMERIC.findall(text):
        bare = raw.replace(",", "")
        if _YEAR.match(bare):
            continue
        try:
            found.add(float(bare))
        except ValueError:
            continue

    for word in _WORD_NUMBER.findall(text):
        found.add(_WORD_NUMBERS[word.casefold()])

    return found


def _proper_nouns_in(text: str) -> set[str]:
    """Capitalised words that are plausibly names.

    The first word of a sentence is skipped, because every bullet begins with a capital and
    treating that as an employer would reject every rewrite ever generated. A known technology is
    also skipped — it is already checked, more precisely, as a technology.
    """
    technologies = {t.casefold() for t in extract_skills(text)}
    names: set[str] = set()

    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        words = _WORD.findall(sentence)
        for index, word in enumerate(words):
            if index == 0:
                continue
            if not word[0].isupper():
                continue
            if word.casefold() in _NOT_NAMES:
                continue
            if word.casefold() in technologies:
                continue
            # An all-caps token is usually an acronym for a technology or a course code rather
            # than a name, and the technology check already covers the ones that matter.
            if word.isupper() and len(word) <= 4:
                continue
            names.add(word)

    return names


def extract_claims(text: str) -> Claims:
    if not text or not text.strip():
        return Claims()

    return Claims(
        technologies=extract_skills(text),
        numbers=_numbers_in(text),
        proper_nouns=_proper_nouns_in(text),
    )
