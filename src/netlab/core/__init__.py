"""Dependency-free analytics core for LinkedIn connection exports."""

from .analytics import (
    company_cooccurrence,
    company_profile,
    composition_profile,
    data_quality,
    detect_eras,
    graph_payload,
    overview,
    structure_profile,
    temporal_profile,
)
from .insights import generate as generate_insights
from .models import Connection, NetlabError, ParseError, ParseReport
from .normalize import canonical_company, classify_function, classify_seniority, enrich
from .parsing import parse_connections, parse_file
from .pipeline import SCHEMA_VERSION, analyze, analyze_bytes, analyze_path
from .report import render_markdown

__all__ = [
    "Connection",
    "ParseReport",
    "NetlabError",
    "ParseError",
    "SCHEMA_VERSION",
    "analyze",
    "analyze_bytes",
    "analyze_path",
    "parse_file",
    "parse_connections",
    "enrich",
    "canonical_company",
    "classify_seniority",
    "classify_function",
    "overview",
    "data_quality",
    "company_profile",
    "temporal_profile",
    "composition_profile",
    "structure_profile",
    "company_cooccurrence",
    "detect_eras",
    "graph_payload",
    "generate_insights",
    "render_markdown",
]
