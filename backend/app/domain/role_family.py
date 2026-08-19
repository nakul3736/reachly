"""Reading a role's family and seniority from its title.

Deterministic, per ADR 0003. This runs on every posting on every refresh — 2,586 of them
today — so a model call per job would be both slow and unaffordable, and would make the feed's
composition depend on a provider's uptime.

Spike 001 is why this module exists at all: under 3% of company-board postings are entry level
and they skew to non-software titles, so without it the feed is technically correct and
practically useless. That measurement reproduces exactly in the ingested data — 59 of 2,586
titles carry any entry-level marker.
"""

import re
from enum import StrEnum


class Seniority(StrEnum):
    ENTRY = "entry"
    SENIOR = "senior"
    # No marker in the title. Deliberately not a guess in either direction: guessing entry
    # fills a graduate's feed with roles wanting ten years, and guessing senior hides the
    # plain "Software Engineer" postings that are often exactly right for them.
    UNKNOWN = "unknown"


def _word_pattern(terms: list[str]) -> re.Pattern[str]:
    """Match any term on word boundaries.

    Boundaries rather than substrings because the short markers are destructive otherwise:
    `I` matches "IT Support", and `lead` matches "Leadership Development".
    """
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![\w.])(?:" + "|".join(escaped) + r")(?![\w])", re.IGNORECASE)


# `Sr.` is listed separately from `Senior` because the real data has 205 of the abbreviation
# against 513 of the full word. A rule matching only the long form leaves two hundred senior
# roles looking like unknowns, which puts them straight into a graduate's feed.
_SENIOR_TERMS = [
    "senior",
    "sr",
    "sr.",
    "staff",
    "principal",
    "lead",
    "leader",
    "manager",
    "management",
    "director",
    "head",
    "vp",
    "svp",
    "evp",
    "vice president",
    "chief",
    "architect",
    "distinguished",
    "fellow",
    # Level suffixes. II and above are not entry level whatever else the title says.
    "ii",
    "iii",
    "iv",
    "v",
]

_ENTRY_TERMS = [
    "intern",
    "internship",
    "co-op",
    "coop",
    "new grad",
    "new graduate",
    "new-grad",
    "graduate",
    "junior",
    "jr",
    "jr.",
    "entry level",
    "entry-level",
    "apprentice",
    "apprenticeship",
    "trainee",
    "university grad",
    "campus",
    # Roman numeral one, as its own word only.
    "i",
]

_SENIOR = _word_pattern(_SENIOR_TERMS)
_ENTRY = _word_pattern(_ENTRY_TERMS)

# Numeric levels: L4 and above, and "5+ years" style requirements that appear in titles.
_NUMERIC_SENIOR = re.compile(r"\b(?:L[4-9]|[5-9]\+\s*years?)\b", re.IGNORECASE)


def classify_seniority(title: str) -> Seniority:
    """Entry, senior, or honestly unknown.

    A senior marker always wins over an entry marker. `Senior Software Engineer Intern` and
    `Manager, Graduate Recruiting` both contain entry words, and both are senior roles. Reading
    it the other way round is the single fastest way to make this product useless.
    """
    if not title:
        return Seniority.UNKNOWN

    if _SENIOR.search(title) or _NUMERIC_SENIOR.search(title):
        return Seniority.SENIOR
    if _ENTRY.search(title):
        return Seniority.ENTRY
    return Seniority.UNKNOWN


# Families in priority order. Order is the whole design: a title can contain words from
# several families, and the first match wins, so the more specific families are listed above
# the ones whose vocabulary they borrow.
#
# `Solutions Engineer` and `Sales Engineer` are the reason. Both contain `Engineer` and both
# are commercial roles that would waste a graduate developer's evening — exactly the confusion
# spike 001 said this filter exists to prevent. So sales is tested before engineering.
_FAMILIES: list[tuple[str, list[str]]] = [
    (
        "sales",
        [
            "account executive",
            "account manager",
            "account associate",
            "sales",
            "solutions engineer",
            "solutions architect",
            "solutions consultant",
            "presales",
            "pre-sales",
            "business development",
            "partnerships",
            "revenue",
            "quota",
        ],
    ),
    (
        "support",
        [
            "customer success",
            "customer support",
            "customer experience",
            "technical support",
            "support engineer",
            "support specialist",
            "implementation",
            "onboarding specialist",
            "technical account",
        ],
    ),
    (
        "data_ml",
        [
            "data scientist",
            "data science",
            "data analyst",
            "data engineer",
            "analytics",
            "machine learning",
            "ml engineer",
            "deep learning",
            "research scientist",
            "applied scientist",
            "business intelligence",
            "statistician",
        ],
    ),
    (
        "infrastructure",
        [
            "site reliability",
            "sre",
            "devops",
            "platform engineer",
            "infrastructure",
            "cloud engineer",
            "security engineer",
            "security analyst",
            "network engineer",
            "systems engineer",
            "database administrator",
            "observability",
        ],
    ),
    (
        "quality",
        ["qa", "quality assurance", "test engineer", "sdet", "automation engineer"],
    ),
    (
        "design",
        [
            "designer",
            "design",
            "ux",
            "ui",
            "user experience",
            "user research",
            "brand studio",
        ],
    ),
    (
        "product",
        ["product manager", "product management", "product owner", "technical program"],
    ),
    (
        "software_engineering",
        [
            "software engineer",
            "software developer",
            "software development",
            "backend",
            "back end",
            "back-end",
            "frontend",
            "front end",
            "front-end",
            "full stack",
            "fullstack",
            "full-stack",
            "web developer",
            "mobile engineer",
            "ios",
            "android",
            "developer",
            "engineer",
            "engineering",
            "programmer",
        ],
    ),
    (
        "marketing",
        [
            "marketing",
            "content",
            "brand",
            "communications",
            "social media",
            "growth",
            "demand generation",
            "seo",
            # Editorial work found on unseen boards. General publishing vocabulary rather
            # than a patch for one company's title.
            "editor",
            "editorial",
            "copywriter",
            "community manager",
        ],
    ),
    (
        "business",
        [
            "accountant",
            "accounting",
            "finance",
            "financial",
            "controller",
            "treasury",
            "tax",
            "legal",
            "counsel",
            "compliance",
            "recruiter",
            "recruiting",
            # Standard recruiting vocabulary, missed until the classifier was run against
            # boards it had never seen. "Technical Sourcer" is a recruiter, not an engineer.
            "sourcer",
            "sourcing",
            "talent",
            "people",
            "human resources",
            "administrative",
            "executive assistant",
            "office manager",
            "operations",
            "strategy",
            "procurement",
            "payroll",
            "workplace",
            "government affairs",
        ],
    ),
]

_COMPILED_FAMILIES = [(name, _word_pattern(terms)) for name, terms in _FAMILIES]

OTHER = "other"

ROLE_FAMILIES = [name for name, _ in _FAMILIES] + [OTHER]


def classify_role_family(title: str) -> str:
    """The first family whose vocabulary the title uses, or `other`.

    `other` is a real answer rather than a dumping ground, and the feed lets a student include
    it. A classifier that quietly files what it does not understand under a plausible heading
    hides the mistake; `other` shows it.
    """
    if not title:
        return OTHER

    for name, pattern in _COMPILED_FAMILIES:
        if pattern.search(title):
            return name
    return OTHER
