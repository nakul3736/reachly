"""The real resume parser: pdfplumber extraction, then model structuring.

Two halves with different characters, deliberately kept apart.

**Extraction is deterministic.** pdfplumber either finds a text layer or there is not
one. No model, no variance, no cost.

**Structuring uses one model call per upload.** Spike 002 is the argument for this. That
spike found the geometry of a real LaTeX resume clean enough to parse by coordinates —
and rejected doing so, because those coordinates are LaTeX-specific. A Word resume has
different fonts, different sizes, hyphens instead of bullet glyphs, and headings in upper
case. A rules-based structurer tuned to one layout passes all its tests and then fails for
the first student whose resume came out of something else, silently.

**Everything the model returns is checked against the source text.** Recall is what the
model is for; the same freedom lets it invent. A fabrication at parse time is worse than a
missed skill, because everything downstream trusts the parsed resume — scoring would match
on a skill the student does not have, tailoring would assert it to an employer, and the gap
list would omit it as already held. Nothing would surface the error.

Identifiers are assigned here, not by the model. Content-derived, so re-parsing the same
document produces the same ids and a stored `provenance_map` still resolves.
"""

import logging
from typing import Any

from app.adapters.llm_client import LLMClient, LLMError, LLMMalformedResponse
from app.adapters.pdf_text import extract_text
from app.adapters.resume_parser import ResumeParseFailed
from app.domain.evidence import appears_in
from app.domain.parsed_resume import (
    Bullet,
    EducationEntry,
    ExperienceEntry,
    ParsedResume,
    ProjectEntry,
    derive_id,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You convert resume text into JSON. You are transcribing, not writing.

Rules, in order of importance:

1. COPY TEXT VERBATIM. Every bullet, employer, title and skill must appear in the input
   character for character. Do not rephrase, summarise, correct spelling, expand
   abbreviations, or improve grammar. If you cannot copy it exactly, omit it.
2. JOIN WRAPPED LINES. A bullet often continues onto the next line with no marker. Join
   those into one bullet separated by a single space. Never emit a continuation line as
   its own bullet.
3. DATES EXACTLY AS WRITTEN. "January 2026 - Present" and "Aug 2023" stay in those forms.
   Never convert to a standard format, never infer a missing year, never guess an end date.
4. ADD NOTHING. No skills the text does not list. No inferred seniority. No employer you
   worked out from context. Absent is a valid answer; invented is not.
5. ONE SKILL PER ENTRY. Resumes group skills as "Languages: Java, Python, SQL". Return
   "Java", "Python", "SQL" as separate entries and never the group label. Keep a bracketed
   qualifier attached: "AWS (lambda, IAM)" is one skill, not three.

Layouts vary. Section headings may be upper case or title case. Bullets may use a glyph,
a hyphen, or nothing at all. The employer may come before or after the job title, and the
date may sit on the title line, the employer line, or its own line. Read what is there.

Projects are a separate section from experience, and often the most substantial part of a
graduate resume. Headings include "Projects", "Personal Projects", "Academic Projects",
"Technical Projects" and "Selected Work". Put them in "projects", never in "experience":
nobody employed the student to build them, and inventing an employer for a personal project
puts a company on their resume that does not exist. A project frequently has no dates, which
is fine — return an empty string. Course work described under an education entry stays where
it is; only a distinct projects section becomes a project.

Return exactly this shape:

{
  "summary": "string, verbatim from the text, or empty",
  "skills": ["string", ...],
  "experience": [
    {"employer": "string", "title": "string", "dates": "string", "bullets": ["string", ...]}
  ],
  "projects": [
    {"name": "string", "dates": "string", "bullets": ["string", ...]}
  ],
  "education": [
    {"institution": "string", "credential": "string", "dates": "string"}
  ]
}
"""


class RealResumeParser:
    """pdfplumber extraction, model structuring, evidence checking."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def parse(self, pdf_bytes: bytes) -> ParsedResume:
        # Raises ResumeUnreadable when there is no text layer — a scan or an encrypted
        # file. Distinct from a structuring failure, because the student can act on it.
        raw_text = extract_text(pdf_bytes)

        try:
            payload = await self._llm.complete_json(
                system=SYSTEM_PROMPT,
                user=f"Resume text:\n\n{raw_text}",
                max_output_tokens=8192,
            )
        except LLMMalformedResponse as exc:
            raise ResumeParseFailed from exc
        except LLMError as exc:
            # Unavailable is still a parse failure from the student's point of view; the
            # message tells them their file is saved and to retry.
            raise ResumeParseFailed from exc

        return _build(payload, raw_text)


def _build(payload: dict[str, object], raw_text: str) -> ParsedResume:
    """Turn a model response into a `ParsedResume`, keeping only evidenced content."""
    experience = _experience(payload.get("experience"), raw_text)
    projects = _projects(payload.get("projects"), raw_text)
    education = _education(payload.get("education"), raw_text)
    skills = _skills(payload.get("skills"), raw_text)
    summary = _string(payload.get("summary"))

    if summary and not appears_in(summary, raw_text):
        # A written summary is the easiest thing for a model to improve. Dropped rather
        # than failed: its absence costs little, and keeping an invented one would put
        # prose the student never wrote at the top of their resume.
        logger.warning("resume parse: dropped a summary absent from the source text")
        summary = ""

    parsed = ParsedResume(
        summary=summary,
        experience=experience,
        projects=projects,
        education=education,
        skills=skills,
        raw_text=raw_text,
    )

    if parsed.is_empty():
        # Text was read, so the document was not blank — the model simply returned
        # nothing usable. Failing is honest; an empty resume would be a claim about the
        # student's history rather than a report about our processing.
        raise ResumeParseFailed
    return parsed


def _experience(value: object, raw_text: str) -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    for item in _dicts(value):
        employer = _string(item.get("employer"))
        title = _string(item.get("title"))
        if not (employer or title):
            continue

        # A fabricated employer or title is a whole invented role, not a stray detail.
        # This fails the parse rather than dropping quietly, because a resume missing a
        # job is something the student would notice and question — whereas a job they
        # never had, presented as parsed from their own document, they might believe.
        for field, text in (("employer", employer), ("title", title)):
            if text and not appears_in(text, raw_text):
                logger.error("resume parse: fabricated %s: %r", field, text)
                raise ResumeParseFailed

        entry_id = derive_id(employer, title, _string(item.get("dates")))
        entries.append(
            ExperienceEntry(
                id=entry_id,
                employer=employer,
                title=title,
                # Never validated against a format, only against presence. Normalising
                # "Summer 2025" into a range is the invention ADR 0006 exists to prevent.
                dates=_evidenced_or_blank(item.get("dates"), raw_text, kind="dates"),
                bullets=[
                    Bullet(id=derive_id(entry_id, text), text=text)
                    for text in _evidenced_strings(item.get("bullets"), raw_text, kind="bullet")
                ],
            )
        )
    return entries


def _projects(value: object, raw_text: str) -> list[ProjectEntry]:
    """Projects, held to the same evidence rules as experience.

    One difference in severity. A fabricated employer fails the whole parse, because a job the
    student never had is a claim they might believe came from their own document. A fabricated
    project name is dropped instead: the entry is skipped and the rest of the resume survives. Both
    refuse the invention; the harsher response is reserved for the harsher lie.
    """
    entries: list[ProjectEntry] = []
    for item in _dicts(value):
        name = _string(item.get("name"))
        if not name:
            continue

        if not appears_in(name, raw_text):
            logger.warning(
                "resume parse: dropped a project name absent from the source: %r", name
            )
            continue

        entry_id = derive_id("project", name, _string(item.get("dates")))
        bullets = [
            Bullet(id=derive_id(entry_id, text), text=text)
            for text in _evidenced_strings(item.get("bullets"), raw_text, kind="bullet")
        ]
        entries.append(
            ProjectEntry(
                id=entry_id,
                name=name,
                dates=_evidenced_or_blank(item.get("dates"), raw_text, kind="dates"),
                bullets=bullets,
            )
        )
    return entries


def _education(value: object, raw_text: str) -> list[EducationEntry]:
    entries: list[EducationEntry] = []
    for item in _dicts(value):
        institution = _string(item.get("institution"))
        if not institution or not appears_in(institution, raw_text):
            continue
        entries.append(
            EducationEntry(
                id=derive_id(institution, _string(item.get("credential"))),
                institution=institution,
                credential=_evidenced_or_blank(
                    item.get("credential"), raw_text, kind="credential"
                ),
                dates=_evidenced_or_blank(item.get("dates"), raw_text, kind="dates"),
            )
        )
    return entries


def _atomise_skill(text: str) -> list[str]:
    """Split a grouped skill line into individual skills.

    Resumes very often write skills as `Languages: Java, Python, SQL`, and a model asked
    for a skill list will happily return that whole line as one entry. Left alone it is
    quietly destructive: skill overlap is 40% of the match score in ADR 0003, and
    comparing a job's `Python` requirement against a stored `Languages: Java, Python, SQL`
    matches nothing. Every score would be wrong, and nothing would look broken.

    Done here rather than only in the prompt because it is a structural requirement, and
    relying on prompt compliance for structure means one model revision away from silent
    breakage. The prompt asks as well; this enforces.

    Commas inside brackets are not separators — `AWS (lambda, IAM, VPC)` is one skill, and
    splitting it would produce `AWS (lambda` and `VPC)`.
    """
    # Drop a leading group label: everything before the first colon, when what follows is
    # substantial. A bare `C:` style skill is not realistic, but a short tail would be.
    if ":" in text:
        label, _, tail = text.partition(":")
        if len(label) <= 40 and len(tail.strip()) > 2:
            text = tail

    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))

    return [part.strip(" \t\u2022-") for part in parts if part.strip(" \t\u2022-")]


def _skills(value: object, raw_text: str) -> list[str]:
    """Atomic, evidenced, de-duplicated skills in the order given."""
    candidates: list[str] = []
    for item in _strings(value):
        candidates.extend(_atomise_skill(item))
    return _evidenced_strings(candidates, raw_text, kind="skill")


def _evidenced_strings(value: object, raw_text: str, *, kind: str) -> list[str]:
    """Keep the strings that appear in the source, in order, without duplicates.

    Dropped rather than fatal. An invented skill or a rewritten bullet is additive noise:
    removing it leaves the resume correct, just less complete. That is a better outcome
    than refusing the whole upload over one hallucinated line.
    """
    kept: list[str] = []
    seen: set[str] = set()
    for item in _strings(value):
        if not appears_in(item, raw_text):
            logger.warning("resume parse: dropped %s absent from source: %r", kind, item)
            continue
        if item.casefold() in seen:
            continue
        seen.add(item.casefold())
        kept.append(item)
    return kept


def _evidenced_or_blank(value: object, raw_text: str, *, kind: str) -> str:
    text = _string(value)
    if text and not appears_in(text, raw_text):
        logger.warning("resume parse: dropped %s absent from source: %r", kind, text)
        return ""
    return text


def _dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
