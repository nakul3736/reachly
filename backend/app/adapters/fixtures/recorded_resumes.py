"""Recorded parse outcomes for `DEMO_MODE`.

The whole feature has to work with no API key, because that is the path judges use.
These are the recorded results the fixture parser returns.

Built in Python rather than loaded from JSON, deliberately: at this point there is no
provider payload to record — the real structurer arrives in ticket 06, and *its*
response is what gets captured as JSON then. A JSON file here would imply a recording
that does not exist.

Unhappy paths are recorded too, per `.kiro/steering/testing.md`. An adapter that only
has a success fixture is an adapter whose error handling has never run.
"""

from app.domain.parsed_resume import (
    Bullet,
    EducationEntry,
    ExperienceEntry,
    ParsedResume,
    derive_id,
)

# The text as pdfplumber actually extracts it from
# app/tests/fixtures/sample_resume.pdf. Kept verbatim, including the wrapped bullet
# split across two lines, so `raw_text` is what a real parse would have retained.
SAMPLE_RAW_TEXT = """Alex Rivera
alex.rivera@example.edu | (555) 0100 | Halifax, NS
Skills
Languages: Python, TypeScript, SQL, Java
Frameworks: FastAPI, React, PostgreSQL, Docker
Practices: REST APIs, CI/CD, Test-Driven Development
Experience
Software Developer Intern January 2026 - Present
Northwind Analytics
\u2022 Rebuilt the nightly ingestion job to stream records instead of
buffering them, cutting peak memory use by 60 percent.
\u2022 Added integration tests around the billing export.
Web Developer Intern Aug 2023
Lakeside Robotics
\u2022 Built an internal dashboard in React used by the support team.
\u2022 Migrated a legacy jQuery form to a typed React component.
Education
Dalhousie University
Bachelor of Computer Science, expected 2027"""


def _entry(employer: str, title: str, dates: str, bullets: list[str]) -> ExperienceEntry:
    entry_id = derive_id(employer, title, dates)
    return ExperienceEntry(
        id=entry_id,
        employer=employer,
        title=title,
        dates=dates,
        bullets=[Bullet(id=derive_id(entry_id, text), text=text) for text in bullets],
    )


def sample_parsed_resume() -> ParsedResume:
    """The recorded structuring of `sample_resume.pdf`.

    Note the first bullet: the two physical lines from the PDF are joined into one
    bullet. That join is the behaviour spike 002 showed a line-based parser gets wrong,
    and it is what the fixture has to model — a fixture that pretended each line was its
    own bullet would let the real parser in ticket 06 ship the bug.

    Dates are exactly as written. `January 2026 - Present` and `Aug 2023` appear in the
    same document and neither is normalised.
    """
    return ParsedResume(
        summary="",
        experience=[
            _entry(
                employer="Northwind Analytics",
                title="Software Developer Intern",
                dates="January 2026 - Present",
                bullets=[
                    "Rebuilt the nightly ingestion job to stream records instead of "
                    "buffering them, cutting peak memory use by 60 percent.",
                    "Added integration tests around the billing export.",
                ],
            ),
            _entry(
                employer="Lakeside Robotics",
                title="Web Developer Intern",
                dates="Aug 2023",
                bullets=[
                    "Built an internal dashboard in React used by the support team.",
                    "Migrated a legacy jQuery form to a typed React component.",
                ],
            ),
        ],
        education=[
            EducationEntry(
                id=derive_id("Dalhousie University", "Bachelor of Computer Science"),
                institution="Dalhousie University",
                credential="Bachelor of Computer Science",
                dates="expected 2027",
            )
        ],
        # Every one of these appears verbatim in SAMPLE_RAW_TEXT. That is a contract,
        # not a coincidence — see the fabrication tests in test_resume_parser.py.
        skills=[
            "Python",
            "TypeScript",
            "SQL",
            "Java",
            "FastAPI",
            "React",
            "PostgreSQL",
            "Docker",
            "REST APIs",
            "CI/CD",
            "Test-Driven Development",
        ],
        raw_text=SAMPLE_RAW_TEXT,
    )
