"""LinkedIn `Connections.csv` ingest.

Why hand-rolled tolerance instead of a bare `csv.reader`:
  * LinkedIn prepends a variable-length "Notes:" preamble before the real header.
  * Column order and presence has changed across export versions (Email Address came and
    went; "Connected On" formatting differs by locale).
  * Exports are frequently re-saved by Excel, which mangles the encoding to cp1252.

The parser therefore detects the header positionally, maps columns by name, and decodes
defensively. Every anomaly is recorded in a `ParseReport` rather than silently dropped.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import Iterable

from .models import Connection, ParseError, ParseReport

log = logging.getLogger(__name__)

# Candidate header names -> canonical field. Lowercased, whitespace-normalized.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "first_name": ("first name", "firstname", "first"),
    "last_name": ("last name", "lastname", "last"),
    "url": ("url", "profile url", "public profile url"),
    "email": ("email address", "email", "emailaddress"),
    "company_raw": ("company", "current company", "organization"),
    "position_raw": ("position", "title", "current position", "job title"),
    "connected_on_raw": ("connected on", "connectedon", "connected date"),
}

# Ordered by likelihood. utf-8-sig first: strips BOM and is what LinkedIn actually emits.
ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

DATE_FORMATS: tuple[str, ...] = (
    "%d %b %Y",     # 15 Mar 2022  (LinkedIn default, en-US)
    "%d %B %Y",     # 15 March 2022
    "%b %d, %Y",    # Mar 15, 2022
    "%B %d, %Y",    # March 15, 2022
    "%Y-%m-%d",     # ISO
    "%m/%d/%y",     # Excel round-trip
    "%m/%d/%Y",
    "%d/%m/%Y",
)

MAX_BYTES = 64 * 1024 * 1024  # 64 MB hard ceiling; a 30k-connection export is ~4 MB.


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Decode an uploaded file, returning (text, encoding_used).

    Falls back through a codec ladder and finally to lossy latin-1, which cannot fail.
    This is the fix for the classic `'charmap' codec can't decode byte 0x9d` failure mode
    on Excel-resaved exports.
    """
    if len(raw) > MAX_BYTES:
        raise ParseError(f"File exceeds the {MAX_BYTES // (1024 * 1024)} MB limit.")
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1/replace"


def _norm(s: str) -> str:
    return " ".join(s.replace("\ufeff", "").strip().lower().split())


def find_header_row(rows: list[list[str]], max_scan: int = 25) -> int:
    """Locate the real header row, skipping LinkedIn's notes preamble."""
    for i, row in enumerate(rows[:max_scan]):
        cells = {_norm(c) for c in row}
        if cells & set(COLUMN_ALIASES["first_name"]) and cells & set(COLUMN_ALIASES["last_name"]):
            return i
    return -1


def _map_columns(header: list[str]) -> dict[str, int]:
    normalized = [_norm(h) for h in header]
    mapping: dict[str, int] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field_name] = normalized.index(alias)
                break
    return mapping


def parse_connected_on(value: str) -> date | None:
    """Parse LinkedIn's loosely-specified date column. Returns None rather than raising."""
    v = value.strip()
    if not v:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def parse_connections(text: str) -> tuple[list[Connection], ParseReport]:
    """Parse export text into `Connection` records plus an ingest report.

    Raises `ParseError` only when the file is structurally unusable; every other anomaly
    is downgraded to a report warning so a partially-malformed export still yields value.
    """
    report = ParseReport()
    rows = [r for r in csv.reader(io.StringIO(text, newline="")) if any(c.strip() for c in r)]
    report.rows_scanned = len(rows)

    if not rows:
        raise ParseError("The file is empty.")

    header_idx = find_header_row(rows)
    if header_idx == -1:
        raise ParseError(
            "No header row containing 'First Name' and 'Last Name' was found. "
            "Confirm this is Connections.csv from the LinkedIn data export archive."
        )
    report.header_row_index = header_idx

    columns = _map_columns(rows[header_idx])
    report.detected_columns = dict(columns)
    for required in ("first_name", "last_name"):
        if required not in columns:
            raise ParseError(f"Required column '{required}' is missing from the header row.")
    for optional in ("company_raw", "position_raw", "connected_on_raw"):
        if optional not in columns:
            report.warnings.append(
                f"Column '{optional}' absent from this export; dependent metrics will be omitted."
            )

    def cell(row: list[str], key: str) -> str:
        idx = columns.get(key, -1)
        return row[idx].strip() if 0 <= idx < len(row) else ""

    connections: list[Connection] = []
    for row in rows[header_idx + 1 :]:
        first, last = cell(row, "first_name"), cell(row, "last_name")
        if not first and not last:
            report.rows_skipped += 1
            continue
        c = Connection(
            first_name=first,
            last_name=last,
            url=cell(row, "url"),
            email=cell(row, "email"),
            company_raw=cell(row, "company_raw"),
            position_raw=cell(row, "position_raw"),
            connected_on_raw=cell(row, "connected_on_raw"),
        )
        if not c.company_raw:
            report.missing_company += 1
        if not c.position_raw:
            report.missing_position += 1
        c.connected_on = parse_connected_on(c.connected_on_raw)
        if c.connected_on is None:
            report.unparsed_dates += 1
        connections.append(c)

    report.rows_parsed = len(connections)
    if not connections:
        raise ParseError(
            "The header was found but zero connection rows followed. "
            "This may be the wrong CSV from the archive."
        )

    if report.unparsed_dates and report.unparsed_dates == report.rows_parsed:
        report.warnings.append(
            "No 'Connected On' values could be parsed; temporal analysis is unavailable."
        )

    log.info(
        "parsed_connections rows_scanned=%d parsed=%d skipped=%d header_idx=%d",
        report.rows_scanned,
        report.rows_parsed,
        report.rows_skipped,
        header_idx,
    )
    return connections, report


def parse_file(raw: bytes) -> tuple[list[Connection], ParseReport]:
    """Convenience wrapper: decode then parse, annotating the encoding used."""
    text, encoding = decode_bytes(raw)
    connections, report = parse_connections(text)
    if encoding != "utf-8-sig":
        report.warnings.append(f"File decoded as '{encoding}' rather than UTF-8.")
    return connections, report


def iter_names(connections: Iterable[Connection]) -> list[str]:
    return [c.name for c in connections]
