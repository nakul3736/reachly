"""Turning provider description markup into prose a student can read.

Every source ships its description as markup, and two of them escape it first. Greenhouse
double-encodes — the JSON string literally contains `&lt;div&gt;` — so the text has to be
unescaped before it can be stripped. Storing it raw shows the student a wall of `&lt;p&gt;`.

Written by hand rather than with an HTML library on purpose. The job is narrow: unescape,
drop tags, keep the paragraph and list breaks that make a job description skimmable. A
parser would also faithfully reproduce the layout soup these descriptions are full of.
"""

import html
import re

# Tags whose boundaries are meaningful to a reader. Everything else collapses away.
_BREAK_BEFORE = re.compile(
    r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|table|section|blockquote)\b[^>]*>",
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")
_LIST_ITEM = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_BLANK_RUN = re.compile(r"\n{3,}")
_SPACE_RUN = re.compile(r"[ \t\u00a0]+")


def html_to_text(raw: str) -> str:
    """Readable prose from a description, preserving paragraph and bullet structure.

    Unescapes twice in effect: once because Greenhouse escapes the markup, and then again
    for the entities inside the markup itself. `&amp;amp;` in a company name is a real
    thing that appears in these payloads.
    """
    if not raw:
        return ""

    text = html.unescape(raw)

    # A second pass, because the first only revealed the markup. Entities written inside
    # that markup are still encoded, and a lone surviving `&amp;` looks like a bug to a
    # reader even though nothing crashed.
    if "&" in text:
        text = html.unescape(text)

    # Bullets first, so list items stay visually distinct once tags are gone. Without this
    # a ten-point requirements list becomes one unreadable paragraph.
    text = _LIST_ITEM.sub("\n• ", text)
    text = _BREAK_BEFORE.sub("\n", text)
    text = _TAG.sub("", text)

    # Entities can appear a third time in practice — some boards paste already-escaped
    # text into an escaped field. Cheap to be certain.
    if "&lt;" in text or "&amp;" in text:
        text = html.unescape(text)

    text = _SPACE_RUN.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_RUN.sub("\n\n", text)

    return text.strip()
