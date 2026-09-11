"""Analysis orchestration.

One entry point, `analyze_bytes`, so the CLI, the HTTP API, and any notebook all execute
an identical code path. The returned document is a plain dict -- JSON-serializable, schema-
stable, and safe to persist as a pipeline artifact.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

from . import analytics, insights
from .models import Connection, ParseReport
from .normalize import enrich
from .parsing import parse_file

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"


def analyze(
    connections: Sequence[Connection],
    report: ParseReport,
    *,
    cluster_by: str = "company",
    redact: bool = False,
    include_graph: bool = True,
) -> dict[str, Any]:
    """Run every analysis section over an already-parsed, enriched connection set."""
    started = time.perf_counter()

    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "overview": analytics.overview(connections),
        "data_quality": analytics.data_quality(connections, report),
        "companies": analytics.company_profile(connections),
        "temporal": analytics.temporal_profile(connections),
        "composition": analytics.composition_profile(connections),
        "structure": analytics.structure_profile(connections),
        "eras": analytics.detect_eras(connections),
    }
    document["insights"] = insights.generate(document)

    if include_graph:
        document["graph"] = analytics.graph_payload(connections, cluster_by=cluster_by, redact=redact)

    document["runtime_ms"] = round((time.perf_counter() - started) * 1000, 2)
    log.info(
        "analysis_complete connections=%d sections=%d runtime_ms=%.1f",
        len(connections),
        len(document),
        document["runtime_ms"],
    )
    return document


def analyze_bytes(
    raw: bytes,
    *,
    cluster_by: str = "company",
    redact: bool = False,
    include_graph: bool = True,
) -> dict[str, Any]:
    """Decode -> parse -> enrich -> analyze. The single supported entry point."""
    connections, report = parse_file(raw)
    connections = enrich(connections)
    return analyze(connections, report, cluster_by=cluster_by, redact=redact, include_graph=include_graph)


def analyze_path(path: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper for local files and batch jobs."""
    with open(path, "rb") as fh:
        return analyze_bytes(fh.read(), **kwargs)
