"""Ingest robustness.

These cases encode every malformed-export failure mode encountered in the wild: a Notes
preamble, Excel's cp1252 re-encoding, quoted commas, missing optional columns, and empty
rows. Each is a regression guard, not a hypothetical.
"""

from __future__ import annotations

import pytest

from netlab.core import ParseError, parse_file
from netlab.core.parsing import decode_bytes, find_header_row, parse_connected_on


class TestHeaderDetection:
    def test_skips_notes_preamble(self, minimal_connections):
        connections, report = minimal_connections
        # Blank lines are dropped before indexing, so the header lands at row 2.
        assert report.header_row_index == 2
        assert report.rows_parsed == 4

    def test_missing_header_raises(self):
        with pytest.raises(ParseError, match="No header row"):
            parse_file(b"a,b,c\n1,2,3\n")

    def test_empty_file_raises(self):
        with pytest.raises(ParseError, match="empty"):
            parse_file(b"")

    def test_alternate_column_names(self):
        raw = b"First,Last,Title,Organization,Connected Date\nAda,Lovelace,Engineer,Acme,15 Mar 2022\n"
        connections, report = parse_file(raw)
        assert connections[0].position_raw == "Engineer"
        assert connections[0].company_raw == "Acme"

    def test_header_row_scan_is_bounded(self):
        rows = [["junk"] for _ in range(40)] + [["First Name", "Last Name"]]
        assert find_header_row(rows) == -1


class TestFieldHandling:
    def test_quoted_comma_preserved(self, minimal_connections):
        connections, _ = minimal_connections
        assert connections[1].position_raw == "Director, Systems"

    def test_blank_row_counted_not_dropped_silently(self, minimal_connections):
        connections, report = minimal_connections
        assert report.missing_company == 1
        assert report.unparsed_dates == 1
        assert connections[3].name == "Katherine Johnson"

    def test_completeness_reported(self, minimal_connections):
        _, report = minimal_connections
        assert report.completeness["company"] == 0.75
        assert 0 <= report.completeness["connected_on"] <= 1


class TestEncoding:
    @pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252", "latin-1"])
    def test_codec_ladder(self, encoding):
        text = "First Name,Last Name,Company\nJosé,Muñoz,Café Corp\n"
        decoded, used = decode_bytes(text.encode(encoding))
        assert "Name" in decoded
        assert used

    def test_cp1252_smart_quote_does_not_crash(self):
        """The 0x9d byte that breaks a naive `open(..., encoding='cp1252')`."""
        raw = b"First Name,Last Name,Company\nAda,Lovelace,Acme\x9d Labs\n"
        connections, report = parse_file(raw)
        assert len(connections) == 1
        assert any("decoded as" in w for w in report.warnings)

    def test_oversized_payload_rejected(self):
        with pytest.raises(ParseError, match="exceeds"):
            decode_bytes(b"x" * (65 * 1024 * 1024))


class TestDateParsing:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("15 Mar 2022", (2022, 3, 15)),
            ("15 March 2022", (2022, 3, 15)),
            ("Mar 15, 2022", (2022, 3, 15)),
            ("2022-03-15", (2022, 3, 15)),
            ("03/15/2022", (2022, 3, 15)),
        ],
    )
    def test_supported_formats(self, value, expected):
        parsed = parse_connected_on(value)
        assert parsed is not None
        assert (parsed.year, parsed.month, parsed.day) == expected

    @pytest.mark.parametrize("value", ["", "   ", "not a date", "13/45/9999"])
    def test_unparseable_returns_none_rather_than_raising(self, value):
        assert parse_connected_on(value) is None


def test_sample_export_parses_cleanly(sample_bytes):
    connections, report = parse_file(sample_bytes)
    assert report.rows_parsed == len(connections) == 400
    assert report.rows_skipped == 0
    assert report.completeness["connected_on"] > 0.99
