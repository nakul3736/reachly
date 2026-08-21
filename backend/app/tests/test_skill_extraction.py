"""Skill extraction from free text.

Skill overlap is 40 of the 100 points, so an extractor that looks plausible while under-reading
makes every score quietly wrong. That failure has already happened once in this project: a model
returned 7 "skills" for a resume listing 46, each one a whole category line, and nothing broke
until the count was checked by hand. These tests are the hand-check made permanent.
"""

import time

from app.domain.skill_extraction import canonical_skill, extract_skills
from app.domain.skills_vocabulary import VOCABULARY


class TestWholeTermMatching:
    """Substring matching is the failure that would make every score nonsense."""

    def test_r_is_not_found_inside_react(self) -> None:
        found = extract_skills("We use React and Redux on the front end.")
        assert "R" not in found
        assert "React" in found

    def test_go_is_not_found_inside_django_or_mongo(self) -> None:
        found = extract_skills("Our stack is Django with MongoDB.")
        assert "Go" not in found

    def test_go_is_found_when_actually_named(self) -> None:
        assert "Go" in extract_skills("Services are written in Go.")
        assert "Go" in extract_skills("Experience with Golang preferred.")

    def test_c_is_not_found_inside_ordinary_words(self) -> None:
        found = extract_skills("Candidates can collaborate across a curious culture.")
        assert "C" not in found

    def test_the_ordinary_word_it_never_produces_the_field(self) -> None:
        # "it" appears in almost every description ever written.
        found = extract_skills("If it works, ship it. It is that simple.")
        assert "IT" not in found

    def test_java_is_not_found_inside_javascript(self) -> None:
        found = extract_skills("Strong JavaScript skills required.")
        assert "JavaScript" in found
        assert "Java" not in found


class TestPunctuatedSkills:
    """Where a naive \\b regex fails: \\b does not exist between + and end of string."""

    def test_c_plus_plus(self) -> None:
        assert "C++" in extract_skills("Systems programming in C++ required.")

    def test_c_sharp(self) -> None:
        assert "C#" in extract_skills("Backend services in C# and .NET.")

    def test_dot_net(self) -> None:
        assert ".NET" in extract_skills("Backend services in C# and .NET.")

    def test_node_js(self) -> None:
        assert "Node.js" in extract_skills("APIs built with Node.js and Express.")

    def test_ci_cd(self) -> None:
        assert "CI/CD" in extract_skills("You will own our CI/CD pipelines.")

    def test_c_plus_plus_does_not_also_yield_bare_c(self) -> None:
        found = extract_skills("Systems programming in C++ required.")
        assert "C" not in found

    def test_c_sharp_does_not_also_yield_bare_c(self) -> None:
        found = extract_skills("We write C# here.")
        assert "C" not in found

    def test_bare_c_is_found_when_it_is_the_language(self) -> None:
        assert "C" in extract_skills("Embedded work in C and assembly.")


class TestSingleLetterSkills:
    """Real postings contain standalone capital letters that are not languages.

    Case-sensitivity is not enough here: a list marker, a section label, a grade and a vitamin
    are all capital C, and one such posting was a SpaceX listing with no C anywhere in it.
    """

    def test_a_lone_c_with_no_technical_company_is_rejected(self) -> None:
        found = extract_skills(
            "SpaceX was founded under the belief that a future is worth building. "
            "Please refer to Section C of the handbook."
        )
        assert "C" not in found

    def test_c_in_a_list_of_languages_is_accepted(self) -> None:
        assert "C" in extract_skills("You should know Python, C, and SQL.")

    def test_r_in_a_list_of_languages_is_accepted(self) -> None:
        assert "R" in extract_skills("Statistical work in R, Python and SQL.")

    def test_a_lone_r_in_prose_is_rejected(self) -> None:
        found = extract_skills("The R&D team meets weekly. Option R was selected.")
        assert "R" not in found

    def test_a_distant_skill_does_not_vouch_for_a_lone_letter(self) -> None:
        """Proximity is the evidence, not co-occurrence anywhere in a 6,000-character page."""
        text = (
            "We use Python here. " + ("Filler sentence about our culture. " * 12) + "Exhibit C."
        )
        assert "C" not in extract_skills(text)


class TestAliases:
    """A resume and a posting using different surface forms must still match."""

    def test_js_and_javascript_collapse(self) -> None:
        assert extract_skills("Strong JS fundamentals.") == extract_skills(
            "Strong JavaScript fundamentals."
        )

    def test_postgres_variants_collapse(self) -> None:
        for surface in ("Postgres", "PostgreSQL", "postgresql"):
            assert "PostgreSQL" in extract_skills(f"Data lives in {surface}.")

    def test_k8s_is_kubernetes(self) -> None:
        assert "Kubernetes" in extract_skills("Deployed on k8s.")

    def test_canonical_skill_maps_an_alias(self) -> None:
        assert canonical_skill("js") == "JavaScript"
        assert canonical_skill("JAVASCRIPT") == "JavaScript"

    def test_canonical_skill_returns_none_for_an_unknown_term(self) -> None:
        assert canonical_skill("underwater basket weaving") is None


class TestMultiWordSkills:
    def test_machine_learning(self) -> None:
        assert "Machine learning" in extract_skills("Applied machine learning experience.")

    def test_infrastructure_as_code(self) -> None:
        assert "Infrastructure as code" in extract_skills(
            "Familiarity with infrastructure as code."
        )

    def test_unit_testing(self) -> None:
        assert "Unit testing" in extract_skills(
            "You write unit tests and unit testing matters."
        )

    def test_a_multi_word_skill_is_not_split_into_its_parts(self) -> None:
        # "machine learning" must not also register a bare "learning" skill if one existed.
        found = extract_skills("Applied machine learning experience.")
        assert "Machine learning" in found


class TestSetSemantics:
    def test_a_skill_named_many_times_counts_once(self) -> None:
        found = extract_skills("Python, Python, and more Python. Did we mention Python?")
        assert [s for s in found if s == "Python"] == ["Python"]

    def test_extraction_is_order_independent(self) -> None:
        assert extract_skills("Python and Docker") == extract_skills("Docker and Python")

    def test_empty_text_yields_nothing(self) -> None:
        assert extract_skills("") == set()
        assert extract_skills("   \n  ") == set()


class TestVocabularyIsData:
    def test_every_canonical_name_is_reachable_by_its_own_name(self) -> None:
        """A canonical name that its own text cannot find is a typo nobody would notice.

        The probe names Python alongside, because one-letter skills require a companion
        technology to count and would otherwise fail this for the right reason.
        """
        unreachable = [
            canonical
            for canonical in VOCABULARY
            if canonical not in extract_skills(f"We use {canonical} and Python here.")
        ]
        assert unreachable == []

    def test_no_alias_is_claimed_by_two_canonical_skills(self) -> None:
        seen: dict[str, str] = {}
        collisions: list[str] = []
        for canonical, aliases in VOCABULARY.items():
            for alias in aliases:
                key = alias.casefold()
                if key in seen and seen[key] != canonical:
                    collisions.append(f"{alias}: {seen[key]} and {canonical}")
                seen[key] = canonical
        assert collisions == []

    def test_the_vocabulary_is_not_trivially_small(self) -> None:
        # A vocabulary of thirty terms would score every posting the same.
        assert len(VOCABULARY) >= 120


class TestPerformance:
    def test_extraction_over_a_real_sized_description_is_fast(self) -> None:
        """Twenty of these run per page render, so this is a budget, not a micro-benchmark."""
        text = (
            "We are looking for an engineer to work on our platform. "
            "You will use Python, Go, Kubernetes and Terraform. " * 60
        )
        assert len(text) > 6_000

        started = time.perf_counter()
        for _ in range(20):
            extract_skills(text)
        elapsed = time.perf_counter() - started

        assert elapsed < 1.0, f"twenty descriptions took {elapsed:.2f}s"
