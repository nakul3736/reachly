"""The tailoring service: generate, validate, retry once, fall back.

The behaviour that matters is what happens when the model misbehaves, because that is the case the
whole feature exists for and the case a demo never shows.
"""

from app.adapters.llm_client import LLMUnavailable
from app.domain.parsed_resume import Bullet, ExperienceEntry, ParsedResume
from app.domain.tailoring import RejectionReason
from app.services.tailoring_service import tailor_resume

JOB = {
    "job_title": "Backend Engineer",
    "company": "Northwind",
    "description": "You will build Python services and deploy them on Kubernetes.",
}


def _resume() -> ParsedResume:
    return ParsedResume(
        summary="Graduate developer",
        experience=[
            ExperienceEntry(
                id="e1",
                employer="Campus Lab",
                title="Research Assistant",
                dates="2025",
                bullets=[
                    Bullet(id="b1", text="Built a REST API in Python for the survey tool"),
                    Bullet(id="b2", text="Wrote unit tests using pytest"),
                ],
            )
        ],
        education=[],
        skills=["Python", "pytest"],
        raw_text="Built a REST API in Python for the survey tool. Wrote unit tests using pytest.",
    )


class ScriptedLLM:
    """Returns a prepared reply per call, and records the prompts it received."""

    def __init__(self, replies: list[dict[str, str]]) -> None:
        self._replies = replies
        self.prompts: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        self.prompts.append(user)
        index = min(len(self.prompts) - 1, len(self._replies) - 1)
        reply = self._replies[index]
        return {"bullets": [{"id": k, "text": v} for k, v in reply.items()]}


class BrokenLLM:
    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 4096
    ) -> dict[str, object]:
        raise LLMUnavailable("no quota")


class TestFaithfulRewrites:
    async def test_a_valid_rewrite_is_accepted(self) -> None:
        llm = ScriptedLLM(
            [{"b1": "Developed a Python REST API for the survey tool", "b2": "Authored pytest unit tests"}]
        )

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        assert result.changed_count == 2
        assert result.rejected_count == 0
        assert all(o.changed for o in result.outcomes)

    async def test_one_request_covers_the_whole_resume(self) -> None:
        llm = ScriptedLLM([{"b1": "Developed a Python REST API for the survey tool"}])

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        assert result.requests_made == 1, "per-bullet calls would be the costliest thing here"
        assert len(llm.prompts) == 1

    async def test_the_original_is_always_kept_alongside(self) -> None:
        llm = ScriptedLLM([{"b1": "Developed a Python REST API for the survey tool"}])

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        first = next(o for o in result.outcomes if o.bullet_id == "b1")
        assert first.original == "Built a REST API in Python for the survey tool"
        assert first.tailored != first.original


class TestFabricationIsCaught:
    async def test_an_invented_technology_is_rejected_and_retried(self) -> None:
        """The posting wants Kubernetes. The student has never used it."""
        llm = ScriptedLLM(
            [
                {"b1": "Built a Python REST API deployed on Kubernetes"},
                {"b1": "Developed a Python REST API for the survey tool"},
            ]
        )

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        assert result.requests_made == 2, "a rejected bullet must be retried exactly once"
        first = next(o for o in result.outcomes if o.bullet_id == "b1")
        assert first.changed, "the retry succeeded, so the improved text should be used"
        assert "Kubernetes" not in first.tailored

    async def test_the_retry_prompt_names_what_was_added(self) -> None:
        """A retry that repeats the same prompt mostly reproduces the same mistake."""
        llm = ScriptedLLM(
            [
                {"b1": "Built a Python REST API deployed on Kubernetes"},
                {"b1": "Developed a Python REST API for the survey tool"},
            ]
        )

        await tailor_resume(_resume(), **JOB, llm=llm)

        assert "Kubernetes" in llm.prompts[1]

    async def test_a_second_failure_falls_back_to_the_original(self) -> None:
        llm = ScriptedLLM(
            [
                {"b1": "Built a Python REST API deployed on Kubernetes"},
                {"b1": "Built a Python REST API on Kubernetes and AWS"},
            ]
        )

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        first = next(o for o in result.outcomes if o.bullet_id == "b1")
        assert first.tailored == first.original, "the student's own sentence is always safe"
        assert not first.changed
        assert first.rejected_reason == RejectionReason.ADDED_TECHNOLOGY
        assert "Kubernetes" in first.rejected_detail

    async def test_the_rejected_text_is_kept_for_the_interface(self) -> None:
        """Story 42: the student is shown what was caught rather than asked to trust."""
        llm = ScriptedLLM([{"b1": "Built a Python REST API deployed on Kubernetes"}])

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        first = next(o for o in result.outcomes if o.bullet_id == "b1")
        assert "Kubernetes" in first.rejected_text

    async def test_a_failure_on_one_bullet_does_not_block_the_others(self) -> None:
        llm = ScriptedLLM(
            [
                {
                    "b1": "Built a Python REST API deployed on Kubernetes",
                    "b2": "Authored pytest unit tests",
                },
                {"b1": "Built a Python REST API on Kubernetes"},
            ]
        )

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        second = next(o for o in result.outcomes if o.bullet_id == "b2")
        assert second.changed, "punishing every bullet for one model mistake helps nobody"


class TestDegradation:
    async def test_no_client_returns_the_resume_unchanged(self) -> None:
        result = await tailor_resume(_resume(), **JOB, llm=None)

        assert result.changed_count == 0
        assert all(o.tailored == o.original for o in result.outcomes)
        assert result.requests_made == 0

    async def test_an_outage_returns_the_resume_unchanged(self) -> None:
        result = await tailor_resume(_resume(), **JOB, llm=BrokenLLM())

        assert result.changed_count == 0
        assert all(o.tailored == o.original for o in result.outcomes)

    async def test_a_malformed_reply_does_not_lose_the_resume(self) -> None:
        class Malformed:
            async def complete_json(
                self, *, system: str, user: str, max_output_tokens: int = 4096
            ) -> dict[str, object]:
                return {"unexpected": "shape"}

        result = await tailor_resume(_resume(), **JOB, llm=Malformed())

        assert len(result.outcomes) == 2
        assert all(o.tailored == o.original for o in result.outcomes)

    async def test_a_reply_missing_a_bullet_leaves_that_bullet_alone(self) -> None:
        llm = ScriptedLLM([{"b1": "Developed a Python REST API for the survey tool"}])

        result = await tailor_resume(_resume(), **JOB, llm=llm)

        second = next(o for o in result.outcomes if o.bullet_id == "b2")
        assert second.tailored == second.original

    async def test_a_resume_with_no_bullets_is_not_an_error(self) -> None:
        empty = ParsedResume(summary="", experience=[], education=[], skills=[], raw_text="")

        result = await tailor_resume(empty, **JOB, llm=ScriptedLLM([{}]))

        assert result.outcomes == []
        assert result.requests_made == 0


class TestGaps:
    async def test_unmet_requirements_are_reported_as_gaps(self) -> None:
        """The honest home for everything tailoring is forbidden from inventing."""
        result = await tailor_resume(
            _resume(), **JOB, missing_skills=["Kubernetes", "AWS"], llm=None
        )

        assert result.gaps == ["AWS", "Kubernetes"]

    async def test_gaps_never_leak_into_the_bullets(self) -> None:
        llm = ScriptedLLM([{"b1": "Built a Python REST API deployed on Kubernetes"}])

        result = await tailor_resume(
            _resume(), **JOB, missing_skills=["Kubernetes"], llm=llm
        )

        for outcome in result.outcomes:
            assert "Kubernetes" not in outcome.tailored
