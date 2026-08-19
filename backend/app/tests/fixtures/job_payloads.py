"""Provider payloads recorded from the live APIs.

Recorded, never hand-authored. A fixture written to match the parser proves only that it was
written to match the parser. These carry the details nobody would invent: HTML-escaped
descriptions, multi-location strings joined with a bullet character, and Figma's real board
containing no entry-level software roles at all.
"""

import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parents[2] / "adapters" / "fixtures"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return data


def _load_list(name: str) -> list[dict[str, Any]]:
    """Lever returns a bare array, so its fixture is a list rather than an object."""
    data: list[dict[str, Any]] = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return data


GREENHOUSE_BOARD = _load("greenhouse_board.json")
LEVER_BOARD = _load_list("lever_board.json")
ASHBY_BOARD = _load("ashby_board.json")
MUSE_PAGE = _load("muse_page.json")
