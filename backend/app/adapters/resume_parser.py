"""The resume parsing seam.

Seam 2 from the spec design. The protocol exists so the pdfplumber path can be
exercised against real messy bytes in ticket 06 while everything upstream is tested
against a recorded outcome — and so `DEMO_MODE` has something to substitute.
"""

import hashlib
from typing import Protocol

from app.domain.parsed_resume import ParsedResume
from app.errors import DomainError


class ResumeParserError(DomainError):
    """Base for parse failures. Never raised directly."""


class ResumeUnreadable(ResumeParserError):
    """The file yielded no text.

    A scanned or encrypted resume. Distinct from a structuring failure because the
    student can act on this one: export a text-based PDF instead of an image.
    """

    status_code = 422
    code = "resume_unreadable"
    message = (
        "We could not read any text in that PDF. If it is a scan or an image, "
        "export it from your editor as a PDF instead and upload it again."
    )


class ResumeParseFailed(ResumeParserError):
    """Text was read but could not be structured.

    Not something the student can fix, so the message does not pretend otherwise and
    does not blame their file.
    """

    status_code = 502
    code = "resume_parse_failed"
    message = (
        "We read your resume but could not break it into sections just now. "
        "Your file is saved — try again in a moment."
    )


class ResumeParser(Protocol):
    """Turn PDF bytes into a structured resume.

    Raises `ResumeUnreadable` or `ResumeParseFailed`. Never returns an empty result to
    signal a failure: an empty resume and a failed parse are different facts, and a
    caller that cannot tell them apart will show the student a blank resume with no
    explanation.
    """

    async def parse(self, pdf_bytes: bytes) -> ParsedResume: ...


def fingerprint(pdf_bytes: bytes) -> str:
    """Content hash, used to key recorded outcomes and to derive stable ids."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def get_resume_parser() -> ResumeParser:
    """The parser for the current configuration.

    The same `RealResumeParser` in both modes. Only the inference client differs, so
    `DEMO_MODE` still runs real extraction, real evidence checking and real identifier
    derivation — a fixture that returned a finished result would skip the code most
    likely to be wrong, and a judge running the demo path would be testing a different
    program.
    """
    from app.adapters.llm_client import get_llm_client
    from app.adapters.real_resume_parser import RealResumeParser

    return RealResumeParser(get_llm_client())
