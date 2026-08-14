"""Generate the sample resume PDFs used as committed test fixtures.

Run: python scripts/make_sample_resume_pdf.py

**Why fictional resumes rather than a real one.** A committed fixture has to be in the
repository, or the suite cannot run on a fresh clone — which is what CI and the judges'
testing instructions do. This repository is public, so a real resume in it would put a
name, phone number and email address on a permanent public URL. These people are
invented and the files are reproducible from this script, so a reviewer can see exactly
what each fixture contains without opening a binary.

Testing against genuinely real output still happens, separately: see
`REACHLY_REAL_RESUME_PDF` in `app/tests/conftest.py`. Those tests read a file from
outside the repository and skip when it is absent.

**Why more than one variant.** This is the point of the script. Spike 002 examined a
single real resume, produced by LaTeX. A parser validated only against that is tuned to
LaTeX whether or not anyone intended it, and the tuning is invisible — every test passes,
and the failure only appears for the first student whose resume came out of Word.

So the variants below disagree with each other on every structural decision a resume
generator makes:

| | `latex_like` | `word_like` | `plain` |
|---|---|---|---|
| Headings | Title Case | UPPER CASE | Title Case |
| Bullet marker | `•` | `-` | none |
| Date position | on the title line | own line | on the employer line |
| Order | title then employer | employer then title | employer then title |
| Skills format | `Label: a, b, c` | one per line | comma run, no label |

A parser that passes on all three, plus a real resume, is doing something more general
than pattern-matching one layout. A rule that only works for one of them will fail
loudly here rather than silently in front of a user.

**Why written by hand rather than with reportlab.** Fixtures are not worth a dependency,
and the PDF format is specified well enough to emit directly.
"""

from pathlib import Path

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "backend" / "app" / "tests" / "fixtures"
)

# WinAnsi octal escape for the bullet glyph.
BULLET = r"\225"

# The `latex_like` variant mirrors what spike 002 found in real LaTeX output: title-case
# headings, a bullet glyph, the date right-aligned onto the title line, and — most
# importantly — a bullet that wraps onto a second line carrying no marker.
LATEX_LIKE: list[tuple[str, str]] = [
    ("F2", "Alex Rivera"),
    ("F1", "alex.rivera@example.edu | (555) 0100 | Halifax, NS"),
    ("F2", "Skills"),
    ("F1", "Languages: Python, TypeScript, SQL, Java"),
    ("F1", "Frameworks: FastAPI, React, PostgreSQL, Docker"),
    ("F1", "Practices: REST APIs, CI/CD, Test-Driven Development"),
    ("F2", "Experience"),
    ("F2", "Software Developer Intern    January 2026 - Present"),
    ("F1", "Northwind Analytics"),
    ("F1", f"{BULLET} Rebuilt the nightly ingestion job to stream records instead of"),
    ("F1", "   buffering them, cutting peak memory use by 60 percent."),
    ("F1", f"{BULLET} Added integration tests around the billing export."),
    ("F2", "Web Developer Intern    Aug 2023"),
    ("F1", "Lakeside Robotics"),
    ("F1", f"{BULLET} Built an internal dashboard in React used by the support team."),
    ("F1", f"{BULLET} Migrated a legacy jQuery form to a typed React component."),
    ("F2", "Education"),
    ("F1", "Dalhousie University"),
    ("F1", "Bachelor of Computer Science, expected 2027"),
]

# Upper-case headings, hyphen bullets, employer before title, date on its own line.
# Every one of those disagrees with `latex_like`.
WORD_LIKE: list[tuple[str, str]] = [
    ("F2", "Priya Raman"),
    ("F1", "priya.raman@example.edu"),
    ("F1", "Toronto, ON"),
    ("F2", "TECHNICAL SKILLS"),
    ("F1", "Go"),
    ("F1", "Kubernetes"),
    ("F1", "Terraform"),
    ("F1", "Prometheus"),
    ("F2", "WORK EXPERIENCE"),
    ("F1", "Beacon Freight Systems"),
    ("F2", "Platform Engineering Co-op"),
    ("F1", "May 2025 to December 2025"),
    ("F1", "- Cut deployment time from 25 minutes to 4 by replacing the hand-rolled"),
    ("F1", "  release script with a reusable pipeline template."),
    ("F1", "- Wrote the runbook the on-call rotation now uses."),
    ("F2", "EDUCATION"),
    ("F1", "University of Toronto"),
    ("F1", "BSc Computer Engineering, 2026"),
]

# No bullet markers at all. Some resumes are written as short paragraphs, and a parser
# that requires a marker to recognise an achievement finds nothing here.
PLAIN: list[tuple[str, str]] = [
    ("F2", "Sam Okonkwo"),
    ("F1", "sam.okonkwo@example.edu"),
    ("F2", "Skills"),
    ("F1", "Ruby, Rails, Sidekiq, MySQL, Redis, RSpec"),
    ("F2", "Experience"),
    ("F1", "Harbour Lending, Data Engineer Intern, Summer 2025"),
    ("F1", "Replaced a nightly CSV hand-off with an incremental sync, which removed"),
    ("F1", "the daily reconciliation step the finance team had been doing manually."),
    ("F1", "Added contract tests between the two services so schema changes fail in"),
    ("F1", "CI rather than at three in the morning."),
    ("F2", "Education"),
    ("F1", "McGill University, BA Computer Science, expected 2026"),
]

VARIANTS: dict[str, list[tuple[str, str]]] = {
    "sample_resume": LATEX_LIKE,
    "sample_resume_word_like": WORD_LIKE,
    "sample_resume_plain": PLAIN,
}


def _escape(text: str) -> str:
    # Backslashes pass through: the bullet is already an octal escape.
    return text.replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[tuple[str, str]]) -> bytes:
    parts = ["BT", "14 TL", "50 742 Td"]
    for index, (font, text) in enumerate(lines):
        size = 16 if index == 0 else (11 if font == "F2" else 10)
        parts.append(f"/{font} {size} Tf")
        parts.append(f"({_escape(text)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def build_pdf(lines: list[tuple[str, str]]) -> bytes:
    stream = _content_stream(lines)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, lines in VARIANTS.items():
        target = FIXTURE_DIR / f"{name}.pdf"
        target.write_bytes(build_pdf(lines))
        print(f"wrote {target.name} ({target.stat().st_size} bytes)")
