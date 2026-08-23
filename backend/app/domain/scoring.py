"""The match score: four weighted components, summed, with every part inspectable.

ADR 0003 fixes the weights and forbids inference here. The arithmetic below is the whole of
matching, which is deliberate — a student can be shown why a posting scored what it did, and the
same posting scores the same on every load.

Two decisions in the arithmetic matter more than the weights themselves.

**Each component is an integer within its own weight, and the total is their sum.** The obvious
alternative — score each component 0..1, multiply by its weight at the end, round — puts the
visible parts up to a point away from the visible total, and a student reading a bar that says
40 + 22 + 11 + 7 next to a total of 81 has found a bug in the only number they were given. There
is no explaining that away, so it is made impossible instead.

**Unstated is a state, not a value of zero.** Three of the four components can be genuinely
unknown: a posting may list no skills, state no experience requirement, or carry no date.
Scoring
those zero would rank an uninformative posting *below* one whose stated requirements the student
fails, which is backwards — the student can act on a stated mismatch and cannot act on silence.
Each unknown scores a neutral share of its weight and says so, and the interface renders that
state differently from both full marks and zero.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.experience import Basis, ExperienceRequirement

SKILL_WEIGHT = 40
EXPERIENCE_WEIGHT = 30
KEYWORD_WEIGHT = 20
FRESHNESS_WEIGHT = 10

TOTAL_WEIGHT = SKILL_WEIGHT + EXPERIENCE_WEIGHT + KEYWORD_WEIGHT + FRESHNESS_WEIGHT

# What an unknown is worth, as a fraction of its weight. Half: high enough that silence does not
# read as failure, low enough that it never beats a posting the student demonstrably fits.
_NEUTRAL_SHARE = 0.5

# A posting stops being fresh after a month. Chosen from what the index shows rather than taste:
# a graduate applying to something four weeks old is usually applying after the shortlist
# already exists.
_FRESHNESS_HORIZON_DAYS = 30

# How many years of shortfall exhausts the experience component. Ten because the index contains
# genuine 10+ year postings, and a graduate is equally excluded by 12 as by 10 — the score should
# not keep distinguishing between two impossibilities.
_MAX_GAP_YEARS = 10.0

# A stated preference is a softer bar than a stated requirement, so a graduate who misses it keeps
# most of the component. Applied as a reduction of the penalty rather than a bonus, so a preference
# can never score higher than the same requirement met.
_PREFERENCE_PENALTY_SCALE = 0.4


class ComponentState(StrEnum):
    """Why a component scored what it did, for the interface to render distinctly."""

    SCORED = "scored"
    MET = "met"
    SHORT = "short"

    # The posting did not say. Never rendered as full marks and never as zero.
    UNSTATED = "unstated"


@dataclass(frozen=True)
class StudentProfile:
    skills: set[str]
    years_experience: float
    resume_text: str


@dataclass(frozen=True)
class MatchBreakdown:
    total: int

    skill_points: int
    experience_points: int
    keyword_points: int
    freshness_points: int

    skill_state: ComponentState
    experience_state: ComponentState
    keyword_state: ComponentState
    freshness_state: ComponentState

    # The score's receipt. Which terms the posting wanted and which the student has, so the
    # number can be interrogated rather than merely believed.
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    # What the experience component read, and the words it read it from.
    required_years: float | None = None
    requirement_basis: Basis = Basis.UNSTATED
    requirement_phrase: str | None = None

    # False when there is no active resume to score against. The interface explains what
    # uploading would add rather than showing a student a row of zeros.
    is_complete: bool = True


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.]{1,}")

# Words too common to carry similarity. Kept short deliberately: a long stop list starts encoding
# opinions about which words matter, and the weights already decide that.
_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "you",
        "will",
        "our",
        "are",
        "your",
        "this",
        "that",
        "have",
        "from",
        "not",
        "all",
        "who",
        "work",
        "team",
        "role",
        "job",
        "company",
        "experience",
        "skills",
        "years",
        "must",
        "able",
        "including",
        "other",
        "their",
        "they",
        "them",
        "any",
        "may",
        "can",
        "more",
        "also",
        "well",
        "new",
        "help",
        "make",
        "using",
        "use",
    }
)


def _words(text: str) -> list[str]:
    return [
        token.casefold()
        for token in _TOKEN.findall(text)
        if token.casefold() not in _STOPWORDS
    ]


def _score_skills(
    profile_skills: set[str], posting_skills: set[str]
) -> tuple[int, ComponentState, list[str], list[str]]:
    """What share of what the posting asked for does the student have?

    The denominator is the posting's requirements, never the student's skill count. A student who
    knows forty things should not score higher against a posting wanting two of them than a
    student who knows exactly those two — the question is whether the job's needs are met.
    """
    if not posting_skills:
        return (
            round(SKILL_WEIGHT * _NEUTRAL_SHARE),
            ComponentState.UNSTATED,
            [],
            [],
        )

    folded = {skill.casefold(): skill for skill in profile_skills}
    matched = sorted(s for s in posting_skills if s.casefold() in folded)
    missing = sorted(s for s in posting_skills if s.casefold() not in folded)

    share = len(matched) / len(posting_skills)
    return round(SKILL_WEIGHT * share), ComponentState.SCORED, matched, missing


def _score_experience(
    student_years: float, requirement: ExperienceRequirement
) -> tuple[int, ComponentState]:
    if requirement.basis == Basis.UNSTATED or requirement.years is None:
        return round(EXPERIENCE_WEIGHT * _NEUTRAL_SHARE), ComponentState.UNSTATED

    gap = requirement.years - student_years
    if gap <= 0:
        return EXPERIENCE_WEIGHT, ComponentState.MET

    # Linear in the shortfall, floored at zero. Linear rather than exponential because the
    # student needs the ordering to be legible: two years short should look twice as far as one.
    penalty = min(gap / _MAX_GAP_YEARS, 1.0)
    if requirement.basis == Basis.PREFERRED:
        penalty *= _PREFERENCE_PENALTY_SCALE

    return round(EXPERIENCE_WEIGHT * (1.0 - penalty)), ComponentState.SHORT


def _score_keywords(resume_text: str, description: str) -> tuple[int, ComponentState]:
    """Vocabulary overlap between the resume and the posting, weighted by term rarity.

    A BM25-shaped score rather than BM25 proper: with one document there is no corpus to draw
    document frequencies from, so rarity is approximated by how often a term repeats inside this
    description. The effect that matters is the same — a posting using the student's vocabulary
    throughout scores above one that mentions it once in a list of nice-to-haves.
    """
    resume_words = set(_words(resume_text))
    description_words = _words(description)
    if not resume_words or not description_words:
        return 0, ComponentState.UNSTATED

    counts: dict[str, int] = {}
    for word in description_words:
        counts[word] = counts.get(word, 0) + 1

    # Saturating term frequency, as BM25 does: the fifth mention of a word adds far less than the
    # second, so a description repeating one word cannot dominate.
    k = 1.5
    overlap = 0.0
    for word in resume_words & set(description_words):
        tf = counts[word]
        overlap += (tf * (k + 1)) / (tf + k)

    # Normalised against the resume's own vocabulary, so a longer resume is not penalised.
    ceiling = len(resume_words) * ((k + 1) / (1 + k)) * 2.0
    share = min(overlap / ceiling, 1.0) if ceiling else 0.0
    return round(KEYWORD_WEIGHT * share), ComponentState.SCORED


def _score_freshness(
    posted_at: datetime | None, now: datetime
) -> tuple[int, ComponentState]:
    if posted_at is None:
        # Providers omit the date constantly, and the student is not at fault for that.
        return round(FRESHNESS_WEIGHT * _NEUTRAL_SHARE), ComponentState.UNSTATED

    age_days = (now - posted_at).total_seconds() / 86_400
    if age_days <= 0:
        # A future date is a provider quirk, not a reason to score badly.
        return FRESHNESS_WEIGHT, ComponentState.SCORED

    remaining = max(0.0, 1.0 - age_days / _FRESHNESS_HORIZON_DAYS)
    return math.floor(FRESHNESS_WEIGHT * remaining), ComponentState.SCORED


def score_job(
    profile: StudentProfile | None,
    *,
    posting_skills: set[str],
    requirement: ExperienceRequirement,
    description: str,
    posted_at: datetime | None,
    now: datetime,
) -> MatchBreakdown:
    """Score one posting against one profile.

    `now` is injected rather than read from the clock. A score that changes because time passed
    is a score nobody can reproduce, and freshness is the only component that could do that.
    """
    if profile is None:
        # Not a score of zero merit — no score at all. The distinction is what lets the interface
        # explain what uploading a resume would add instead of showing a student four empty bars.
        return MatchBreakdown(
            total=0,
            skill_points=0,
            experience_points=0,
            keyword_points=0,
            freshness_points=0,
            skill_state=ComponentState.UNSTATED,
            experience_state=ComponentState.UNSTATED,
            keyword_state=ComponentState.UNSTATED,
            freshness_state=ComponentState.UNSTATED,
            required_years=requirement.years,
            requirement_basis=requirement.basis,
            requirement_phrase=requirement.phrase,
            is_complete=False,
        )

    skill_points, skill_state, matched, missing = _score_skills(profile.skills, posting_skills)
    experience_points, experience_state = _score_experience(profile.years_experience, requirement)
    keyword_points, keyword_state = _score_keywords(profile.resume_text, description)
    freshness_points, freshness_state = _score_freshness(posted_at, now)

    return MatchBreakdown(
        total=skill_points + experience_points + keyword_points + freshness_points,
        skill_points=skill_points,
        experience_points=experience_points,
        keyword_points=keyword_points,
        freshness_points=freshness_points,
        skill_state=skill_state,
        experience_state=experience_state,
        keyword_state=keyword_state,
        freshness_state=freshness_state,
        matched_skills=matched,
        missing_skills=missing,
        required_years=requirement.years,
        requirement_basis=requirement.basis,
        requirement_phrase=requirement.phrase,
        is_complete=True,
    )
