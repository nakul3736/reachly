"""The structured form of an uploaded resume.

Shape decided in `.kiro/specs/01-profile-and-resume/design.md`, because provenance in
ADR 0006 depends on it. Two properties are load-bearing:

* **Bullets carry stable ids.** `provenance_map` references them, so a bullet without
  an id cannot be cited as evidence.
* **Dates are strings, as written.** There is deliberately no start/end date pair. A
  real resume mixes `January 2026 - Present` with `Aug 2023`; parsing either into a
  range invents precision the document does not contain.
"""

import hashlib

from pydantic import BaseModel, Field


def derive_id(*parts: str) -> str:
    """A short identifier derived from content.

    Content-derived rather than positional. A positional id — `experience-0`, or a
    database sequence — changes when a role is added above it or the parser reorders
    sections, and every stored `provenance_map` referencing it would then point at the
    wrong bullet while still resolving. That failure is silent, which is the worst kind
    here: the interface would show evidence for a claim it did not come from.
    """
    digest = hashlib.sha256("\u001f".join(parts).encode()).hexdigest()
    return digest[:16]


class Bullet(BaseModel):
    """One achievement line.

    `id` is what `provenance_map` points at. It is derived from content rather than
    assigned by position, so re-parsing the same document yields the same id and a
    stored provenance map still resolves.
    """

    id: str
    text: str


class ExperienceEntry(BaseModel):
    id: str
    employer: str
    title: str
    # As written. Never parsed into a range, never inferred when absent.
    dates: str = ""
    bullets: list[Bullet] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    """A personal, academic or open-source project.

    Modelled with bullets like an experience entry rather than as a paragraph, because for a new
    graduate this is often the strongest evidence in the document — the person with one retail job
    and four built things is better represented by the four built things. Tailoring reads bullets,
    so a projects section stored as prose would be excluded from the feature that matters most to
    exactly the students this product is for.

    `name` rather than `employer`: nobody employed them, and calling it an employer would put a
    company that does not exist onto a resume.
    """

    id: str
    name: str
    # As written. A project has no HR system, so dates are frequently absent, and absent is fine.
    dates: str = ""
    bullets: list[Bullet] = Field(default_factory=list)


class EducationEntry(BaseModel):
    id: str
    institution: str
    credential: str = ""
    dates: str = ""


class ParsedResume(BaseModel):
    """The whole document, structured.

    `raw_text` is retained on purpose: the ADR 0006 validator draws its entity set from
    the entire document, so a skill mentioned only in a summary line does not read as
    fabricated when it appears in a tailored bullet.
    """

    summary: str = ""
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    raw_text: str = ""

    def is_empty(self) -> bool:
        """Whether the document yielded nothing.

        A genuinely empty resume is a fact the interface can report. It is never used
        to signal a failure — that is what the parser exceptions are for.
        """
        return not (
            self.experience
            or self.projects
            or self.education
            or self.skills
            or self.summary.strip()
        )
