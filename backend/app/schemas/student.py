from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Without these three, the feed cannot produce anything useful: there is nothing to
# match on, nowhere to look, and no skills to score overlap against.
REQUIRED_FOR_RESULTS = ("target_role", "locations", "skills")

# Zero is a legitimate answer for a new graduate. The upper bound only has to
# exclude values that cannot describe a person's career.
MIN_YEARS_EXPERIENCE = 0
MAX_YEARS_EXPERIENCE = 60

MAX_LOCATIONS = 10
MAX_SKILLS = 60


def _clean_list(values: list[str]) -> list[str]:
    """Trim, drop blanks, and collapse case-insensitive duplicates in order.

    A stored empty string becomes a filter matching nothing, and does it silently —
    the student sees an empty feed with no reason for it. Duplicates would double a
    skill's weight in overlap scoring.

    The spelling the student chose is preserved; only later occurrences are dropped.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        trimmed = value.strip()
        if not trimmed or trimmed.casefold() in seen:
            continue
        seen.add(trimmed.casefold())
        cleaned.append(trimmed)
    return cleaned


class StudentProfileUpdate(BaseModel):
    """A partial update.

    Every field defaults to unset, and only the fields actually present in the
    request body are applied. This is what stops a form that submits one field from
    clearing the rest.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    target_role: str | None = None
    years_experience: (
        Annotated[int, Field(ge=MIN_YEARS_EXPERIENCE, le=MAX_YEARS_EXPERIENCE)] | None
    ) = None
    locations: Annotated[list[str], Field(max_length=MAX_LOCATIONS)] | None = None
    skills: Annotated[list[str], Field(max_length=MAX_SKILLS)] | None = None
    links: dict[str, str] | None = None

    @field_validator("name", "target_role")
    @classmethod
    def _trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        # A whitespace-only name is not a name. Storing None says "unstated", which
        # is what the student actually communicated.
        return trimmed or None

    @field_validator("locations", "skills")
    @classmethod
    def _normalise_list(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_list(value)


class StudentProfile(BaseModel):
    """The profile as the student sees it.

    `missing_for_results` is computed, not stored. An empty feed with no explanation
    is the worst version of this product; this field is how the interface says what
    it still needs.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str | None
    target_role: str | None
    years_experience: int | None
    locations: list[str]
    skills: list[str]
    links: dict[str, str]
    missing_for_results: list[str]
