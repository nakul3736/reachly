"""Byte fixtures for upload tests.

`MINIMAL_PDF` is the smallest input that exercises the storage path. It also turns out
to be the honest fixture for an *unreadable* resume: it passes the magic-byte check,
opens in pdfplumber, reports one page, and extracts an empty string — which is what a
scanned resume looks like.

`RECORDED_RESUME_PDF` is the generated fictional resume. See
`scripts/make_sample_resume_pdf.py` for what it contains and why it is not a real one.
"""

from pathlib import Path

from app.adapters.fixtures.demo_resume import demo_resume_bytes

# The primary readable resume. It lives with the adapters because the demo path and the
# seeded account both use it — see app/adapters/fixtures/demo_resume.py. It reproduces the
# three things spike 002 found in real output that break a naive parser: a wrapped bullet
# whose continuation carries no marker, two date formats in one document, and title-case
# headings.
RECORDED_RESUME_PDF = demo_resume_bytes()

# Structurally different resumes, used to make overfitting fail loudly. They disagree on
# heading case, bullet marker, date position and section order — see the comparison table
# in scripts/make_sample_resume_pdf.py.
RESUME_VARIANTS = {
    "latex_like": RECORDED_RESUME_PDF,
    **{
        path.stem.removeprefix("resume_"): path.read_bytes()
        for path in sorted(Path(__file__).parent.glob("resume_*.pdf"))
    },
}

# Minimal structurally valid PDF: header, one empty page, xref, trailer.
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)

# A PDF header is `%PDF-`. This is what a .docx, an image, or an HTML error page
# saved with the wrong extension looks like to the upload endpoint.
NOT_A_PDF = b"PK\x03\x04" + b"\x00" * 64

# Bytes that would pass an extension check and a declared-content-type check while
# being nothing of the sort.
HTML_MASQUERADING_AS_PDF = b"<!DOCTYPE html><html><body>Sign in to continue</body></html>"


def pdf_of_size(total_bytes: int) -> bytes:
    """A readable PDF padded to an exact size, for testing the cap.

    Padded after `%%EOF` so the document still parses — the trailing bytes are outside
    the structure pdfplumber reads via the xref table. Built on the readable sample
    rather than on `MINIMAL_PDF`, because upload now parses and a fixture with no text
    layer would be refused as unreadable before the size check could be observed.
    """
    padding = b"\n%" + b"a" * max(0, total_bytes - len(RECORDED_RESUME_PDF) - 2)
    return RECORDED_RESUME_PDF + padding
