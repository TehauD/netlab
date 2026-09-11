"""CLI surface: exit codes, output modes, and file handling."""

from __future__ import annotations

import json

import pytest

from netlab.cli import main


class TestAnalyzeCommand:
    def test_json_to_stdout(self, sample_csv_path, capsys):
        assert main(["analyze", sample_csv_path, "--no-graph"]) == 0
        document = json.loads(capsys.readouterr().out)
        assert document["overview"]["connections"] == 400
        assert "graph" not in document

    def test_summary_mode(self, sample_csv_path, capsys):
        assert main(["analyze", sample_csv_path, "--summary"]) == 0
        out = capsys.readouterr().out
        assert "connections" in out
        assert "no data left this machine" in out

    def test_markdown_to_file(self, sample_csv_path, tmp_path, capsys):
        target = tmp_path / "report.md"
        assert main(["analyze", sample_csv_path, "--markdown", "--out", str(target)]) == 0
        text = target.read_text(encoding="utf-8")
        assert text.startswith("# Network Analysis")
        assert "Employer concentration" in text

    def test_redaction_removes_names(self, sample_csv_path, capsys):
        main(["analyze", sample_csv_path, "--redact"])
        document = json.loads(capsys.readouterr().out)
        for node in document["graph"]["nodes"]:
            if node["kind"] == "person":
                assert node["url"] == ""

    def test_missing_file_exits_two(self, capsys):
        assert main(["analyze", "/nonexistent/Connections.csv"]) == 2
        assert "No such file" in capsys.readouterr().err

    def test_unparseable_file_exits_one(self, tmp_path, capsys):
        junk = tmp_path / "junk.csv"
        junk.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        assert main(["analyze", str(junk)]) == 1
        assert "Analysis failed" in capsys.readouterr().err


class TestSampleCommand:
    def test_writes_generated_export(self, tmp_path, capsys):
        target = tmp_path / "Connections.csv"
        assert main(["sample", "--out", str(target), "--count", "80"]) == 0
        assert "First Name" in target.read_text(encoding="utf-8")

    def test_seed_is_deterministic(self, tmp_path):
        a, b = tmp_path / "a.csv", tmp_path / "b.csv"
        main(["sample", "--out", str(a), "--count", "60", "--seed", "11"])
        main(["sample", "--out", str(b), "--count", "60", "--seed", "11"])
        assert a.read_bytes() == b.read_bytes()


class TestParser:
    def test_missing_subcommand_exits(self):
        with pytest.raises(SystemExit):
            main([])

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert "netlab" in capsys.readouterr().out
