"""Entity resolution and title taxonomy."""

from __future__ import annotations

import pytest

from netlab.core.normalize import (
    canonical_company,
    classify_function,
    classify_seniority,
    enrich,
    resolution_gain,
)


class TestCanonicalCompany:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Acme, Inc.", "Acme"),
            ("Acme Inc", "Acme"),
            ("Acme LLC", "Acme"),
            ("Acme Ltd.", "Acme"),
            ("  Acme   Corp  ", "Acme"),
            ("Acme Holdings Ltd, Inc.", "Acme Holdings"),
            ("Acme (Contract)", "Acme"),
            ("IBM Corporation", "IBM"),
            ("self employed", "Self-Employed"),
            ("N/A", ""),
            ("", ""),
        ],
    )
    def test_cascade(self, raw, expected):
        assert canonical_company(raw) == expected

    def test_short_acronyms_preserved(self):
        assert canonical_company("NASA") == "NASA"
        assert canonical_company("IBM") == "IBM"

    def test_shouted_multiword_gets_title_cased(self):
        assert canonical_company("NORTHWIND HEALTH SYSTEMS") == "Northwind Health Systems"

    def test_is_idempotent(self):
        once = canonical_company("Acme, Inc.")
        assert canonical_company(once) == once


class TestSeniority:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("VP of Engineering", "executive"),          # must beat "manager"
            ("Vice President, Sales", "executive"),
            ("Chief Technology Officer", "executive"),
            ("Co-Founder", "founder_owner"),
            ("Director of Data Science", "director"),
            ("Engineering Manager", "manager"),
            ("Principal Architect", "staff_principal"),
            ("Senior Software Engineer", "senior"),
            ("Software Engineer", "individual_contributor"),
            ("Graduate Student", "student"),
            ("", "unknown"),
        ],
    )
    def test_ladder_precedence(self, title, expected):
        assert classify_seniority(title)[0] == expected

    def test_rank_is_monotonic_with_ladder(self):
        assert classify_seniority("Software Engineer")[1] < classify_seniority("VP of Product")[1]


class TestFunction:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Data Scientist", "data_ai"),
            ("Machine Learning Engineer", "data_ai"),
            ("Engineering Manager", "engineering"),
            ("Registered Nurse", "healthcare"),
            ("Director of Nursing", "healthcare"),
            ("Account Executive", "sales"),
            ("Head of Marketing", "marketing"),
            ("Financial Analyst", "finance"),
            ("Technical Recruiter", "people_ops"),
            ("General Counsel", "legal"),
            ("Supply Chain Analyst", "operations"),
            ("", "unclassified"),
        ],
    )
    def test_domains(self, title, expected):
        assert classify_function(title) == expected

    def test_data_ai_wins_over_engineering(self):
        """Ordering matters: an ML engineer is a data practitioner, not a generic dev."""
        assert classify_function("Machine Learning Engineer") == "data_ai"


def test_enrich_is_idempotent(minimal_connections):
    connections, _ = minimal_connections
    first = [(c.company, c.seniority, c.function) for c in connections]
    second = [(c.company, c.seniority, c.function) for c in enrich(connections)]
    assert first == second


def test_resolution_gain_counts_merges(minimal_connections):
    connections, _ = minimal_connections
    gain = resolution_gain(connections)
    # "Analytical Engines Inc." and "Analytical Engines" collapse to one employer.
    assert gain["raw_distinct"] == 3
    assert gain["canonical_distinct"] == 2
    assert gain["merged"] == 1
