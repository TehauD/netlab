"""Shared fixtures.

The synthetic export is generated per-session rather than committed as a binary fixture,
so the test corpus and the demo data can never drift apart.
"""

from __future__ import annotations

import pytest

from netlab.core import analyze_bytes, enrich, parse_file
from netlab.sampledata import generate, write_sample

MINIMAL_CSV = """Notes:
"Some preamble LinkedIn inserts."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Ada,Lovelace,https://linkedin.com/in/ada,,Analytical Engines Inc.,Principal Engineer,15 Mar 2022
Grace,Hopper,https://linkedin.com/in/grace,,Analytical Engines,"Director, Systems",02 Jan 2021
Alan,Turing,,,Bletchley Ltd.,Research Fellow,"Nov 3, 2019"
Katherine,Johnson,,,,,
"""


@pytest.fixture(scope="session")
def sample_csv_path(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("data") / "Connections.csv"
    write_sample(path, n=400, seed=7)
    return str(path)


@pytest.fixture(scope="session")
def sample_bytes(sample_csv_path) -> bytes:
    with open(sample_csv_path, "rb") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def analysis(sample_bytes) -> dict:
    return analyze_bytes(sample_bytes)


@pytest.fixture()
def minimal_connections():
    connections, report = parse_file(MINIMAL_CSV.encode("utf-8"))
    return enrich(connections), report


@pytest.fixture(scope="session")
def sample_rows():
    return generate(n=200, seed=7)
