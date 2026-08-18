"""Is this claim present in the source document?

The primitive underneath ADR 0006. Used twice: at parse time, to check a model did not
invent a role or a skill while structuring; and at tailor time, to check a rewritten
bullet introduces no entity or number absent from the resume.

Normalisation is the whole design problem. Too strict and faithful text is rejected
because a line wrapped; too loose and a fabrication slips through. The rule here is
whitespace and case only — never word removal, never stemming, never fuzzy distance.
Anything looser stops being evidence.
"""

import re

_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Collapse all whitespace to single spaces and casefold.

    Collapsing whitespace is required rather than cosmetic. Spike 002 found that a
    bullet wrapping onto a second line appears in extracted text with a newline in the
    middle, while the joined bullet has a space — so a literal comparison would report
    every wrapped bullet as fabricated. Those are the longest, most detailed bullets,
    which is the worst possible set to reject.

    Casefolding rather than lowercasing, so non-ASCII text compares correctly.
    """
    return _WHITESPACE.sub(" ", text).strip().casefold()


def appears_in(claim: str, source: str) -> bool:
    """Whether `claim` occurs in `source`, ignoring whitespace and case.

    Substring containment, deliberately. It is checkable, explainable to a student in one
    sentence, and cannot be argued with — which matters when the answer is used to refuse
    to write something.
    """
    claim_normalised = normalise(claim)
    if not claim_normalised:
        return False
    return claim_normalised in normalise(source)
