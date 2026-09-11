"""Cross-engine parity.

The browser and Python engines are independent implementations of the same rules. Without
a guard they drift, and a user would silently get different numbers depending on whether
`netlab serve` happened to be running. This test executes the JavaScript modules under Node
and diffs the results against Python.

Skipped when Node is unavailable, so the suite stays green in a Python-only environment.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from netlab.core import analyze_path

NODE = shutil.which("node")
HARNESS = Path(__file__).resolve().parents[1] / "scripts" / "parity_check.mjs"

pytestmark = pytest.mark.skipif(
    NODE is None or not HARNESS.is_file(),
    reason="Node.js or the parity harness is unavailable.",
)

# Fields that must agree exactly -- counts, dates, and categorical labels.
EXACT_FIELDS = [
    "connections", "distinct_companies", "with_company", "with_position", "with_date",
    "first_connection", "last_connection", "total_months", "active_months",
    "half_life", "modal_function", "projection_edges", "merged_companies",
]

# Floating-point statistics: agreement to 3 decimal places is sufficient and avoids
# coupling the test to language-specific rounding behavior.
APPROX_FIELDS = ["gini", "hhi", "entropy", "effective_companies", "singleton_rate",
                 "mean_seniority_rank"]


@pytest.fixture(scope="module")
def js_result(sample_csv_path) -> dict:
    completed = subprocess.run(
        [NODE, str(HARNESS), sample_csv_path],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def py_result(sample_csv_path) -> dict:
    doc = analyze_path(sample_csv_path)
    conc = doc["companies"]["concentration"]
    t = doc["temporal"]
    return {
        "connections": doc["overview"]["connections"],
        "distinct_companies": doc["overview"]["distinct_companies"],
        "with_company": doc["overview"]["with_company"],
        "with_position": doc["overview"]["with_position"],
        "with_date": doc["overview"]["with_date"],
        "first_connection": doc["overview"]["first_connection"],
        "last_connection": doc["overview"]["last_connection"],
        "gini": conc["gini"],
        "hhi": conc["hhi_normalized"],
        "entropy": conc["shannon_entropy"],
        "effective_companies": conc["effective_companies"],
        "singleton_rate": conc["singleton_rate"],
        "total_months": t["total_months"],
        "active_months": t["active_months"],
        "burst_months": len(t["bursts"]),
        "half_life": t["accumulation_half_life"],
        "mean_seniority_rank": doc["composition"]["seniority"]["mean_rank"],
        "modal_function": doc["composition"]["function"]["modal"],
        "projection_edges": doc["structure"]["projection"]["edges"],
        "merged_companies": doc["data_quality"]["entity_resolution"]["merged"],
        "top_companies": [[e["company"], e["count"]] for e in doc["companies"]["largest"][:5]],
    }


@pytest.mark.parametrize("field", EXACT_FIELDS)
def test_exact_agreement(field, js_result, py_result):
    assert js_result[field] == py_result[field], f"{field} diverged between engines"


@pytest.mark.parametrize("field", APPROX_FIELDS)
def test_statistical_agreement(field, js_result, py_result):
    assert js_result[field] == pytest.approx(py_result[field], abs=1e-3), (
        f"{field} diverged between engines"
    )


def test_company_ranking_agrees(js_result, py_result):
    assert js_result["top_companies"] == py_result["top_companies"]


def test_burst_detection_agrees(js_result, py_result):
    assert js_result["burst_months"] == py_result["burst_months"]
