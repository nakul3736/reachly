"""Byte fixtures for upload tests.

These are the smallest inputs that exercise the storage path. A real multi-page PDF
with a messy text layer belongs with the parser in ticket 06 — this ticket stores
bytes without reading them, so a valid header is the whole contract.
"""

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
    """A valid-header PDF padded to an exact size, for testing the cap."""
    padding = b"%" + b"a" * max(0, total_bytes - len(MINIMAL_PDF) - 1)
    return MINIMAL_PDF + padding
