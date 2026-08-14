"""The `DEMO_MODE` resume parser.

Real extraction, recorded structuring. The whole feature works with no API key, which
is the path judges use.

The split matters. Extraction actually runs, so an unreadable PDF is detected for the
real reason rather than by matching a known hash — a judge who uploads a scan in demo
mode gets the correct error and the correct advice. Only the structuring step, the one
that needs a model in ticket 06, is substituted.
"""

from app.adapters.fixtures.recorded_resumes import sample_parsed_resume
from app.adapters.pdf_text import extract_text
from app.domain.parsed_resume import ParsedResume


class FixtureResumeParser:
    """Recorded structuring of genuinely extracted text."""

    async def parse(self, pdf_bytes: bytes) -> ParsedResume:
        # Runs for its error behaviour: raises ResumeUnreadable when there is no text
        # layer. The extracted text is not structured here — that is what a model does
        # in ticket 06 — so the recorded resume is returned whole, including its own
        # raw_text.
        #
        # Returning the recorded raw_text rather than this document's is deliberate. The
        # ADR 0006 contract is that nothing in a parsed resume is absent from its
        # raw_text, and pairing recorded roles with a stranger's extracted text would
        # break that invariant inside the demo path — the one place it is most visible.
        extract_text(pdf_bytes)
        return sample_parsed_resume()
