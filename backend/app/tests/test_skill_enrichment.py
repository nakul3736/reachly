"""Model-assisted skill enrichment, per ADR 0011.

The vocabulary is the floor and this is what sits on top of it. Two properties matter more than
anything else here, and both are about not corrupting the score:

- **Enrichment can only add.** If a model reply ever replaced the vocabulary's findings, a bad
  reply would silently lower a student's score against skills they actually have.
- **A skill not present in the description is discarded.** An invented requirement lowers the
  student's score against a demand no employer made, which is the same fabrication rule that
  governs tailoring — and here nobody would ever notice it.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm_client import LLMUnavailable
from app.models.board_token import BoardToken
from app.models.job import Job
from app.services.skill_enrichment_service import enrich_job_skills


class RecordingLLM:
    """Answers with whatever it is told to, and records what it was asked."""

    def __init__(self, replies: dict[str, list[str]] | list[dict[str, list[str]]]) -> None:
        self._replies = replies
        self.calls: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 2048
    ) -> dict[str, object]:
        self.calls.append(user)
        reply = (
            self._replies[len(self.calls) - 1]
            if isinstance(self._replies, list)
            else self._replies
        )
        return {"postings": [{"id": k, "skills": v} for k, v in reply.items()]}


class FailingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(
        self, *, system: str, user: str, max_output_tokens: int = 2048
    ) -> dict[str, object]:
        self.calls += 1
        raise LLMUnavailable("no quota")


async def _board(session: AsyncSession) -> BoardToken:
    board = BoardToken(
        provider="greenhouse", token="testco", company_name="Testco", active=True
    )
    session.add(board)
    await session.flush()
    return board


async def _job(
    session: AsyncSession,
    board: BoardToken,
    *,
    job_id: str,
    description: str,
    seniority: str = "entry",
    country: str = "US",
    role_family: str = "software_engineering",
) -> Job:
    job = Job(
        source="greenhouse",
        source_job_id=job_id,
        board_token_id=board.id,
        company_name="Testco",
        title="Software Engineer",
        location_raw="Toronto, ON",
        country=country,
        description=description,
        apply_url=f"https://example.test/{job_id}",
        seniority=seniority,
        role_family=role_family,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


class TestTheVocabularyFloor:
    async def test_vocabulary_skills_are_stored_without_any_model(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        job = await _job(
            session, board, job_id="1", description="You will write Python and use Docker."
        )

        summary = await enrich_job_skills(session, llm=None)

        assert summary.enriched == 1
        await session.refresh(job)
        assert set(job.extracted_skills or []) == {"Python", "Docker"}
        assert job.skills_basis == "vocabulary"
        assert job.skills_extracted_at is not None

    async def test_a_model_reply_is_added_to_the_vocabulary_result_not_substituted(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        job = await _job(
            session,
            board,
            job_id="1",
            description="You will write Python. Comfortable owning a service end to end.",
        )
        llm = RecordingLLM({"1": ["service ownership"]})

        await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        stored = set(job.extracted_skills or [])
        assert "Python" in stored, "the vocabulary's finding must survive enrichment"
        assert "service ownership" in stored
        assert job.skills_basis == "model"


class TestTheEvidenceRule:
    async def test_a_skill_absent_from_the_description_is_discarded(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        job = await _job(session, board, job_id="1", description="You will write Python.")
        llm = RecordingLLM({"1": ["Python", "Kubernetes", "Rust"]})

        summary = await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        stored = set(job.extracted_skills or [])
        assert stored == {"Python"}
        assert "Kubernetes" not in stored, (
            "invented requirement would lower the student's score"
        )
        assert summary.discarded == 2

    async def test_a_skill_present_under_an_alias_is_kept(self, session: AsyncSession) -> None:
        board = await _board(session)
        job = await _job(session, board, job_id="1", description="Deployed on k8s.")
        llm = RecordingLLM({"1": ["Kubernetes"]})

        await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        # The description says k8s, so Kubernetes is evidenced even though the word is absent.
        assert "Kubernetes" in set(job.extracted_skills or [])

    async def test_a_nominalised_skill_is_kept(self, session: AsyncSession) -> None:
        """The readings enrichment exists for arrive in a different grammatical form.

        "Comfortable owning a service end to end" supports `service ownership`, and a literal
        substring test would throw away exactly the findings no vocabulary can reach.
        """
        board = await _board(session)
        job = await _job(
            session,
            board,
            job_id="1",
            description="You will be comfortable owning a service end to end.",
        )
        llm = RecordingLLM({"1": ["service ownership"]})

        await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        assert "service ownership" in set(job.extracted_skills or [])

    async def test_a_multi_word_skill_with_absent_words_is_still_discarded(
        self, session: AsyncSession
    ) -> None:
        """The widened rule must not become a rule that accepts anything."""
        board = await _board(session)
        job = await _job(
            session,
            board,
            job_id="1",
            description="You will be comfortable owning a service end to end.",
        )
        llm = RecordingLLM({"1": ["distributed systems", "financial modelling"]})

        summary = await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        assert set(job.extracted_skills or []) == set()
        assert summary.discarded == 2

    async def test_a_partly_supported_skill_is_discarded(self, session: AsyncSession) -> None:
        """One word appearing is not evidence for a two-word requirement."""
        board = await _board(session)
        job = await _job(
            session, board, job_id="1", description="You will write tests for our service."
        )
        llm = RecordingLLM({"1": ["service mesh"]})

        summary = await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        assert "service mesh" not in set(job.extracted_skills or [])
        assert summary.discarded == 1


class TestBounding:
    async def test_only_one_request_is_made_for_a_batch_of_postings(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        for i in range(5):
            await _job(session, board, job_id=str(i), description="You will write Python.")
        llm = RecordingLLM({str(i): [] for i in range(5)})

        await enrich_job_skills(session, llm=llm, batch_size=5)

        assert len(llm.calls) == 1, "one call per posting is the cost ADR 0011 exists to avoid"

    async def test_the_run_is_bounded(self, session: AsyncSession) -> None:
        board = await _board(session)
        for i in range(10):
            await _job(session, board, job_id=str(i), description="You will write Python.")

        summary = await enrich_job_skills(session, llm=None, max_jobs=4)

        assert summary.enriched == 4, "one run must not be able to exhaust a day's quota"

    async def test_an_already_enriched_posting_is_not_enriched_again(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        await _job(session, board, job_id="1", description="You will write Python.")

        first = await enrich_job_skills(session, llm=None)
        second = await enrich_job_skills(session, llm=None)

        assert first.enriched == 1
        assert second.enriched == 0, "re-reading settled postings would be pure waste"


class TestWhoGetsEnriched:
    async def test_a_senior_posting_is_not_enriched(self, session: AsyncSession) -> None:
        board = await _board(session)
        await _job(session, board, job_id="1", description="Python.", seniority="senior")

        summary = await enrich_job_skills(session, llm=None)

        assert summary.enriched == 0, "a graduate will never see it, so reading it is wasted"

    async def test_a_posting_outside_north_america_is_not_enriched(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        await _job(session, board, job_id="1", description="Python.", country="IN")

        summary = await enrich_job_skills(session, llm=None)

        assert summary.enriched == 0

    async def test_an_unknown_seniority_posting_is_enriched(
        self, session: AsyncSession
    ) -> None:
        """Plain `Software Engineer` is often exactly right for a graduate."""
        board = await _board(session)
        await _job(session, board, job_id="1", description="Python.", seniority="unknown")

        summary = await enrich_job_skills(session, llm=None)

        assert summary.enriched == 1

    async def test_a_closed_posting_is_not_enriched(self, session: AsyncSession) -> None:
        board = await _board(session)
        job = await _job(session, board, job_id="1", description="Python.")
        job.closed_at = datetime.now(UTC)
        await session.flush()

        summary = await enrich_job_skills(session, llm=None)

        assert summary.enriched == 0

    async def test_a_posting_with_no_description_is_not_sent_to_the_model(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        await _job(session, board, job_id="1", description="")
        llm = RecordingLLM({})

        summary = await enrich_job_skills(session, llm=llm)

        assert llm.calls == []
        assert summary.enriched == 0


class TestFailure:
    async def test_a_model_outage_leaves_the_vocabulary_result_and_retries_later(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        job = await _job(session, board, job_id="1", description="You will write Python.")
        llm = FailingLLM()

        summary = await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        assert set(job.extracted_skills or []) == {"Python"}, "the floor still holds"
        assert job.skills_basis == "vocabulary"
        assert summary.failed_batches == 1
        assert job.skills_extracted_at is None, (
            "an outage must not be recorded as a finished reading, or it is never retried"
        )

    async def test_a_malformed_reply_does_not_lose_the_vocabulary_result(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        job = await _job(session, board, job_id="1", description="You will write Python.")

        class Malformed:
            async def complete_json(
                self, *, system: str, user: str, max_output_tokens: int = 2048
            ) -> dict[str, object]:
                return {"unexpected": "shape"}

        await enrich_job_skills(session, llm=Malformed())

        await session.refresh(job)
        assert set(job.extracted_skills or []) == {"Python"}

    async def test_a_reply_naming_an_unknown_posting_is_ignored(
        self, session: AsyncSession
    ) -> None:
        board = await _board(session)
        job = await _job(session, board, job_id="1", description="You will write Python.")
        llm = RecordingLLM({"1": ["Python"], "999": ["Kubernetes"]})

        await enrich_job_skills(session, llm=llm)

        await session.refresh(job)
        assert set(job.extracted_skills or []) == {"Python"}


class TestPromptShape:
    async def test_each_posting_in_the_prompt_is_identified(
        self, session: AsyncSession
    ) -> None:
        """The model reorders replies, so answers must be keyed rather than positional."""
        board = await _board(session)
        await _job(session, board, job_id="a1", description="Python.")
        await _job(session, board, job_id="b2", description="Docker.")
        llm = RecordingLLM({"a1": [], "b2": []})

        await enrich_job_skills(session, llm=llm)

        prompt = llm.calls[0]
        assert "a1" in prompt
        assert "b2" in prompt

    @pytest.mark.parametrize("length", [200, 20_000])
    async def test_the_description_sent_is_bounded(
        self, session: AsyncSession, length: int
    ) -> None:
        board = await _board(session)
        await _job(session, board, job_id="1", description="Python. " + ("x" * length))
        llm = RecordingLLM({"1": []})

        await enrich_job_skills(session, llm=llm)

        assert len(llm.calls[0]) < 12_000, "a 20k description would dominate the batch's budget"
