"""The outreach draft: a message the student sends, assembled from things Reachly can prove.

ADR 0004 fixes the shape. Reachly does not send email — it produces a finished draft and hands it
over, so the student is the sender, from their own address, having read what goes out under their
name. That decision was made on legal and practical grounds and it is not revisited here.

What this module adds is the part that decides *what the message says*, and the governing rule is the
same one that governs tailoring: **every specific claim in the draft must be something Reachly can
point at.** A cold email is the place where a tool is most tempted to invent enthusiasm, and a
graduate who sends "I have long admired your work in distributed systems" to a company they learned
about ninety seconds ago is worse off than one who sends four plain sentences that are true.

So there is no model call here at all. Not to save quota — because generation is the wrong tool. The
draft's content is four facts the database already holds:

  - the student's name, and the role they are writing about
  - which of the posting's required skills their resume actually evidences, from feature 03's score
  - how many other roles that company currently has open, which is the personalisation hook ADR 0001
    identified after LinkedIn scraping was ruled out: it is specific, verifiable, genuinely useful,
    and costs one SQL count
  - the fact that they have applied, or are about to

Assembling those deterministically means the draft is reproducible, testable, instant, free, and
incapable of flattering anybody with something that is not true. A student who wants warmth can add
it themselves — and it will be their warmth.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OutreachDraft:
    subject: str
    body: str

    # What each specific claim in the body rests on, so the interface can show the student why the
    # message says what it says — the same argument the score report makes for the score.
    evidence: list[str] = field(default_factory=list)


# How many skills to name. Three because a list of eight reads as a keyword dump and invites the
# reader to check every one; three of the strongest reads as a person who understands the job.
_MAX_SKILLS = 3

# Below this, naming the count is not a useful observation about the company.
_MIN_OTHER_ROLES = 1

# And above this it stops being one again. Measured against the real index: the draft for an Airbnb
# posting read "I also noticed Airbnb has 209 other roles open at the moment", which is true, useless,
# and reads like scraped data rather than something the sender noticed. At four openings the remark is
# a genuine observation about a company's trajectory and an honest invitation to be redirected; at two
# hundred it tells a recruiter something they know better than anybody and makes the sender look
# automated. Twelve is where a person could plausibly have looked at the careers page and counted.
_MAX_OTHER_ROLES = 12


def _sentence_list(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c` — Oxford-free, which is the British form the rest of this uses."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def build_outreach_draft(
    *,
    student_name: str,
    job_title: str,
    company: str,
    matched_skills: list[str],
    other_open_roles: int = 0,
    applied: bool = False,
) -> OutreachDraft:
    """Assemble a short, specific, entirely true message.

    Deliberately plain. It opens by saying which role and that an application exists, gives one
    concrete reason the student is a plausible fit, offers the observation about the company's
    hiring, and stops. No adjectives about the company, no claimed admiration, no request beyond a
    conversation — the things a recruiter reads fifty times a day and discounts.

    Absent inputs remove sentences rather than producing vaguer ones. A student with no matched
    skills gets a shorter message, not a message claiming enthusiasm in place of evidence.
    """
    name = student_name.strip() or "A candidate"
    skills = [skill for skill in matched_skills if skill.strip()][:_MAX_SKILLS]

    subject = f"{job_title} — application from {name}" if name else f"{job_title} — application"

    lines: list[str] = ["Hello,", ""]
    evidence: list[str] = []

    opening = (
        f"I applied for the {job_title} role at {company}"
        if applied
        else f"I am applying for the {job_title} role at {company}"
    )
    lines.append(f"{opening}, and wanted to introduce myself briefly.")
    evidence.append(
        f"The role and company come from the posting you opened: {job_title}, {company}."
    )

    if skills:
        lines.append("")
        lines.append(
            f"The posting asks for {_sentence_list(skills)}, which is what I have been working "
            "with — it is on my resume rather than something I am claiming for this application."
        )
        evidence.append(
            "These are the skills the posting asks for that your resume already evidences, taken "
            "from your match score. Nothing you do not have is named."
        )

    if _MIN_OTHER_ROLES <= other_open_roles <= _MAX_OTHER_ROLES:
        plural = "roles" if other_open_roles > 1 else "role"
        lines.append("")
        lines.append(
            f"I also noticed {company} has {other_open_roles} other {plural} open at the moment. "
            "If a different one is a closer fit for my background, I would rather be pointed there "
            "than not considered."
        )
        evidence.append(
            f"Reachly ingests whole job boards, so it can count that {company} currently has "
            f"{other_open_roles} other {plural} posted. This is the one personalisation hook "
            "available without scraping anybody's profile (ADR 0001)."
        )

    lines.append("")
    lines.append(
        "If you have a few minutes, I would appreciate the chance to ask about the team. Either "
        "way, thank you for reading."
    )
    lines.append("")
    lines.append(name)

    return OutreachDraft(subject=subject, body="\n".join(lines), evidence=evidence)
