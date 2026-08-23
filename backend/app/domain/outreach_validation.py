"""Checking a written email before a student is shown it.

Tailoring validates each bullet against its own source, because moving Python into the retail job
produces a sentence that is false about that job (ADR 0006). An email is different in a way that
matters: it is one message from one person about their whole background, so the corpus it may draw on
is the whole resume rather than a single line. Claiming Python in an email is true if the student
knows Python; claiming it in a bullet about a till is not.

What does not change is the subset test. Everything the message asserts must already be somewhere in
the evidence given to the writer. The model gets the resume and the posting, and the posting is
vocabulary only — a skill that appears in the job description and nowhere in the resume is exactly the
skill a graduate must not claim, and it is the single most likely fabrication, because the model can
see that claiming it would make the email fit better.

The second check has no equivalent in tailoring: **phrases that make a message read as generated.**
This is not a matter of taste. Recruiters have been trained by volume to recognise them, and a
graduate whose email opens "I hope this email finds you well" and describes themselves as a
"passionate developer with a proven track record" has been actively harmed by the tool that wrote it -
the reader stops at the first line. Refusing them is cheap and the effect is large. Sources for the
list are recorded beside it.

Neither check can be done by asking the model nicely. A prompt that says "do not invent skills" is
what every competitor ships, it fails silently, and it leaves the student nothing to audit.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.claims import extract_claims

# An introduction that runs past this has stopped being an introduction. Recruiter attention on a cold
# email is measured in seconds, and length is also the surface fabrication hides in: a model asked to
# be impressive fills space with unfalsifiable prose about collaboration and passion. 200 words is
# roughly a screen on a phone, which is where it will be read.
MAX_WORDS = 200

# Below this it is not a message. Usually the sign of a truncated or refused generation.
MIN_WORDS = 40


class OutreachRejection(StrEnum):
    ADDED_TECHNOLOGY = "added_technology"
    ADDED_NUMBER = "added_number"
    ADDED_PROPER_NOUN = "added_proper_noun"
    GENERATED_PHRASE = "generated_phrase"
    UNVERIFIABLE_CLAIM = "unverifiable_claim"
    TOO_LONG = "too_long"
    TOO_SHORT = "too_short"
    MISSING_SUBSTANCE = "missing_substance"
    EMPTY = "empty"


# Openers, filler and self-description that mark a message as machine-written.
#
# Sources: Topo's field guides to AI tells in outreach (Oct 2025), which name the formal opener, the
# jargon-stuffed value proposition and the vague self-praise as the three recognisable failures; and
# Forbes on cold emails that read as human (Jun 2026), whose test is whether the sentence is something
# you would say out loud to a person.
#
# The list is deliberately about *phrases*, not words. Banning "experience" would be absurd; banning
# "wealth of experience" costs nothing a real sentence needs.
_GENERATED_PHRASES: tuple[str, ...] = (
    "i hope this email finds you well",
    "i hope this message finds you well",
    "i trust this email finds you well",
    "i hope you are doing well",
    "i hope this finds you well",
    "hope you're doing well",
    "i am writing to express my interest",
    "i am writing to apply",
    "i would like to express my keen interest",
    "please find attached my resume for your consideration",
    "i believe i would be a valuable asset",
    "i am confident that my skills",
    "wealth of experience",
    "proven track record",
    "unique blend",
    "perfect fit",
    "ideal candidate",
    "dream job",
    "dream company",
    "passionate about",
    "deeply passionate",
    "i am excited about the opportunity",
    "thrilled at the prospect",
    "delighted to",
    "it would be an honour",
    "it would be an honor",
    "leverage my skills",
    "leverage my expertise",
    "synergy",
    "synergies",
    "revolutionize",
    "revolutionise",
    "cutting-edge",
    "fast-paced world",
    "in today's competitive",
    "embark on a journey",
    "delve into",
    "i look forward to hearing from you at your earliest convenience",
    "thank you for your time and consideration",
    "does not hesitate to",
    "please do not hesitate to contact me",
    "i would love to connect",
    "circle back",
    "touch base",
)

# Claims about a relationship, a history or a feeling that no data Reachly holds can support.
#
# These are worse than jargon because they are checkable, and false. A recruiter who reads "I have
# followed your work for years" and knows the company is eighteen months old has learned something
# specific about the sender. The rule is that the message may state what the student has done and what
# the posting says, and may not narrate a past with the company.
_UNVERIFIABLE: tuple[str, ...] = (
    "i have long admired",
    "i have always admired",
    "i have followed your",
    "i've followed your",
    "i have been following",
    "i've been a fan",
    "i am a huge fan",
    "as we discussed",
    "as we spoke",
    "it was great meeting",
    "great to meet you",
    "following up on our",
    "your recent linkedin post",
    "i saw your post",
    "i read your blog",
    "i listened to your podcast",
    "your recent funding round",
    "i have been using your product",
    "i've been using your product",
    "as a long-time user",
    "i grew up",
    "since childhood",
    "my whole life",
    "my entire career",
    "years of experience in",
)


@dataclass(frozen=True)
class OutreachValidation:
    ok: bool
    reason: OutreachRejection | None = None
    detail: str = ""


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9%+#'’-]+", text)  # noqa: RUF001 - curly apostrophes occur


# Words as the corpus offers them, for the name check. Punctuation is excluded so a sentence-final
# "Acme." in the message still matches a plain "Acme" in the resume.
_WORD_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#'’-]*")  # noqa: RUF001 - as above


def validate_outreach(
    body: str,
    *,
    corpus: str,
    company: str,
    job_title: str,
) -> OutreachValidation:
    """Require the message to assert nothing the corpus does not already contain.

    `corpus` is everything the student can legitimately claim: their resume, plus the company and role
    names, plus any count Reachly derived. The job description is deliberately **not** part of it. A
    posting mentioning Kubernetes does not make a graduate a Kubernetes engineer, and letting the
    description into the corpus would license precisely the fabrication that matters most.
    """
    if not body or not body.strip():
        return OutreachValidation(False, OutreachRejection.EMPTY)

    lowered = body.casefold()

    for phrase in _GENERATED_PHRASES:
        if phrase in lowered:
            return OutreachValidation(False, OutreachRejection.GENERATED_PHRASE, phrase)

    for phrase in _UNVERIFIABLE:
        if phrase in lowered:
            return OutreachValidation(False, OutreachRejection.UNVERIFIABLE_CLAIM, phrase)

    count = len(_words(body))
    if count > MAX_WORDS:
        return OutreachValidation(False, OutreachRejection.TOO_LONG, str(count))
    if count < MIN_WORDS:
        return OutreachValidation(False, OutreachRejection.TOO_SHORT, str(count))

    # An introduction that never names the role it is about is not usable, and is a common failure
    # when a model is given a long resume and loses the brief.
    if job_title.casefold() not in lowered and company.casefold() not in lowered:
        return OutreachValidation(
            False, OutreachRejection.MISSING_SUBSTANCE, "role and company"
        )

    # The corpus includes the company and title so naming them is not an invention.
    permitted = extract_claims(f"{corpus}\n{company}\n{job_title}")
    asserted = extract_claims(body)

    added_tech = asserted.technologies - permitted.technologies
    if added_tech:
        return OutreachValidation(
            False, OutreachRejection.ADDED_TECHNOLOGY, ", ".join(sorted(added_tech))
        )

    added_numbers = asserted.numbers - permitted.numbers
    if added_numbers:
        return OutreachValidation(
            False,
            OutreachRejection.ADDED_NUMBER,
            ", ".join(f"{n:g}" for n in sorted(added_numbers)),
        )

    added_names = _added_names(
        asserted.proper_nouns, corpus=f"{corpus}\n{company}\n{job_title}"
    )
    if added_names:
        return OutreachValidation(
            False, OutreachRejection.ADDED_PROPER_NOUN, ", ".join(sorted(added_names))
        )

    return OutreachValidation(True)


def _added_names(asserted: set[str], *, corpus: str) -> set[str]:
    """Names in the message that appear nowhere in the corpus.

    Deliberately not `asserted - extract_claims(corpus).proper_nouns`, which was the first attempt and
    was wrong twice over. That extractor skips the first word of every sentence — correct when reading a
    message, since every sentence starts with a capital and treating those as employers would reject
    everything, but wrong when reading the corpus, where "Backend Engineer" on its own line means
    "Backend" is never registered as permitted and is then flagged as an invention. It also compares
    exact surfaces, so the sentence-final "Acme." fails to match the corpus's "Acme".

    The right question is simply whether the word occurs in the evidence at all, in any position and any
    case. A name the corpus never contains is the invention; a name it contains is the student's own.
    """
    permitted = {word.casefold() for word in _WORD_TOKEN.findall(corpus)}
    return {name for name in asserted if name.strip(".,;:!?\"'()").casefold() not in permitted}
