"""HTTP contract and privacy guarantees."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from netlab.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _upload(sample_bytes):
    return {"file": ("Connections.csv", sample_bytes, "text/csv")}


class TestMeta:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["persistence_enabled"] is False

    def test_ui_is_served(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "netlab" in response.text

    def test_openapi_schema_published(self, client):
        assert "/api/analyze" in client.get("/openapi.json").json()["paths"]

    def test_sample_is_parseable(self, client):
        response = client.get("/api/sample?count=120")
        assert response.status_code == 200
        assert "First Name" in response.text
        analysis = client.post("/api/analyze", files=_upload(response.content)).json()
        assert analysis["overview"]["connections"] == 120

    def test_sample_count_is_clamped(self, client):
        response = client.get("/api/sample?count=999999")
        assert response.text.count("\n") < 5100


class TestAnalyze:
    def test_returns_full_document(self, client, sample_bytes):
        body = client.post("/api/analyze", files=_upload(sample_bytes)).json()
        for section in ("overview", "companies", "temporal", "composition",
                        "structure", "eras", "insights", "graph"):
            assert section in body
        assert body["correlation_id"]

    def test_correlation_id_echoed(self, client, sample_bytes):
        response = client.post(
            "/api/analyze", files=_upload(sample_bytes), headers={"x-correlation-id": "abc123"}
        )
        assert response.headers["x-correlation-id"] == "abc123"

    def test_cluster_mode_applied(self, client, sample_bytes):
        body = client.post(
            "/api/analyze", files=_upload(sample_bytes), data={"cluster_by": "seniority"}
        ).json()
        assert body["graph"]["cluster_by"] == "seniority"

    def test_rejects_unknown_cluster_mode(self, client, sample_bytes):
        response = client.post(
            "/api/analyze", files=_upload(sample_bytes), data={"cluster_by": "colour"}
        )
        assert response.status_code == 400

    def test_graph_can_be_omitted(self, client, sample_bytes):
        body = client.post(
            "/api/analyze", files=_upload(sample_bytes), data={"include_graph": "false"}
        ).json()
        assert "graph" not in body

    def test_redaction_flag(self, client, sample_bytes):
        body = client.post(
            "/api/analyze", files=_upload(sample_bytes), data={"redact": "true"}
        ).json()
        assert body["graph"]["redacted"] is True

    def test_empty_upload_rejected(self, client):
        response = client.post("/api/analyze", files={"file": ("empty.csv", b"", "text/csv")})
        assert response.status_code == 400

    def test_malformed_upload_returns_422_with_guidance(self, client):
        response = client.post(
            "/api/analyze", files={"file": ("junk.csv", b"a,b,c\n1,2,3\n", "text/csv")}
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "ParseError"
        assert "Connections.csv" in body["detail"]
        assert body["correlation_id"]


class TestReport:
    def test_markdown_artifact(self, client, sample_bytes):
        response = client.post("/api/report", files=_upload(sample_bytes))
        assert response.status_code == 200
        assert response.text.startswith("# Network Analysis")
        assert "Employer concentration" in response.text

    def test_report_redacts_by_default(self, client, sample_bytes):
        """The report is the shareable artifact, so names must not appear in it."""
        text = client.post("/api/report", files=_upload(sample_bytes)).text
        assert "linkedin.com/in/" not in text
