"""Reading skills out of job descriptions, once per posting.

ADR 0011. Two readings, in a fixed order:

1. The vocabulary, always. Free, identical on every run, and the floor beneath the score.
2. A model, once per posting, batched, its findings **unioned onto** the vocabulary's.

The union direction is the load-bearing decision. If a reply could replace the vocabulary's
findings, one bad response would silently lower a student's score against skills they have, and
nothing downstream would look wrong — the score would simply be a little lower, forever, for
reasons nobody could see. Adding can only make the reading more complete.

The second rule is that **a skill absent from the description is discarded**. A model asked what
a
posting requires will happily produce what a posting like it usually requires, and an invented
requirement lowers the student's score against a demand no employer made. This is the same
evidence
rule that governs tailoring, applied where nobody would ever catch a violation by eye.

Runs at refresh time, never at render time, so the feed keeps ADR 0003's promise that a student
never waits on a model and two loads never disagree.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm_client import LLMClient, LLMError
from app.domain.role_family import Seniority
from app.domain.skill_extraction import canonical_skill, extract_skills
from app.models.job import Job

logger = logging.getLogger(__name__)

# Postings per request. Twenty descriptions of five thousand characters is a hundred thousand
# characters in one prompt, which is within the model's window but slow and expensive to retry;
# ten keeps a failed batch cheap to lose.
DEFAULT_BATCH_SIZE = 10

# Postings per run. The bound exists so one refresh cannot exhaust a day's free quota, and so a
# newly registered board does not turn the next refresh into the most expensive request the
# application has ever made.
DEFAULT_MAX_JOBS = 120

# Characters of description sent per posting. Requirements are not reliably at the top, so this
# is not a prefix chosen for tidiness — it is the point where one 20,000-character posting would
# otherwise consume the whole batch's budget and starve the other nine.
MAX_DESCRIPTION_CHARS = 5_000

_COUNTRIES = ("US", "CA")

_SYSTEM = """You read job descriptions and list the skills each one requires.

Rules:
- List only skills that are actually named or plainly described in the text you are given.
- Do not add skills that postings like this one usually want. If the text does not support it,
  leave it out.
- Prefer the ordinary name of the skill: "Kubernetes", not "container orchestration platform".
- Include soft skills only when the description names them.
- Return at most 25 skills per posting.

Reply with JSON only: {"postings": [{"id": "<the id given>", "skills": ["...", "..."]}]}"""


@dataclass
class EnrichmentSummary:
    considered: int = 0
    enriched: int = 0
    batches: int = 0
    failed_batches: int = 0
    added_by_model: int = 0
    discarded: int = 0
    basis_counts: dict[str, int] = field(default_factory=dict)


# Words that carry no evidence of their own inside a skill name. `infrastructure as code` is
# supported by `infrastructure` and `code`; requiring `as` to appear proves nothing.
_SKILL_STOPWORDS = frozenset(
    {"as", "of", "and", "or", "in", "on", "the", "a", "an", "with", "to", "for"}
)

# Suffixes stripped to compare word forms. This exists for one specific reason: the model's most
# valuable findings are the ones the vocabulary cannot reach, and they arrive nominalised. A
# description saying "comfortable owning a service end to end" supports `service ownership`, and
# a
# literal substring test rejects it — throwing away exactly the readings enrichment was added
# for.
#
# Stripped repeatedly, so `ownership` reduces through `owner` to `own` and meets `owning`.
_SUFFIXES = ("ship", "ment", "ance", "ence", "ing", "ity", "ies", "ed", "er", "es", "s")
_MIN_STEM = 3

# Suffix tables do not reach nominalisation. A live run discarded `shipment coordination` from a
# description reading "Coordinate inbound and outbound shipments", and `carrier negotiation`
# from
# "negotiate collection windows with carriers" — both genuinely present, both rejected, because
# coordinate/coordination and negotiate/negotiation share no suffix rule.
#
# Comparing prefixes covers the whole family without a table per English form. Six characters is
# long enough that `management` and `manifest` do not meet, and short enough that
# `negotiate`/`negotiation` do.
_MIN_SHARED_PREFIX = 6


def _stem(word: str) -> str:
    current = word.casefold()
    for _ in range(2):
        for suffix in _SUFFIXES:
            if current.endswith(suffix) and len(current) - len(suffix) >= _MIN_STEM:
                current = current[: -len(suffix)]
                break
        else:
            break
    return current


_WORD = re.compile(r"[A-Za-z0-9+#.]+")


def _stems(text: str) -> set[str]:
    return {_stem(word) for word in _WORD.findall(text)}


def _shares_prefix(word: str, candidates: set[str]) -> bool:
    folded = word.casefold()
    if len(folded) < _MIN_SHARED_PREFIX:
        return False
    head = folded[:_MIN_SHARED_PREFIX]
    return any(candidate.startswith(head) for candidate in candidates)


def _is_evidenced(skill: str, description: str) -> bool:
    """Whether the posting's own text supports this skill.

    Four ways it can, in widening order:

    - the skill's own text appears;
    - a known alias appears, so `k8s` supports `Kubernetes` and rejecting the model's correct
      expansion would discard a real finding;
    - every content word appears in some inflected form, so `owning a service` supports
      `service ownership`;
    - every content word shares a long prefix with a word that appears, so `Coordinate ...
      shipments` supports `shipment coordination`.

    What none of these permit is a skill whose words are simply absent. That is what this guard
    exists for: a model asked what a posting requires will otherwise produce what postings like
    it
    usually require, and an invented requirement lowers the student's score against a demand no
    employer ever made.
    """
    haystack = description.casefold()
    if skill.casefold() in haystack:
        return True

    canonical = canonical_skill(skill)
    if canonical is not None and canonical in extract_skills(description):
        return True

    words = [w for w in _WORD.findall(skill) if w.casefold() not in _SKILL_STOPWORDS]
    if not words:
        return False

    available_stems = _stems(description)
    available_words = {w.casefold() for w in _WORD.findall(description)}
    return all(
        _stem(word) in available_stems or _shares_prefix(word, available_words)
        for word in words
    )


class PostingLike(Protocol):
    """What the prompt builder actually needs from a posting.

    A protocol rather than `Job` because these two functions read three attributes and touch no
    database, which is what lets the live test exercise the real prompt and the real evidence
    rule against hand-written descriptions without a session.
    """

    @property
    def source_job_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def description(self) -> str: ...


def _prompt_for(batch: Sequence[PostingLike]) -> str:
    parts: list[str] = []
    for job in batch:
        description = (job.description or "")[:MAX_DESCRIPTION_CHARS]
        parts.append(f"id: {job.source_job_id}\ntitle: {job.title}\n{description}")
    return "\n\n---\n\n".join(parts)


async def _ask(llm: LLMClient, batch: Sequence[PostingLike]) -> dict[str, list[str]]:
    """One request for the whole batch, answers keyed by the id we supplied.

    Keyed rather than positional because a model reorders its replies, and a positional read
    would attach one posting's skills to another — the same mistake dedup had to avoid when it
    numbered its pairs.
    """
    reply = await llm.complete_json(
        system=_SYSTEM, user=_prompt_for(batch), max_output_tokens=2048
    )

    postings = reply.get("postings")
    if not isinstance(postings, list):
        raise ValueError(f"expected a postings list, got {type(postings).__name__}")

    answers: dict[str, list[str]] = {}
    for entry in postings:
        if not isinstance(entry, dict):
            continue
        job_id = entry.get("id")
        skills = entry.get("skills")
        if isinstance(job_id, str) and isinstance(skills, list):
            answers[job_id] = [s for s in skills if isinstance(s, str) and s.strip()]
    return answers


async def _candidates(session: AsyncSession, limit: int) -> list[Job]:
    """Postings worth reading: open, unread, described, and reachable by a graduate.

    Senior postings and postings outside the US and Canada are excluded because no student using
    Reachly will ever see them, so reading them would be paying for pages nobody opens. Unknown
    seniority is included deliberately — a plain `Software Engineer` is often exactly right for
    a
    graduate, and it is the single largest group in the index.
    """
    stmt = (
        select(Job)
        .where(
            Job.closed_at.is_(None),
            Job.canonical_job_id.is_(None),
            Job.skills_extracted_at.is_(None),
            Job.description != "",
            Job.country.in_(_COUNTRIES),
            Job.seniority != Seniority.SENIOR.value,
        )
        # Entry-level first: those are the postings a graduate reaches soonest, so if a run is
        # bounded they are the ones worth spending the budget on.
        .order_by(
            (Job.seniority == Seniority.ENTRY.value).desc(),
            Job.first_seen_at.desc(),
        )
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def enrich_job_skills(
    session: AsyncSession,
    *,
    llm: LLMClient | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_jobs: int = DEFAULT_MAX_JOBS,
) -> EnrichmentSummary:
    """Read skills for postings that have none, and record what read them.

    `llm` is optional and everything works without it, exactly as in dedup: the deployed demo
    has
    no key, and a feature that quietly did nothing there would be a feature the judges never
    see.
    """
    summary = EnrichmentSummary()
    jobs = await _candidates(session, max_jobs)
    summary.considered = len(jobs)
    if not jobs:
        return summary

    now = datetime.now(UTC)

    for start in range(0, len(jobs), batch_size):
        batch = jobs[start : start + batch_size]

        # The floor, computed for every posting whether or not the model is reachable.
        floors = {job.id: extract_skills(job.description or "") for job in batch}

        answers: dict[str, list[str]] = {}
        batch_failed = False
        if llm is not None:
            summary.batches += 1
            try:
                answers = await _ask(llm, batch)
            except (LLMError, ValueError, KeyError, TypeError) as exc:
                # An outage is not a reading. Nothing is timestamped, so the next run retries,
                # and the vocabulary result is still written because it is correct on its own.
                logger.warning("skill enrichment batch failed: %s", exc)
                summary.failed_batches += 1
                batch_failed = True

        for job in batch:
            skills = set(floors[job.id])

            # The title is part of the posting, so a skill named there is evidenced. `Patient
            # Care
            # Assistant` supports `patient care` even when the body only says "residents".
            evidence = f"{job.title}\n{job.description or ''}"

            proposed = answers.get(job.source_job_id, [])
            for raw in proposed:
                skill = raw.strip()
                if not skill:
                    continue
                if not _is_evidenced(skill, evidence):
                    summary.discarded += 1
                    continue
                # Canonicalise so the model's phrasing and the vocabulary's agree, then add.
                resolved = canonical_skill(skill) or skill
                if resolved not in skills:
                    summary.added_by_model += 1
                skills.add(resolved)

            enriched_by_model = llm is not None and not batch_failed
            basis = "model" if enriched_by_model else "vocabulary"

            job.extracted_skills = sorted(skills)
            job.skills_basis = basis
            # Only a finished reading gets a timestamp. A failed batch leaves this null so the
            # posting is picked up again, rather than being remembered as read.
            if not batch_failed:
                job.skills_extracted_at = now
                summary.enriched += 1
                summary.basis_counts[basis] = summary.basis_counts.get(basis, 0) + 1

    # Committed, not flushed. This currently survives only because `deduplicate` runs afterwards in
    # the same cron session and commits, which is an accident: reordering the cycle, or a
    # deduplication failure, would silently discard a batch of model calls that had already been
    # paid for. It also puts the "enrichment failure never timestamps, so it is retried" invariant
    # at the mercy of a function that knows nothing about it.
    await session.commit()
    return summary
