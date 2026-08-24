"""The written email, and the check that stands between a model and a student's reputation.

The tests that matter here are the ones that feed the writer a plausible fabrication and assert the
student never sees it. A fake client is used rather than a live model on purpose: to prove the guarantee
you have to control the output, and a live model that happens to behave proves only that it happened to
behave this time.

The single most important case is `test_a_skill_from_the_posting_the_resume_lacks_is_refused`. That is
not a hypothetical failure — it is the one a model is actively pulled towards, because it can see that
claiming Kubernetes would make the email fit the posting better.
"""

import pytest

from app.adapters.llm_client import LLMClient, LLMError
from app.domain.outreach_validation import (
    MAX_WORDS,
    OutreachRejection,
    validate_outreach,
)
from app.domain.parsed_resume import (
    Bullet,
    EducationEntry,
    ExperienceEntry,
    ParsedResume,
    ProjectEntry,
)
from app.services.outreach_service import revise_outreach, write_outreach

RESUME = ParsedResume(
    summary="Computer science graduate.",
    skills=["Python", "PostgreSQL", "React"],
    experience=[
        ExperienceEntry(
            id="e1",
            employer="Dalhousie University",
            title="Research Assistant",
            dates="2025",
            bullets=[
                Bullet(id="b1", text="Built a Python pipeline that cleaned survey responses."),
            ],
        )
    ],
    projects=[
        ProjectEntry(
            id="p1",
            name="Transit Delay Tracker",
            dates="2025",
            bullets=[
                Bullet(id="pb1", text="Wrote a React dashboard over a PostgreSQL store."),
            ],
        )
    ],
    education=[
        EducationEntry(
            id="ed1", institution="Dalhousie University", credential="BSc", dates="2026"
        )
    ],
    raw_text="Python PostgreSQL React Dalhousie Transit Delay Tracker",
)

CORPUS = (
    "Built a Python pipeline that cleaned survey responses. "
    "Wrote a React dashboard over a PostgreSQL store. "
    "Project: Transit Delay Tracker (2025) "
    "Research Assistant at Dalhousie University "
    "Dalhousie University BSc"
)

POSTING = "We need Python, PostgreSQL and Kubernetes experience for our payments team."

GOOD_BODY = (
    "Hi there,\n\n"
    "I am applying for the Backend Engineer role at Acme. The posting asks for Python and "
    "PostgreSQL, and both are what I have actually been building with. For Transit Delay Tracker I "
    "wrote a React dashboard over a PostgreSQL store, and at Dalhousie University I built a Python "
    "pipeline that cleaned survey responses.\n\n"
    "If there is a short conversation to be had about the team, I would appreciate it. Either way, "
    "thank you for reading this."
)


class FakeLLM(LLMClient):
    """Returns whatever it is told to, so the check can be tested against the output that matters."""

    def __init__(self, replies: list[dict[str, object]]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        self.calls.append(user)
        if not self.replies:
            raise LLMError("no more replies")
        return self.replies.pop(0)


class TestTheCheckOnAWrittenEmail:
    def test_a_faithful_message_passes(self) -> None:
        verdict = validate_outreach(
            GOOD_BODY, corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert verdict.ok, verdict.detail

    def test_a_technology_absent_from_the_resume_is_caught(self) -> None:
        body = GOOD_BODY.replace("Python and PostgreSQL", "Python, PostgreSQL and Kubernetes")

        verdict = validate_outreach(
            body, corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.ADDED_TECHNOLOGY
        assert "kubernetes" in verdict.detail.casefold()

    def test_an_invented_number_is_caught(self) -> None:
        body = GOOD_BODY.replace("cleaned survey responses", "cleaned 40,000 survey responses")

        verdict = validate_outreach(
            body, corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.ADDED_NUMBER

    def test_an_invented_employer_is_caught(self) -> None:
        body = GOOD_BODY.replace("at Dalhousie University", "at Shopify")

        verdict = validate_outreach(
            body, corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.ADDED_PROPER_NOUN

    @pytest.mark.parametrize(
        "phrase",
        [
            "I hope this email finds you well.",
            "I am writing to express my interest in this role.",
            "I am passionate about building software.",
            "I would be the ideal candidate for this position.",
            "I bring a wealth of experience and a proven track record.",
            "I want to leverage my skills at your company.",
        ],
    )
    def test_phrases_that_mark_an_email_as_generated_are_refused(self, phrase: str) -> None:
        verdict = validate_outreach(
            GOOD_BODY.replace("Hi there,", f"Hi there,\n\n{phrase}"),
            corpus=CORPUS,
            company="Acme",
            job_title="Backend Engineer",
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.GENERATED_PHRASE

    @pytest.mark.parametrize(
        "phrase",
        [
            "I have long admired your work in payments.",
            "I have been following Acme for years.",
            "I saw your post about the new platform.",
            "As we discussed, I am keen to move forward.",
            "I have been using your product since launch.",
        ],
    )
    def test_a_claimed_history_with_the_company_is_refused(self, phrase: str) -> None:
        """Checkable, and false. The reader knows whether they have met the sender."""
        verdict = validate_outreach(
            GOOD_BODY.replace("Hi there,", f"Hi there,\n\n{phrase}"),
            corpus=CORPUS,
            company="Acme",
            job_title="Backend Engineer",
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.UNVERIFIABLE_CLAIM

    def test_an_essay_is_refused(self) -> None:
        body = GOOD_BODY + (" I also did other things at university." * 60)

        verdict = validate_outreach(
            body, corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.TOO_LONG
        assert int(verdict.detail) > MAX_WORDS

    def test_a_fragment_is_refused(self) -> None:
        verdict = validate_outreach(
            "Hi, I am applying for the Backend Engineer role at Acme. Thanks.",
            corpus=CORPUS,
            company="Acme",
            job_title="Backend Engineer",
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.TOO_SHORT

    def test_a_message_that_names_neither_role_nor_company_is_refused(self) -> None:
        body = (
            "Hi there,\n\nI wanted to introduce myself. I built a Python pipeline that cleaned "
            "survey responses, and I wrote a React dashboard over a PostgreSQL store. If there is "
            "a short conversation to be had, I would appreciate it. Thank you for reading this "
            "message today.\n\nA Student"
        )

        verdict = validate_outreach(
            body, corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.MISSING_SUBSTANCE

    def test_an_empty_body_is_refused(self) -> None:
        verdict = validate_outreach(
            "   ", corpus=CORPUS, company="Acme", job_title="Backend Engineer"
        )

        assert not verdict.ok
        assert verdict.reason == OutreachRejection.EMPTY


class TestWritingTheEmail:
    async def test_a_good_draft_is_returned_and_signed(self) -> None:
        llm = FakeLLM([{"subject": "Backend Engineer application", "body": GOOD_BODY}])

        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python", "PostgreSQL"],
            llm=llm,
        )

        assert draft.written is True
        assert draft.body.strip().endswith("Nakul Patel")
        assert len(llm.calls) == 1

    async def test_the_resume_is_given_to_the_writer_and_the_posting_is_marked_as_context(
        self,
    ) -> None:
        llm = FakeLLM([{"subject": "Backend Engineer application", "body": GOOD_BODY}])

        await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=llm,
        )

        prompt = llm.calls[0]
        assert "Built a Python pipeline that cleaned survey responses." in prompt
        assert "Transit Delay Tracker" in prompt, "projects are evidence too"
        assert "Kubernetes" in prompt, "the posting is included"
        assert "not claimable" in prompt, "and marked as context rather than as claims"

    async def test_a_skill_from_the_posting_the_resume_lacks_is_refused(self) -> None:
        """The fabrication the model is actively pulled towards, because it improves the fit."""
        bad = GOOD_BODY.replace("Python and PostgreSQL", "Python, PostgreSQL and Kubernetes")
        llm = FakeLLM(
            [
                {"subject": "Backend Engineer application", "body": bad},
                {"subject": "Backend Engineer application", "body": GOOD_BODY},
            ]
        )

        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python", "PostgreSQL"],
            llm=llm,
        )

        assert "Kubernetes" not in draft.body
        assert draft.written is True, (
            "the second attempt was clean, so the student gets writing"
        )
        assert len(llm.calls) == 2
        assert "added_technology" in llm.calls[1], "the retry names what was caught"
        assert "kubernetes" in llm.calls[1].casefold()

    async def test_two_bad_drafts_fall_back_to_the_assembled_message(self) -> None:
        bad = GOOD_BODY.replace("Python and PostgreSQL", "Python, PostgreSQL and Kubernetes")
        llm = FakeLLM(
            [
                {"subject": "s", "body": bad},
                {"subject": "s", "body": bad},
            ]
        )

        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python", "PostgreSQL"],
            llm=llm,
        )

        assert draft.written is False, "and the interface will say so rather than claim writing"
        assert "Kubernetes" not in draft.body
        assert draft.body, "a refusal still leaves the student something to send"
        assert "Backend Engineer" in draft.body

    async def test_an_outage_falls_back_without_a_retry(self) -> None:
        llm = FakeLLM([])

        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=llm,
        )

        assert draft.written is False
        assert len(llm.calls) == 1, "a transport failure is not retried; a refusal is"

    async def test_without_a_model_the_assembled_draft_is_returned(self) -> None:
        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=None,
        )

        assert draft.written is False
        assert "Backend Engineer" in draft.body

    async def test_without_a_resume_nothing_is_generated(self) -> None:
        """There is nothing to ground a message in, so no call is spent trying."""
        llm = FakeLLM([{"subject": "s", "body": GOOD_BODY}])

        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=None,
            matched_skills=[],
            llm=llm,
        )

        assert draft.written is False
        assert llm.calls == []

class TestRevisingTheEmail:
    """The asymmetry being closed: a bullet could be argued with, the email could only be rerolled."""

    async def test_the_instruction_and_the_previous_draft_both_reach_the_writer(self) -> None:
        llm = FakeLLM([{"subject": "Backend Engineer application", "body": GOOD_BODY}])

        await revise_outreach(
            instruction="Lead with the transit project and cut the last paragraph.",
            previous_subject="Old subject",
            previous_body="Old body about nothing in particular.",
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=llm,
        )

        prompt = llm.calls[0]
        assert "Lead with the transit project" in prompt
        assert "Old body about nothing in particular." in prompt, "shorter means nothing without it"
        assert "not claimable" in prompt, "the hard rules travel with the revision"

    async def test_an_instruction_cannot_widen_what_may_be_claimed(self) -> None:
        """"Say I know Kubernetes" is refused for the same reason a first draft would be."""
        bad = GOOD_BODY.replace("Python and PostgreSQL", "Python, PostgreSQL and Kubernetes")
        llm = FakeLLM([{"subject": "s", "body": bad}, {"subject": "s", "body": bad}])

        draft = await revise_outreach(
            instruction="Say I know Kubernetes, they clearly want it.",
            previous_subject="Backend Engineer application",
            previous_body=GOOD_BODY,
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python", "PostgreSQL"],
            llm=llm,
        )

        assert "Kubernetes" not in draft.body
        assert draft.written is False, "two refusals, so the plain version is what they get"

    async def test_a_valid_revision_is_returned_and_signed(self) -> None:
        revised = GOOD_BODY.replace("Hi there,", "Hi,")
        llm = FakeLLM([{"subject": "Backend Engineer — Transit Delay Tracker", "body": revised}])

        draft = await revise_outreach(
            instruction="Make the subject mention my project.",
            previous_subject="Backend Engineer application",
            previous_body=GOOD_BODY,
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python", "PostgreSQL"],
            llm=llm,
        )

        assert draft.written is True
        assert draft.subject == "Backend Engineer — Transit Delay Tracker"
        assert draft.body.strip().endswith("Nakul Patel")

    async def test_revisions_are_judged_against_the_resume_not_the_previous_draft(self) -> None:
        """Otherwise a claim could arrive by degrees across several polite revisions."""
        llm = FakeLLM(
            [
                {
                    "subject": "s",
                    "body": GOOD_BODY.replace(
                        "cleaned survey responses", "cleaned 12,000 survey responses"
                    ),
                },
                {"subject": "s", "body": GOOD_BODY},
            ]
        )

        draft = await revise_outreach(
            instruction="Add a number to make it concrete.",
            previous_subject="s",
            # A previous draft that already contained the number would license it if the check ran
            # against the draft. It runs against the resume, so it does not.
            previous_body=GOOD_BODY.replace(
                "cleaned survey responses", "cleaned 12,000 survey responses"
            ),
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=llm,
        )

        assert "12,000" not in draft.body
        assert "added_number" in llm.calls[1], "and the student is told the number is the problem"

    async def test_an_empty_instruction_does_not_spend_a_call(self) -> None:
        llm = FakeLLM([{"subject": "s", "body": GOOD_BODY}])

        draft = await revise_outreach(
            instruction="   ",
            previous_subject="s",
            previous_body=GOOD_BODY,
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=llm,
        )

        assert llm.calls == []
        assert draft.written is False

    async def test_the_first_draft_and_a_revision_permit_exactly_the_same_things(self) -> None:
        """Shared generator, asserted — a revision path with weaker checks is how a fabrication lands."""
        bad = GOOD_BODY.replace("at Dalhousie University", "at Shopify")

        first = FakeLLM([{"subject": "s", "body": bad}, {"subject": "s", "body": bad}])
        second = FakeLLM([{"subject": "s", "body": bad}, {"subject": "s", "body": bad}])

        written = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=first,
        )
        revised = await revise_outreach(
            instruction="Mention where I worked.",
            previous_subject="s",
            previous_body=GOOD_BODY,
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python"],
            llm=second,
        )

        assert written.written is revised.written is False
        assert "Shopify" not in written.body
        assert "Shopify" not in revised.body
        assert len(first.calls) == len(second.calls) == 2, "same attempt budget"

    async def test_the_evidence_describes_the_check_not_the_prompt(self) -> None:
        llm = FakeLLM([{"subject": "Backend Engineer application", "body": GOOD_BODY}])

        draft = await write_outreach(
            student_name="Nakul Patel",
            job_title="Backend Engineer",
            company="Acme",
            description=POSTING,
            resume=RESUME,
            matched_skills=["Python", "PostgreSQL"],
            llm=llm,
        )

        joined = " ".join(draft.evidence)
        assert "Checked afterwards" in joined
        assert "job description is deliberately excluded" in joined
        assert "Python" in joined, "the skills it named are attributed to the score"
