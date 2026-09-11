"""Analysis sections, insight generation, and pipeline determinism."""

from __future__ import annotations

from netlab.core import analytics, analyze_bytes, insights
from netlab.core.analytics import _components


class TestSections:
    def test_overview_counts_and_span(self, analysis):
        ov = analysis["overview"]
        assert ov["connections"] == 400
        assert ov["distinct_companies"] > 0
        assert ov["span_days"] > 365
        assert ov["first_connection"] < ov["last_connection"]

    def test_company_profile_shape(self, analysis):
        c = analysis["companies"]
        assert c["available"]
        assert len(c["largest"]) <= 25
        assert c["largest"] == sorted(c["largest"], key=lambda e: -e["count"])
        k = c["concentration"]
        assert 0 <= k["gini"] <= 1
        assert 0 <= k["hhi_normalized"] <= 1
        assert 0 <= k["pielou_evenness"] <= 1
        assert k["effective_companies"] <= c["distinct"]

    def test_temporal_series_is_dense(self, analysis):
        t = analysis["temporal"]
        assert t["available"]
        months = [p["month"] for p in t["monthly"]]
        assert months == sorted(months), "Month index must be ordered"
        assert len(months) == t["total_months"]
        assert t["active_months"] <= t["total_months"]
        assert 0 <= t["duty_cycle"] <= 1

    def test_bursts_exceed_threshold(self, analysis):
        for burst in analysis["temporal"]["bursts"]:
            assert burst["z"] >= 3.5

    def test_composition_rank_bounds(self, analysis):
        s = analysis["composition"]["seniority"]
        assert 0 <= s["mean_rank"] <= 8
        assert 0 <= s["classified_rate"] <= 1
        assert 0 <= s["leadership_share"] <= 1

    def test_projection_is_reported_with_its_caveat(self, analysis):
        proj = analysis["structure"]["projection"]
        assert "cliques" in proj["note"]
        assert proj["components"] >= 1
        assert 0 <= proj["largest_component_share"] <= 1

    def test_cooccurrence_edges_respect_min_weight(self, analysis):
        co = analysis["structure"]["company_cooccurrence"]
        if co["available"]:
            assert co["inferred"] is True
            assert all(e["weight"] >= co["min_weight"] for e in co["top_edges"])

    def test_eras_are_contiguous_and_ordered(self, analysis):
        eras = analysis["eras"]
        assert eras["available"]
        windows = [(e["start"], e["end"]) for e in eras["eras"]]
        assert windows == sorted(windows)
        for (_, end), (start, _) in zip(windows, windows[1:]):
            assert end <= start, "Eras must not overlap"
        assert sum(e["count"] for e in eras["eras"]) == analysis["overview"]["with_date"]


class TestGraphPayload:
    def test_hub_edges_match_people_with_a_company(self, sample_bytes):
        doc = analyze_bytes(sample_bytes, cluster_by="company")
        g = doc["graph"]
        people = [n for n in g["nodes"] if n["kind"] == "person"]
        hubs = [n for n in g["nodes"] if n["kind"] == "hub"]
        assert len(people) == doc["overview"]["connections"]
        assert len(hubs) == doc["overview"]["distinct_companies"]
        assert g["edge_count"] == doc["overview"]["with_company"]

    def test_no_clustering_emits_no_hubs(self, sample_bytes):
        g = analyze_bytes(sample_bytes, cluster_by="none")["graph"]
        assert all(n["kind"] == "person" for n in g["nodes"])
        assert g["edge_count"] == 0

    def test_invalid_cluster_mode_falls_back(self, sample_bytes):
        g = analyze_bytes(sample_bytes, cluster_by="nonsense")["graph"]
        assert g["cluster_by"] == "company"

    def test_redaction_strips_identifiers(self, sample_bytes):
        g = analyze_bytes(sample_bytes, redact=True)["graph"]
        for node in g["nodes"]:
            if node["kind"] == "person":
                assert node["url"] == ""
                assert len(node["label"]) <= 5 and node["label"].endswith(".")


class TestInsights:
    def test_every_insight_is_well_formed(self, analysis):
        assert analysis["insights"]
        for item in analysis["insights"]:
            assert set(item) == {"title", "detail", "kind", "confidence", "evidence"}
            assert item["confidence"] in {"high", "medium", "low"}
            assert item["title"] and item["detail"]

    def test_ranked_by_confidence(self, analysis):
        order = {"high": 0, "medium": 1, "low": 2}
        ranks = [order[i["confidence"]] for i in analysis["insights"]]
        assert ranks == sorted(ranks)

    def test_methodology_caveat_always_present(self, analysis):
        assert any(i["kind"] == "methodology" for i in analysis["insights"])

    def test_empty_document_yields_no_insights(self):
        assert insights.generate({"overview": {"connections": 0}}) == []


class TestDeterminism:
    def test_repeat_runs_are_identical(self, sample_bytes):
        first = analyze_bytes(sample_bytes)
        second = analyze_bytes(sample_bytes)
        first.pop("runtime_ms"), second.pop("runtime_ms")
        assert first == second


class TestGraphUtilities:
    def test_union_find_components(self):
        comps = _components([("a", "b"), ("b", "c"), ("x", "y")])
        assert sorted(len(c) for c in comps) == [2, 3]

    def test_components_of_empty_edge_set(self):
        assert _components([]) == []


class TestDegenerateInputs:
    def test_single_connection_degrades_gracefully(self):
        raw = b"First Name,Last Name,Company,Position,Connected On\nAda,Lovelace,Acme,Engineer,15 Mar 2022\n"
        doc = analyze_bytes(raw)
        assert doc["overview"]["connections"] == 1
        assert doc["temporal"]["available"] is False
        assert doc["eras"]["available"] is False
        assert doc["companies"]["available"] is True

    def test_no_company_column(self):
        raw = b"First Name,Last Name,Connected On\nAda,Lovelace,15 Mar 2022\nAlan,Turing,16 Mar 2022\n"
        doc = analyze_bytes(raw)
        assert doc["companies"]["available"] is False
        assert doc["structure"]["company_cooccurrence"]["available"] is False
