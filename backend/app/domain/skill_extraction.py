"""Finding skills in free text, deterministically.

The whole difficulty is boundaries. Skill names are short, punctuated, and contained inside each
other: `R` lives inside `React`, `Go` inside `Django` and `Mongo`, `Java` inside `JavaScript`,
`C`
inside `C++` and inside most English words. A substring search returns a set that looks full and
means nothing, and because skill overlap is 40% of the score, nothing downstream would look
broken.

**The text is tokenised once and tokens are looked up, rather than searching the text for each
of
450 terms.** Two reasons, and the first is correctness rather than speed:

- Containment stops being possible. `JavaScript` is one token, so `Java` cannot match inside it;
  `Django` is one token, so `Go` cannot. With a regex alternation this has to be prevented by
  lookarounds on every branch, and any term whose edges are punctuated — `.NET`, `C++`, `C#` —
  needs a different guard from the others. Tokenising makes the guard structural.
- It is an order of magnitude faster. The alternation took 2.15s for twenty real-sized
  descriptions against a 1.0s budget for a page render; token lookup is a dictionary hit per
  word.

Tokens keep the punctuation that belongs to skill names — `C++`, `C#`, `.NET`, `Node.js`,
`CI/CD`,
`scikit-learn` — and drop the punctuation that belongs to the sentence.
"""

import re

from app.domain.skills_vocabulary import VOCABULARY

# A token starts with a letter or digit, or with the dot that begins `.NET`, and continues
# through the characters that appear inside skill names.
_TOKEN = re.compile(r"\.?[A-Za-z0-9][A-Za-z0-9+#./\-]*")

# Trailing sentence punctuation swept up by the token pattern: `C++.` and `Python,` and
# `Node.js/` all end in characters the name does not own. Leading dots are kept, because `.NET`
# needs its own.
_TRAILING_JUNK = re.compile(r"[./\-]+$")

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in VOCABULARY.items():
    _ALIAS_TO_CANONICAL[_canonical.casefold()] = _canonical
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias.casefold()] = _canonical

# Terms whose lowercase form is an ordinary English word, and which therefore only count when
# written in their own case. `it` is the pronoun in every description ever written; `go` is a
# verb; `excel`, `spark`, `rust`, `swift`, `sap` and `unity` are all common nouns or verbs.
#
# This is the difference between a vocabulary that reads a description and one that hallucinates
# a technology stack out of ordinary prose.
_CASE_SENSITIVE = frozenset(
    {
        "IT",
        "C",
        "R",
        "Go",
        "ML",
        "SAP",
        "CAD",
        "Swift",
        "Rust",
        "Dart",
        "Excel",
        "Spark",
        "Jest",
        "Unity",
        "Sass",
    }
)
_CASE_SENSITIVE_FOLDED = frozenset(term.casefold() for term in _CASE_SENSITIVE)

# Skills whose whole name is one character. Case-sensitivity is not enough for these: real
# postings contain a standalone capital `C` as a list marker, a section label, a grade and a
# vitamin, and one of them turned up in a SpaceX posting with no C anywhere in it.
#
# A one-letter language name only means the language in the company of other technologies —
# "Python, R, and SQL" — so that is what is required. The window is deliberately small, because
# the evidence is proximity in a list rather than mere presence in the same document.
_SINGLE_LETTER = frozenset({"C", "R"})
_COMPANION_WINDOW = 60

# The longest phrase in the vocabulary, so n-gram assembly knows where to stop.
_MAX_PHRASE_TOKENS = max(len(alias.split()) for alias in _ALIAS_TO_CANONICAL)


def _tokenise(text: str) -> list[tuple[str, int]]:
    """Tokens with their offsets, because proximity decides the single-letter cases."""
    tokens: list[tuple[str, int]] = []
    for match in _TOKEN.finditer(text):
        cleaned = _TRAILING_JUNK.sub("", match.group(0))
        if cleaned:
            tokens.append((cleaned, match.start()))
    return tokens


def _resolve(phrase: str) -> str | None:
    """The canonical skill for a phrase exactly as it was written, or None.

    A phrase whose folded form is one of the ambiguous terms only counts when its case matches,
    so `IT support` is the field and `if it works` is not.
    """
    folded = phrase.casefold()
    canonical = _ALIAS_TO_CANONICAL.get(folded)
    if canonical is None:
        return None
    if folded in _CASE_SENSITIVE_FOLDED and phrase not in _CASE_SENSITIVE:
        return None
    return canonical


def canonical_skill(term: str) -> str | None:
    """The canonical name for a surface form, or None if it is not a known skill.

    Used for the resume side too: a student who wrote `JS` and a posting that wrote `JavaScript`
    have to arrive at the same string, or the overlap is zero for no reason.

    Case is not enforced here. A term arriving through this function was already identified as a
    skill by a human writing a skills section, so `python` is the language rather than the
    snake;
    the ambiguity this guards against only exists in running prose.
    """
    return _ALIAS_TO_CANONICAL.get(term.strip().casefold())


def extract_skills(text: str) -> set[str]:
    """Canonical skills named in the text.

    A set, deliberately: a description repeating `Python` four times does not want it four
    times, and how often a term appears is BM25's job in the keyword component.
    """
    if not text or not text.strip():
        return set()

    tokens = _tokenise(text)

    # Matches are collected with their offsets first, because whether a one-letter name counts
    # depends on what else was found near it.
    matches: list[tuple[str, int]] = []
    for index, (_, offset) in enumerate(tokens):
        # Longest phrase first, so `React Native` is found rather than `React`, and
        # `machine learning` rather than nothing.
        upper = min(_MAX_PHRASE_TOKENS, len(tokens) - index)
        for length in range(upper, 0, -1):
            phrase = " ".join(token for token, _ in tokens[index : index + length])
            canonical = _resolve(phrase)
            if canonical is not None:
                matches.append((canonical, offset))
                break

    unambiguous = [(name, offset) for name, offset in matches if name not in _SINGLE_LETTER]
    found = {name for name, _ in unambiguous}

    for name, offset in matches:
        if name not in _SINGLE_LETTER:
            continue
        near = any(
            abs(other_offset - offset) <= _COMPANION_WINDOW
            for other_name, other_offset in unambiguous
            if other_name != name
        )
        if near:
            found.add(name)

    return found


def normalise_skill_list(skills: list[str]) -> set[str]:
    """Canonicalise skills that arrived already separated, as on a parsed resume.

    A term the vocabulary does not know is kept as written rather than dropped. The student put
    it
    on their resume; Reachly not recognising it is Reachly's gap, and discarding it would
    silently
    shrink the profile every score is computed against.
    """
    normalised: set[str] = set()
    for skill in skills:
        cleaned = skill.strip()
        if not cleaned:
            continue
        normalised.add(canonical_skill(cleaned) or cleaned)
    return normalised
