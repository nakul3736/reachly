"""Writing the outreach email from the student's tailored resume and the posting.

The earlier version assembled a fixed template from four facts, and it was honest but audibly a form.
This one asks a model to write it, gives it the student's actual evidence and the actual posting, and
then refuses anything it cannot support — so the message reads like a person while still being
incapable of claiming a skill the resume does not have.

Why a model here when `app/domain/outreach.py` argued against one: the objection was never to
generation, it was to generation *without grounding or checking*. The template could not do the one
thing that makes a cold email work, which is to connect a specific thing the student built to a
specific thing the posting asks for. That connection is a writing task. What makes it safe is that the
output is validated against the resume afterwards, exactly as tailored bullets are, and falls back to
the assembled draft when it fails.

The prompt is built from published guidance on what makes outreach read as human rather than
generated, since this is a solved problem in sales and the failure modes are well documented:

  - Topo, "How to Not Sound Like AI in Sales Emails" (Oct 2025): brief the model as you would a new
    hire - persona, tone, goal, context - and the four red flags are the formal opener, jargon-stuffed
    phrasing, total absence of specifics, and a weak non-committal ask.
  - Topo, "The Most Common AI Words to Avoid" (Oct 2025): prefer "use" to "utilise", "improve" to
    "enhance"; vary sentence length, because a uniform rhythm is itself a tell; show a specific fact
    instead of asserting a quality.
  - Forbes, "5 ChatGPT Prompts To Write Compelling Cold Emails That Sound Human" (Jun 2026): the test
    is whether the sentence is one you would say out loud to another person.

Two pieces of that guidance are deliberately **not** followed, because it is written for salespeople
and a graduate is in a different position. It recommends humour and a strong contrarian point of view;
a first-year applicant being funny at a stranger who controls their application is a risk they did not
ask us to take on their behalf. It also recommends a confident specific ask - "does Tuesday at 3
work?" - which is the correct advice for a vendor and presumptuous from a candidate who has not yet
been screened. The ask stays modest.
"""

import json
import logging

from app.adapters.llm_client import LLMClient, LLMError
from app.domain.outreach import OutreachDraft, build_outreach_draft
from app.domain.outreach_validation import (
    MAX_WORDS,
    OutreachRejection,
    validate_outreach,
)
from app.domain.parsed_resume import ParsedResume

logger = logging.getLogger(__name__)

# The brief. Written as instruction rather than persona-play: "act as an expert copywriter" measurably
# buys nothing over saying plainly what the sentences must do, and it invites the model to perform a
# character, which is where flourishes come from.
_SYSTEM = f"""You write one short email for a new graduate applying to a job.

The graduate sends it themselves from their own address. Write in first person as them.

HARD RULES - a draft breaking any of these is discarded by an automatic check:
- Use ONLY facts from the RESUME section. The POSTING section is context for what the employer wants;
  it is NOT a list of things the graduate can claim. If the posting wants Kubernetes and the resume
  never mentions it, the email must not mention it either.
- Invent no numbers, no employers, no products, no institutions, no dates.
- Never describe a history with this company: no admiring their work, following them, using their
  product, reading a post, or having met anyone.
- No feelings presented as facts. Not "passionate", not "excited", not "dream role", not "perfect fit".
- Under {MAX_WORDS} words for the body.

WRITE LIKE A PERSON, NOT A TEMPLATE:
- Open with something concrete. Never "I hope this email finds you well" or "I am writing to express
  my interest" - both are instantly recognised as machine-written and the reader stops there.
- One specific connection is the whole email: something the graduate actually built or did, next to
  something this posting actually asks for. Name the project or the work. Specifics are the only thing
  that proves a human wrote this.
- Plain words. "use" not "utilise", "improve" not "enhance", "help" not "facilitate". No jargon, no
  buzzwords, no "leverage".
- Vary sentence length. A uniform rhythm reads as generated.
- Contractions are fine. Read it as if saying it out loud to someone: if you would not say the
  sentence, do not write it.
- Modest, specific ask: a short conversation, or to be considered. Do not propose a time - they have
  not been screened yet and it reads as presumptuous.
- No sign-off block, no "Best regards" - the sender's name is appended afterwards.

Return JSON only: {{"subject": "...", "body": "..."}}
The subject is under 60 characters, states the role, and is not a slogan.
The body starts with the greeting and ends with the last sentence. Use \\n\\n between paragraphs.
"""


def _resume_evidence(resume: ParsedResume) -> str:
    """The resume as the writer sees it, with the tailored text where the student approved one.

    Bullets carry no ids here. This is a writing brief rather than a tailoring pass, and ids invite the
    model to echo them into prose.
    """
    parts: list[str] = []
    if resume.summary:
        parts.append(f"Summary: {resume.summary}")
    if resume.skills:
        parts.append(f"Skills: {', '.join(resume.skills)}")

    for role in resume.experience:
        header = f"{role.title} at {role.employer} ({role.dates})".strip()
        parts.append(header)
        parts.extend(f"  - {bullet.text}" for bullet in role.bullets)

    for project in resume.projects:
        parts.append(f"Project: {project.name} ({project.dates})".strip())
        parts.extend(f"  - {bullet.text}" for bullet in project.bullets)

    for entry in resume.education:
        parts.append(f"{entry.credential}, {entry.institution} ({entry.dates})".strip())

    return "\n".join(parts)


def _prompt(
    *,
    student_name: str,
    job_title: str,
    company: str,
    description: str,
    evidence: str,
    matched_skills: list[str],
    other_open_roles: int,
    applied: bool,
) -> str:
    lines = [
        f"GRADUATE: {student_name}",
        f"ROLE: {job_title}",
        f"COMPANY: {company}",
        "",
        "RESUME (the only source of facts about the graduate):",
        evidence,
        "",
        "POSTING (what the employer wants - context only, not claimable):",
        description[:4000],
    ]

    if matched_skills:
        # Named separately because these are the overlap feature 03 already computed and can defend.
        # The strongest sentence in the email is usually built from one of them.
        lines += [
            "",
            "SKILLS THE POSTING ASKS FOR THAT THIS RESUME ALREADY EVIDENCES:",
            ", ".join(matched_skills),
        ]

    if 1 <= other_open_roles <= 12:
        lines += [
            "",
            f"FACT Reachly verified: {company} currently has {other_open_roles} other roles posted.",
            "You may mention this once if it fits naturally, as a reason to be redirected.",
        ]

    lines += [
        "",
        (
            "The graduate has already applied through the official form."
            if applied
            else "The graduate is applying through the official form."
        ),
        "Write the email.",
    ]
    return "\n".join(lines)


async def write_outreach(
    *,
    student_name: str,
    job_title: str,
    company: str,
    description: str,
    resume: ParsedResume | None,
    matched_skills: list[str],
    other_open_roles: int = 0,
    applied: bool = False,
    llm: LLMClient | None = None,
) -> OutreachDraft:
    """Write the email, check it, and fall back to the assembled draft rather than ship a bad one.

    The fallback is the point of keeping `build_outreach_draft`. A refused generation must not leave the
    student with nothing, and it must not leave them with something unchecked; the template is neither.
    Its evidence lines say plainly that it is the assembled version, so the interface never claims a
    written email when it is showing a form.
    """
    assembled = build_outreach_draft(
        student_name=student_name,
        job_title=job_title,
        company=company,
        matched_skills=matched_skills,
        other_open_roles=other_open_roles,
        applied=applied,
    )

    if llm is None or resume is None:
        return assembled

    evidence = _resume_evidence(resume)
    if not evidence.strip():
        return assembled

    prompt = _prompt(
        student_name=student_name,
        job_title=job_title,
        company=company,
        description=description,
        evidence=evidence,
        matched_skills=matched_skills,
        other_open_roles=other_open_roles,
        applied=applied,
    )

    # The corpus the message is checked against: the resume, and the count Reachly derived. The posting
    # is absent on purpose - see validate_outreach.
    corpus = f"{evidence}\n{other_open_roles}"

    return await _generate(
        prompt=prompt,
        corpus=corpus,
        company=company,
        job_title=job_title,
        student_name=student_name,
        matched_skills=matched_skills,
        other_open_roles=other_open_roles,
        fallback=assembled,
        llm=llm,
    )


async def revise_outreach(
    *,
    instruction: str,
    previous_subject: str,
    previous_body: str,
    student_name: str,
    job_title: str,
    company: str,
    description: str,
    resume: ParsedResume | None,
    matched_skills: list[str],
    other_open_roles: int = 0,
    applied: bool = False,
    llm: LLMClient | None = None,
) -> OutreachDraft:
    """Rewrite the email the way the student asked, and check it exactly as before.

    The instruction is the student's ("shorter", "lead with the transit project", "less about the
    dashboard"), and it changes only what the writer is aiming for. It cannot widen what the writer is
    allowed to claim: validation still runs against the resume with the posting excluded, so "say I know
    Kubernetes" is refused for the same reason the first draft would have been, and the refusal is
    returned rather than hidden — the student learns the resume is the problem, which is actionable, and
    can add it if it is true.

    The previous draft is shown to the writer, because "make it shorter" is meaningless without it. The
    validation target is still the resume, never the previous draft: comparing each revision against the
    last one would let a claim arrive by degrees, which is the drift the tailoring loop is built to
    prevent (`revise_bullets`). Every revision is judged against the evidence, however many are asked
    for.
    """
    fallback = build_outreach_draft(
        student_name=student_name,
        job_title=job_title,
        company=company,
        matched_skills=matched_skills,
        other_open_roles=other_open_roles,
        applied=applied,
    )

    if llm is None or resume is None or not instruction.strip():
        return fallback

    evidence = _resume_evidence(resume)
    if not evidence.strip():
        return fallback

    base = _prompt(
        student_name=student_name,
        job_title=job_title,
        company=company,
        description=description,
        evidence=evidence,
        matched_skills=matched_skills,
        other_open_roles=other_open_roles,
        applied=applied,
    )
    prompt = (
        f"{base}\n\n"
        f"YOUR PREVIOUS DRAFT:\nSubject: {previous_subject}\n\n{previous_body}\n\n"
        f"WHAT THE GRADUATE WANTS CHANGED: {instruction.strip()}\n\n"
        "Rewrite it accordingly. Their instruction changes what you aim for, not what you are allowed "
        "to claim — every hard rule above still applies, and if the instruction asks for something the "
        "resume does not support, write the closest version that is true instead of inventing it."
    )

    corpus = f"{evidence}\n{other_open_roles}"
    return await _generate(
        prompt=prompt,
        corpus=corpus,
        company=company,
        job_title=job_title,
        student_name=student_name,
        matched_skills=matched_skills,
        other_open_roles=other_open_roles,
        fallback=fallback,
        llm=llm,
    )


async def _generate(
    *,
    prompt: str,
    corpus: str,
    company: str,
    job_title: str,
    student_name: str,
    matched_skills: list[str],
    other_open_roles: int,
    fallback: OutreachDraft,
    llm: LLMClient,
) -> OutreachDraft:
    """One attempt, one retry naming what was caught, then the fallback.

    Shared by the first draft and every revision so the two cannot drift apart in what they permit —
    which is the failure that matters, since a revision path with weaker checks is exactly how a
    fabrication would reach a student: ask once nicely, then ask again.
    """
    rejection: tuple[OutreachRejection, str] | None = None

    for attempt in (1, 2):
        instruction = prompt
        if rejection is not None:
            reason, detail = rejection
            # Naming the offending phrase is what makes the second request worth spending: a bare "try
            # again" reproduces the same sentence.
            instruction = (
                f"{prompt}\n\nYour previous draft was rejected: {reason.value} ({detail}). "
                "Remove it entirely and rewrite. Do not substitute a synonym."
            )

        try:
            reply = await llm.complete_json(system=_SYSTEM, user=instruction)
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            logger.warning("outreach generation failed on attempt %s: %s", attempt, exc)
            return fallback

        payload = reply if isinstance(reply, dict) else {}
        subject = str(payload.get("subject") or "").strip()
        body = str(payload.get("body") or "").strip()

        verdict = validate_outreach(body, corpus=corpus, company=company, job_title=job_title)
        if verdict.ok and subject:
            named = _named_skills(body, matched_skills)
            return OutreachDraft(
                subject=subject,
                body=f"{body}\n\n{student_name.strip()}" if student_name.strip() else body,
                evidence=_evidence_for(
                    job_title=job_title,
                    company=company,
                    named_skills=named,
                    other_open_roles=other_open_roles,
                ),
                written=True,
            )

        rejection = (verdict.reason or OutreachRejection.EMPTY, verdict.detail)
        logger.info("outreach draft rejected: %s (%s)", rejection[0], rejection[1])

    return fallback


def _named_skills(body: str, matched_skills: list[str]) -> list[str]:
    lowered = body.casefold()
    return [skill for skill in matched_skills if skill.casefold() in lowered]


def _evidence_for(
    *, job_title: str, company: str, named_skills: list[str], other_open_roles: int
) -> list[str]:
    """What the student is told about a written draft.

    Necessarily different from the assembled draft's evidence, which could name a sentence per fact
    because it built each one. Here the honest statement is what the writer was allowed to use and what
    was checked afterwards - the guarantee is the check, not the prompt.
    """
    lines = [
        f"Written from your resume and this posting: {job_title} at {company}.",
        (
            "Checked afterwards against your resume. Any technology, number, employer or institution "
            "not already in your resume is rejected and the draft rewritten — the job description is "
            "deliberately excluded from what counts as evidence, so a skill the posting wants and your "
            "resume lacks cannot appear here."
        ),
        (
            "Phrases that mark an email as machine-written are refused too, along with any claim to "
            "have followed, admired or used this company."
        ),
    ]
    if named_skills:
        lines.insert(
            1,
            f"It names {', '.join(named_skills)}, which your match score already credits you with.",
        )
    if 1 <= other_open_roles <= 12:
        lines.append(
            f"Reachly ingests whole job boards, so it can count that {company} currently has "
            f"{other_open_roles} other roles posted."
        )
    return lines


def draft_as_json(draft: OutreachDraft) -> str:
    """For storage. Kept here so the shape has one owner."""
    return json.dumps(
        {
            "subject": draft.subject,
            "body": draft.body,
            "evidence": draft.evidence,
            "written": draft.written,
        }
    )
