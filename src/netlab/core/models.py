"""Core domain models.

Intent: the analytics core is deliberately dependency-free (stdlib only) so it can be
imported by a CLI, a FastAPI process, a notebook, or an Azure Function without dragging
a web framework into the runtime. Pydantic is used only at the HTTP boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional


# --------------------------------------------------------------------------------------
# Taxonomy enums-as-constants (plain strings keep JSON serialization trivial/deterministic)
# --------------------------------------------------------------------------------------

SENIORITY_LADDER: list[str] = [
    "unknown",
    "student",
    "individual_contributor",
    "senior",
    "staff_principal",
    "manager",
    "director",
    "executive",
    "founder_owner",
]
"""Ordinal ladder. Index == rank; rank is used for regression/drift analysis."""

SENIORITY_RANK: dict[str, int] = {name: i for i, name in enumerate(SENIORITY_LADDER)}


@dataclass(slots=True)
class Connection:
    """One first-degree connection as exported by LinkedIn.

    All fields are optional in the export; downstream code must never assume presence.
    """

    first_name: str = ""
    last_name: str = ""
    url: str = ""
    email: str = ""
    company_raw: str = ""
    position_raw: str = ""
    connected_on_raw: str = ""

    # Derived (populated by the enrichment pass).
    company: str = ""
    position: str = ""
    connected_on: Optional[date] = None
    seniority: str = "unknown"
    seniority_rank: int = 0
    function: str = "unclassified"

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def to_public_dict(self, redact: bool = False) -> dict[str, Any]:
        """Serialize for transport. `redact` strips direct identifiers for shareable output."""
        if redact:
            return {
                "name": _initials(self.first_name, self.last_name),
                "company": self.company,
                "position": self.position,
                "connected_on": self.connected_on.isoformat() if self.connected_on else None,
                "seniority": self.seniority,
                "seniority_rank": self.seniority_rank,
                "function": self.function,
                "url": "",
            }
        return {
            "name": self.name,
            "company": self.company,
            "position": self.position,
            "connected_on": self.connected_on.isoformat() if self.connected_on else None,
            "seniority": self.seniority,
            "seniority_rank": self.seniority_rank,
            "function": self.function,
            "url": self.url,
        }


def _initials(first: str, last: str) -> str:
    a = (first[:1] or "?").upper()
    b = (last[:1] or "?").upper()
    return f"{a}.{b}."


@dataclass(slots=True)
class ParseReport:
    """Ingest telemetry. Surfaced in the UI so data quality is never invisible."""

    rows_scanned: int = 0
    rows_parsed: int = 0
    rows_skipped: int = 0
    header_row_index: int = -1
    detected_columns: dict[str, int] = field(default_factory=dict)
    missing_company: int = 0
    missing_position: int = 0
    unparsed_dates: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def completeness(self) -> dict[str, float]:
        n = max(self.rows_parsed, 1)
        return {
            "company": round(1 - self.missing_company / n, 4),
            "position": round(1 - self.missing_position / n, 4),
            "connected_on": round(1 - self.unparsed_dates / n, 4),
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["completeness"] = self.completeness
        return d


class NetlabError(Exception):
    """Base class for all recoverable, user-facing errors."""


class ParseError(NetlabError):
    """Raised when the supplied file is not a usable LinkedIn Connections export."""
