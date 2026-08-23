"""Projects, which for a graduate are often the strongest part of the document.

The parse originally read summary, experience, education and skills. A resume whose best evidence is
four built things and whose only job is retail would have the retail job tailored and the four built
things ignored — the strongest half of the document untouched, for exactly the students this product
exists for.

The rules are the same as everywhere else: nothing that is not in the source text survives, and a
project bullet is tailored under the same validator as an experience bullet.
"""

from app.adapters.real_resume_parser import _build
from app.domain.parsed_resume import ParsedResume
from app.services.tailoring_service import _bullets_of

RAW = """
Nakul Patel
nk@example.test

EXPERIENCE
Campus IT, Student Assistant, 2024
- Answered support tickets for staff laptops.

PROJECTS
Transit Delay Tracker, 2025
- Built a Python service that collects transit updates and stores them in PostgreSQL.
- Wrote a small React dashboard to show delays by route.

Chess Engine
- Implemented move generation and a simple evaluation function in C++.

EDUCATION
Dalhousie University, BSc Computer Science, 2026

SKILLS
Python, PostgreSQL, React, C++
"""


def _payload() -> dict[str, object]:
    """What a well-behaved model returns for the text above."""
    return {
        "summary": "",
        "skills": ["Python", "PostgreSQL", "React", "C++"],
        "experience": [
            {
                "employer": "Campus IT",
                "title": "Student Assistant",
                "dates": "2024",
                "bullets": ["Answered support tickets for staff laptops."],
            }
        ],
        "projects": [
            {
                "name": "Transit Delay Tracker",
                "dates": "2025",
                "bullets": [
                    "Built a Python service that collects transit updates and stores them in "
                    "PostgreSQL.",
                    "Wrote a small React dashboard to show delays by route.",
                ],
            },
            {
                "name": "Chess Engine",
                "dates": "",
                "bullets": [
                    "Implemented move generation and a simple evaluation function in C++."
                ],
            },
        ],
        "education": [
            {
                "institution": "Dalhousie University",
                "credential": "BSc Computer Science",
                "dates": "2026",
            }
        ],
    }


class TestProjectsAreRead:
    def test_projects_are_kept_separate_from_experience(self) -> None:
        """Nobody employed them to build it, and an invented employer is a company that never was."""
        parsed = _build(_payload(), RAW)

        assert [p.name for p in parsed.projects] == ["Transit Delay Tracker", "Chess Engine"]
        assert [e.employer for e in parsed.experience] == ["Campus IT"]
        for entry in parsed.experience:
            assert "Chess" not in entry.employer

    def test_project_bullets_survive_with_ids(self) -> None:
        parsed = _build(_payload(), RAW)

        tracker = parsed.projects[0]
        assert len(tracker.bullets) == 2
        assert all(bullet.id for bullet in tracker.bullets)
        assert "React dashboard" in tracker.bullets[1].text

    def test_a_project_with_no_dates_is_accepted(self) -> None:
        """Projects have no HR system, so a missing date is normal rather than an error."""
        parsed = _build(_payload(), RAW)

        assert parsed.projects[1].name == "Chess Engine"
        assert parsed.projects[1].dates == ""

    def test_an_invented_project_is_dropped_and_the_rest_survives(self) -> None:
        """The evidence rule, applied where it belongs: drop the entry, keep the resume."""
        payload = _payload()
        projects = payload["projects"]
        assert isinstance(projects, list)
        projects.append(
            {"name": "Distributed Ledger Platform", "dates": "2025", "bullets": ["Led a team."]}
        )

        parsed = _build(payload, RAW)

        names = [p.name for p in parsed.projects]
        assert "Distributed Ledger Platform" not in names
        assert "Transit Delay Tracker" in names, "one bad entry must not cost the good ones"

    def test_an_invented_project_bullet_is_dropped(self) -> None:
        payload = _payload()
        projects = payload["projects"]
        assert isinstance(projects, list)
        first = projects[0]
        assert isinstance(first, dict)
        bullets = first["bullets"]
        assert isinstance(bullets, list)
        bullets.append("Scaled the service to 40,000 daily users on Kubernetes.")

        parsed = _build(payload, RAW)

        texts = [b.text for b in parsed.projects[0].bullets]
        assert not any("40,000" in text for text in texts)
        assert not any("Kubernetes" in text for text in texts)

    def test_a_resume_that_is_only_projects_is_not_empty(self) -> None:
        """A first-year student with no jobs still has a resume worth scoring and tailoring."""
        resume = ParsedResume.model_validate(
            {
                "summary": "",
                "experience": [],
                "education": [],
                "skills": [],
                "projects": [
                    {
                        "id": "p1",
                        "name": "Chess Engine",
                        "dates": "",
                        "bullets": [{"id": "b1", "text": "Implemented move generation in C++."}],
                    }
                ],
                "raw_text": RAW,
            }
        )

        assert resume.is_empty() is False


class TestProjectsAreTailored:
    def test_project_bullets_are_offered_for_rewriting(self) -> None:
        parsed = _build(_payload(), RAW)

        ids = {bullet_id for bullet_id, _ in _bullets_of(parsed)}
        texts = {text for _, text in _bullets_of(parsed)}

        assert len(ids) == 4, "one experience bullet and three project bullets"
        assert any("React dashboard" in text for text in texts)
        assert any("move generation" in text for text in texts)

    def test_experience_still_comes_first(self) -> None:
        """Order is the resume's own; tailoring does not decide which section matters more."""
        parsed = _build(_payload(), RAW)

        pairs = _bullets_of(parsed)
        assert "support tickets" in pairs[0][1]

    def test_a_resume_with_no_projects_is_unaffected(self) -> None:
        """The change is additive: existing resumes behave exactly as before."""
        payload = _payload()
        payload["projects"] = []

        parsed = _build(payload, RAW)

        assert parsed.projects == []
        assert len(_bullets_of(parsed)) == 1

    def test_a_stored_resume_without_the_projects_key_still_loads(self) -> None:
        """Every resume parsed before this feature existed has no projects field at all."""
        resume = ParsedResume.model_validate(
            {
                "summary": "Graduate",
                "experience": [],
                "education": [],
                "skills": ["Python"],
                "raw_text": "Python",
            }
        )

        assert resume.projects == []
        assert resume.is_empty() is False
