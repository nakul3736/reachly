"""The tailoring validator. This is the feature; everything else is plumbing.

ADR 0006, non-negotiable 1: a tailored bullet may rephrase, reorder and re-emphasise, and may never
introduce a technology, employer, metric or claim absent from **its own source bullet**.

The rule is a subset test. Extract what the source asserts, extract what the rewrite asserts, and
require the second to be contained in the first. Saying less is always allowed — emphasis is a
permitted transformation, and a shorter bullet cannot fabricate.

Per bullet against its own source, never against the whole resume. A student who knows Python and
also worked a till has both facts on their resume; a rewrite that moves Python into the retail
bullet produces a sentence that is false about that job, and that is precisely the error an
interviewer finds.

Enforced after generation and before display. A prompt asking the model to behave is what every
competitor ships: it fails silently, and it gives the student nothing to audit.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.claims import extract_claims

# How much longer a rewrite may be than its source, as a ratio of word counts.
#
# Length is a proxy for invention that survives even when every extracted claim checks out: a
# bullet that triples in length has had prose added, and prose describing work the student never
# described is a claim whatever nouns it happens to contain. 1.6 leaves room for genuinely more
# specific phrasing while catching the paragraph of stakeholder-collaboration filler that models
# produce when asked to make something sound impressive.
MAX_LENGTH_RATIO = 1.6


class RejectionReason(StrEnum):
    ADDED_TECHNOLOGY = "added_technology"
    ADDED_NUMBER = "added_number"
    ADDED_PROPER_NOUN = "added_proper_noun"
    TOO_LONG = "too_long"
    EMPTY = "empty"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: RejectionReason | None = None

    # What was caught, in words, so the interface can tell the student what happened and the retry
    # prompt can name the specific claim it must drop.
    detail: str = ""


def validate_rewrite(source: str, rewrite: str) -> ValidationResult:
    """Whether `rewrite` is supported entirely by `source`."""
    if not rewrite or not rewrite.strip():
        return ValidationResult(False, RejectionReason.EMPTY, "the rewrite is empty")

    source_words = len(source.split())
    rewrite_words = len(rewrite.split())
    if source_words and rewrite_words > max(source_words * MAX_LENGTH_RATIO, source_words + 6):
        return ValidationResult(
            False,
            RejectionReason.TOO_LONG,
            f"{rewrite_words} words from a source of {source_words}",
        )

    source_claims = extract_claims(source)
    rewrite_claims = extract_claims(rewrite)

    added_tech = rewrite_claims.technologies - source_claims.technologies
    if added_tech:
        return ValidationResult(
            False,
            RejectionReason.ADDED_TECHNOLOGY,
            ", ".join(sorted(added_tech)),
        )

    added_numbers = rewrite_claims.numbers - source_claims.numbers
    if added_numbers:
        return ValidationResult(
            False,
            RejectionReason.ADDED_NUMBER,
            ", ".join(f"{n:g}" for n in sorted(added_numbers)),
        )

    added_names = rewrite_claims.proper_nouns - source_claims.proper_nouns
    if added_names:
        return ValidationResult(
            False,
            RejectionReason.ADDED_PROPER_NOUN,
            ", ".join(sorted(added_names)),
        )

    return ValidationResult(True)
