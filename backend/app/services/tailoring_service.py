"""Tailoring a resume to one posting, with every rewrite checked against its source.

The shape is fixed by ADR 0006: generate, validate, retry once naming what was rejected, and on a
second failure keep the student's own bullet unchanged. The validator is deterministic and runs on
every bullet including the retry, so nothing reaches the student that has not been checked.

One request for the whole resume, not one per bullet. A resume has fifteen to thirty bullets and
per-bullet calls would make this the most expensive operation in the product for no benefit — the
validation that matters is per bullet regardless of how the text arrived.

Falling back rather than dropping: a failed rewrite costs polish and never costs content, because
the original sentence was always an acceptable answer. Recording *why* is what lets the interface
tell the student which bullets it left alone and what it caught, which is the difference between a
guarantee and a claim.
"""

import logging
from dataclasses import dataclass, field

from app.adapters.llm_client import LLMClient, LLMError
from app.domain.parsed_resume import ParsedResume
from app.domain.tailoring import RejectionReason, validate_rewrite

logger = logging.getLogger(__name__)

MAX_RETRIES = 1

_SYSTEM = """You rewrite resume bullets to match a job posting's vocabulary.

Absolute rules:
- Use ONLY facts already in the bullet you are given. Never add a technology, employer, tool,
  metric, number, product or team size that is not already there.
- You may rephrase, reorder, change emphasis, and use the posting's wording for things the bullet
  already describes.
- If a bullet cannot be improved without adding something, return it unchanged.
- Keep each rewrite close to the original length. Never expand a bullet into a paragraph.

Reply with JSON only:
{"bullets": [{"id": "<the id given>", "text": "<rewritten bullet>"}]}"""


@dataclass
class BulletOutcome:
    bullet_id: str
    original: str
    tailored: str

    # True when the text changed and the change passed validation.
    changed: bool

    # Why a rewrite was refused, when one was. None means nothing was rejected.
    rejected_reason: RejectionReason | None = None
    rejected_detail: str = ""
    rejected_text: str = ""


@dataclass
class TailoringResult:
    outcomes: list[BulletOutcome] = field(default_factory=list)
    requests_made: int = 0

    # Requirements the posting states that the resume does not support. The honest home for
    # everything tailoring is forbidden from inventing.
    gaps: list[str] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.changed)

    @property
    def rejected_count(self) -> int:
        return sum(1 for o in self.outcomes if o.rejected_reason is not None)


def _bullets_of(resume: ParsedResume) -> list[tuple[str, str]]:
    """Every bullet with its content-derived id, across all experience entries.

    Ids come from the parse (feature 01) and are content-derived rather than positional, so a
    provenance map still points at the right sentence after the resume is re-parsed.
    """
    pairs: list[tuple[str, str]] = []
    for entry in resume.experience:
        for bullet in entry.bullets:
            if bullet.text.strip():
                pairs.append((bullet.id, bullet.text))
    return pairs


def _prompt(
    bullets: list[tuple[str, str]],
    *,
    job_title: str,
    company: str,
    description: str,
    rejected: dict[str, str] | None = None,
    instructions: dict[str, str] | None = None,
) -> str:
    lines = [
        f"Posting: {job_title} at {company}",
        "",
        "Posting text (for vocabulary only — do not import facts from it):",
        description[:3000],
        "",
        "Bullets to rewrite:",
    ]
    for bullet_id, text in bullets:
        lines.append(f"- id {bullet_id}: {text}")
        # The student's own direction for this bullet, attached to the bullet rather than stated
        # once for the batch, so several bullets can carry different instructions in one request.
        # Framed as subordinate to the source: asking for a number that is not in the sentence is
        # asking for a fabrication, and the answer is a refusal from the validator rather than
        # quiet compliance here.
        if instructions and bullet_id in instructions:
            lines.append(
                f"  the student asks: {instructions[bullet_id].strip()[:400]} "
                "(follow this only as far as the bullet above supports it; do not add a fact, "
                "number, tool or employer in order to satisfy it)"
            )

    if rejected:
        lines.append("")
        lines.append(
            "Your previous attempt added things that were not in the source. Rewrite these "
            "again, and this time do not introduce the named items:"
        )
        for bullet_id, detail in rejected.items():
            lines.append(f"- id {bullet_id}: you added {detail}")

    return "\n".join(lines)


async def _ask(
    llm: LLMClient,
    bullets: list[tuple[str, str]],
    *,
    job_title: str,
    company: str,
    description: str,
    rejected: dict[str, str] | None = None,
    instructions: dict[str, str] | None = None,
) -> dict[str, str]:
    reply = await llm.complete_json(
        system=_SYSTEM,
        user=_prompt(
            bullets,
            job_title=job_title,
            company=company,
            description=description,
            rejected=rejected,
            instructions=instructions,
        ),
        max_output_tokens=4096,
    )

    entries = reply.get("bullets")
    if not isinstance(entries, list):
        raise ValueError(f"expected a bullets list, got {type(entries).__name__}")

    answers: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        bullet_id = entry.get("id")
        text = entry.get("text")
        if isinstance(bullet_id, str) and isinstance(text, str) and text.strip():
            answers[bullet_id] = text.strip()
    return answers


async def tailor_resume(
    resume: ParsedResume,
    *,
    job_title: str,
    company: str,
    description: str,
    missing_skills: list[str] | None = None,
    llm: LLMClient | None = None,
) -> TailoringResult:
    """Rewrite what can be rewritten, keep the rest, and report both.

    `llm` is optional. Without one every bullet is returned unchanged, which is a truthful answer
    rather than a broken one: the student sees their own resume and the gap list, and nothing
    claims to have been tailored.
    """
    result = TailoringResult(gaps=sorted(missing_skills or []))
    bullets = _bullets_of(resume)
    if not bullets:
        return result

    originals = dict(bullets)

    if llm is None:
        result.outcomes = [
            BulletOutcome(bullet_id=b_id, original=text, tailored=text, changed=False)
            for b_id, text in bullets
        ]
        return result

    proposed: dict[str, str] = {}
    try:
        result.requests_made += 1
        proposed = await _ask(
            llm, bullets, job_title=job_title, company=company, description=description
        )
    except (LLMError, ValueError, KeyError, TypeError) as exc:
        # An outage is not a tailoring. Every bullet falls back, and the interface says so.
        logger.warning("tailoring generation failed: %s", exc)
        result.outcomes = [
            BulletOutcome(bullet_id=b_id, original=text, tailored=text, changed=False)
            for b_id, text in bullets
        ]
        return result

    # First validation pass.
    accepted: dict[str, str] = {}
    rejected: dict[str, tuple[RejectionReason, str, str]] = {}

    for bullet_id, original in bullets:
        candidate = proposed.get(bullet_id)
        if candidate is None or candidate == original:
            continue
        verdict = validate_rewrite(original, candidate)
        if verdict.ok:
            accepted[bullet_id] = candidate
        else:
            rejected[bullet_id] = (
                verdict.reason or RejectionReason.EMPTY,
                verdict.detail,
                candidate,
            )

    # One retry, naming exactly what was added so the model has something to act on. A retry that
    # repeated the same prompt would mostly reproduce the same mistake.
    if rejected:
        retry_bullets = [(b_id, originals[b_id]) for b_id in rejected]
        try:
            result.requests_made += 1
            second = await _ask(
                llm,
                retry_bullets,
                job_title=job_title,
                company=company,
                description=description,
                rejected={b_id: detail for b_id, (_, detail, _) in rejected.items()},
            )
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            logger.warning("tailoring retry failed: %s", exc)
            second = {}

        for bullet_id in list(rejected):
            candidate = second.get(bullet_id)
            if candidate is None or candidate == originals[bullet_id]:
                continue
            verdict = validate_rewrite(originals[bullet_id], candidate)
            if verdict.ok:
                accepted[bullet_id] = candidate
                del rejected[bullet_id]
            else:
                rejected[bullet_id] = (
                    verdict.reason or RejectionReason.EMPTY,
                    verdict.detail,
                    candidate,
                )

    for bullet_id, original in bullets:
        if bullet_id in accepted:
            result.outcomes.append(
                BulletOutcome(
                    bullet_id=bullet_id,
                    original=original,
                    tailored=accepted[bullet_id],
                    changed=True,
                )
            )
        elif bullet_id in rejected:
            reason, detail, text = rejected[bullet_id]
            result.outcomes.append(
                BulletOutcome(
                    bullet_id=bullet_id,
                    original=original,
                    tailored=original,
                    changed=False,
                    rejected_reason=reason,
                    rejected_detail=detail,
                    rejected_text=text,
                )
            )
        else:
            result.outcomes.append(
                BulletOutcome(
                    bullet_id=bullet_id, original=original, tailored=original, changed=False
                )
            )

    return result


@dataclass(frozen=True)
class RevisionRequest:
    """One bullet the student wants changed, and what they said about it."""

    bullet_id: str
    original: str
    instruction: str


async def revise_bullets(
    requests: list[RevisionRequest],
    *,
    job_title: str,
    company: str,
    description: str,
    llm: LLMClient | None = None,
) -> list[BulletOutcome]:
    """Rewrite several bullets again from the student's feedback, in one request.

    One model call for the whole batch, and at most two — the same ceiling as the initial tailoring,
    and the reason the shape is worth keeping. Revising bullet by bullet would spend a call per
    comment, which on a free tier is the difference between a student iterating freely on six bullets
    and being rate-limited halfway through.

    Each instruction travels with its own bullet inside the single prompt, so six bullets can carry
    six different instructions without six requests.

    Validation is per bullet against **that bullet's own original**, never against the previous
    rewrite. Chaining revisions would let a claim arrive by degrees: a first pass adds nothing, a
    second adds a mild quantifier, a third sharpens it into a number, and each step passes because it
    is only compared with the step before. Comparing against the student's own sentence every time
    bounds the total drift however many revisions are asked for.

    So "say I handled 10,000 records" is refused when 10,000 is not in the student's bullet, and the
    refusal is returned rather than hidden. The student learns the number is the problem and can add
    it to their master resume if it is true.
    """
    originals = {r.bullet_id: r.original for r in requests}
    instructions = {r.bullet_id: r.instruction for r in requests}
    pairs = [(r.bullet_id, r.original) for r in requests]

    if llm is None or not requests:
        return [
            BulletOutcome(
                bullet_id=r.bullet_id, original=r.original, tailored=r.original, changed=False
            )
            for r in requests
        ]

    try:
        first = await _ask(
            llm,
            pairs,
            job_title=job_title,
            company=company,
            description=description,
            instructions=instructions,
        )
    except (LLMError, ValueError) as exc:
        logger.warning("bullet revision failed: %s", exc)
        first = {}

    accepted: dict[str, str] = {}
    rejected: dict[str, tuple[RejectionReason, str, str]] = {}

    for bullet_id, candidate in first.items():
        if bullet_id not in originals or candidate == originals[bullet_id]:
            continue
        verdict = validate_rewrite(originals[bullet_id], candidate)
        if verdict.ok:
            accepted[bullet_id] = candidate
        else:
            rejected[bullet_id] = (
                verdict.reason or RejectionReason.EMPTY,
                verdict.detail,
                candidate,
            )

    # One retry for the refused ones only, naming what was added — ADR 0006's shape.
    if rejected:
        retry_pairs = [(bullet_id, originals[bullet_id]) for bullet_id in rejected]
        try:
            second = await _ask(
                llm,
                retry_pairs,
                job_title=job_title,
                company=company,
                description=description,
                instructions={k: instructions[k] for k in rejected if k in instructions},
                rejected={k: detail for k, (_, detail, _) in rejected.items()},
            )
        except (LLMError, ValueError) as exc:
            logger.warning("bullet revision retry failed: %s", exc)
            second = {}

        for bullet_id, candidate in second.items():
            if bullet_id not in originals or candidate == originals[bullet_id]:
                continue
            verdict = validate_rewrite(originals[bullet_id], candidate)
            if verdict.ok:
                accepted[bullet_id] = candidate
                rejected.pop(bullet_id, None)
            else:
                rejected[bullet_id] = (
                    verdict.reason or RejectionReason.EMPTY,
                    verdict.detail,
                    candidate,
                )

    outcomes: list[BulletOutcome] = []
    for request in requests:
        bullet_id = request.bullet_id
        if bullet_id in accepted:
            outcomes.append(
                BulletOutcome(
                    bullet_id=bullet_id,
                    original=request.original,
                    tailored=accepted[bullet_id],
                    changed=True,
                )
            )
        elif bullet_id in rejected:
            reason, detail, text = rejected[bullet_id]
            outcomes.append(
                BulletOutcome(
                    bullet_id=bullet_id,
                    original=request.original,
                    tailored=request.original,
                    changed=False,
                    rejected_reason=reason,
                    rejected_detail=detail,
                    rejected_text=text,
                )
            )
        else:
            outcomes.append(
                BulletOutcome(
                    bullet_id=bullet_id,
                    original=request.original,
                    tailored=request.original,
                    changed=False,
                )
            )
    return outcomes
