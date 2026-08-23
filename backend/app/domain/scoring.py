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
        token.casefold() for token in _TOKEN.findall(text) if token.casefold() not in _STOPWORDS
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


def _keyword_overlap(
    resume_text: str, description: str
) -> tuple[int, ComponentState, list[str]]:
    """Vocabulary overlap between the resume and the posting, weighted by term rarity.

    A BM25-shaped score rather than BM25 proper: with one document there is no corpus to draw
    document frequencies from, so rarity is approximated by how often a term repeats inside this
    description. The effect that matters is the same — a posting using the student's vocabulary
    throughout scores above one that mentions it once in a list of nice-to-haves.

    Returns the terms as well as the points, ordered by what each contributed. A student told
    their vocabulary overlap is 12 of 20 learns nothing; shown that the shared words are
    `postgresql, fastapi, pytest` and the absent ones are `kubernetes, terraform`, they know what
    to write next.
    """
    resume_words = set(_words(resume_text))
    description_words = _words(description)
    if not resume_words or not description_words:
        return 0, ComponentState.UNSTATED, []

    counts: dict[str, int] = {}
    for word in description_words:
        counts[word] = counts.get(word, 0) + 1

    # Saturating term frequency, as BM25 does: the fifth mention of a word adds far less than the
    # second, so a description repeating one word cannot dominate.
    k = 1.5
    overlap = 0.0
    contributions: list[tuple[float, str]] = []
    for word in resume_words & set(description_words):
        tf = counts[word]
        weight = (tf * (k + 1)) / (tf + k)
        overlap += weight
        contributions.append((weight, word))

    # Normalised against the resume's own vocabulary, so a longer resume is not penalised.
    ceiling = len(resume_words) * ((k + 1) / (1 + k)) * 2.0
    share = min(overlap / ceiling, 1.0) if ceiling else 0.0

    shared = [word for _, word in sorted(contributions, key=lambda c: (-c[0], c[1]))]
    return round(KEYWORD_WEIGHT * share), ComponentState.SCORED, shared


def _score_keywords(resume_text: str, description: str) -> tuple[int, ComponentState]:
    points, state, _ = _keyword_overlap(resume_text, description)
    return points, state


def _score_freshness(posted_at: datetime | None, now: datetime) -> tuple[int, ComponentState]:
    if posted_at is None:
        # Providers omit the date constantly, and the student is not at fault for that.
        return round(FRESHNESS_WEIGHT * _NEUTRAL_SHARE), ComponentState.UNSTATED

    age_days = (now - posted_at).total_seconds() / 86_400
    if age_days <= 0:
        # A future date is a provider quirk, not a reason to score badly.
        return FRESHNESS_WEIGHT, ComponentState.SCORED

    remaining = max(0.0, 1.0 - age_days / _FRESHNESS_HORIZON_DAYS)
    return math.floor(FRESHNESS_WEIGHT * remaining), ComponentState.SCORED


@dataclass(frozen=True)
class ScoreExplanation:
    """Every number the score was derived from, so the arithmetic can be redone by hand.

    Separate from `MatchBreakdown` on purpose. A breakdown is what gets stored and ranked, and it
    is reconstructed from database columns on a cache hit — so any derivation field added to it
    would come back empty for exactly the postings a student has already looked at, which is worse
    than not offering the explanation at all. This is computed fresh for a single posting, which
    costs a few milliseconds, and is therefore always complete.

    It shares the private scoring functions with `score_job` rather than reimplementing them. An
    explanation that can disagree with the number it explains is a liability, not a feature.

    The fields are facts, not sentences. How to word "you are two years short of a stated
    requirement" belongs to the interface, which knows whether it has room for it.
    """

    total: int

    # Skills: matched over asked, times the weight. The denominator is the posting's list.
    skill_points: int
    skill_weight: int
    skill_state: ComponentState
    skills_asked: int
    matched_skills: list[str]
    missing_skills: list[str]

    # Experience: the shortfall against what the posting stated, linear to a ten-year cap.
    experience_points: int
    experience_weight: int
    experience_state: ComponentState
    student_years: float
    required_years: float | None
    requirement_basis: Basis
    requirement_phrase: str | None
    max_gap_years: float
    preference_penalty_scale: float

    # Keywords: which of the student's own words this posting uses.
    keyword_points: int
    keyword_weight: int
    keyword_state: ComponentState
    shared_keywords: list[str]

    # Freshness: how old, against a one-month horizon.
    freshness_points: int
    freshness_weight: int
    freshness_state: ComponentState
    age_days: float | None
    freshness_horizon_days: int

    # What an unknown component is worth, so the interface can say "half of 30, because the
    # posting did not say" instead of leaving a student to guess where 15 came from.
    neutral_share: float


# How many shared words to report. Enough to be evidence, few enough to be read.
_SHARED_KEYWORD_LIMIT = 24


def explain_score(
    profile: StudentProfile,
    *,
    posting_skills: set[str],
    requirement: ExperienceRequirement,
    description: str,
    posted_at: datetime | None,
    now: datetime,
) -> ScoreExplanation:
    """Score one posting and return the derivation alongside the result.

    Takes a profile rather than `profile | None`: there is nothing to explain about a student who
    has uploaded no resume, and the caller has to handle that case anyway to say something more
    useful than a page of zeros.
    """
    skill_points, skill_state, matched, missing = _score_skills(profile.skills, posting_skills)
    experience_points, experience_state = _score_experience(
        profile.years_experience, requirement
    )
    keyword_points, keyword_state, shared = _keyword_overlap(profile.resume_text, description)
    freshness_points, freshness_state = _score_freshness(posted_at, now)

    age_days = None
    if posted_at is not None:
        age_days = max(0.0, (now - posted_at).total_seconds() / 86_400)

    return ScoreExplanation(
        total=skill_points + experience_points + keyword_points + freshness_points,
        skill_points=skill_points,
        skill_weight=SKILL_WEIGHT,
        skill_state=skill_state,
        skills_asked=len(posting_skills),
        matched_skills=matched,
        missing_skills=missing,
        experience_points=experience_points,
        experience_weight=EXPERIENCE_WEIGHT,
        experience_state=experience_state,
        student_years=profile.years_experience,
        required_years=requirement.years,
        requirement_basis=requirement.basis,
        requirement_phrase=requirement.phrase,
        max_gap_years=_MAX_GAP_YEARS,
        preference_penalty_scale=_PREFERENCE_PENALTY_SCALE,
        keyword_points=keyword_points,
        keyword_weight=KEYWORD_WEIGHT,
        keyword_state=keyword_state,
        shared_keywords=shared[:_SHARED_KEYWORD_LIMIT],
        freshness_points=freshness_points,
        freshness_weight=FRESHNESS_WEIGHT,
        freshness_state=freshness_state,
        age_days=age_days,
        freshness_horizon_days=_FRESHNESS_HORIZON_DAYS,
        neutral_share=_NEUTRAL_SHARE,
    )


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
    experience_points, experience_state = _score_experience(
        profile.years_experience, requirement
    )
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
