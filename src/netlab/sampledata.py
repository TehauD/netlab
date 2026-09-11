"""Synthetic export generator.

Exists so the repository is demonstrable without anyone committing a real contact list,
and so tests exercise realistic structure rather than toy fixtures. The generator plants
the phenomena the analytics are designed to detect:

* a Zipf-distributed employer size distribution (heavy tail, many singletons)
* three career "eras" separated by dormancy gaps
* hiring-wave bursts concentrated in single months
* an upward seniority drift over time
* deliberate dirt: legal-suffix variants, a Notes preamble, blank fields, odd date formats

Seeded: identical output for identical seed, on every platform.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

_COMPANY_STEMS = [
    "Northwind Health", "Contoso", "Fabrikam", "Litware", "Adventure Works", "Tailspin",
    "Proseware", "Wide World Imports", "Lamna Healthcare", "Woodgrove Bank", "Relecloud",
    "VanArsdel", "Trey Research", "Fourth Coffee", "Alpine Ski House", "Blue Yonder",
    "Coho Vineyard", "Graphic Design Institute", "Humongous Insurance", "Margie's Travel",
    "Nod Publishers", "Southridge Video", "The Phone Company", "Consolidated Messenger",
]
_SUFFIXES = ["", "", "", ", Inc.", " LLC", " Ltd.", " Corp"]

_TITLES = [
    ("Software Engineer", 2), ("Senior Software Engineer", 3), ("Staff Engineer", 4),
    ("Principal Architect", 4), ("Engineering Manager", 5), ("Director of Engineering", 6),
    ("VP of Engineering", 7), ("Chief Technology Officer", 7), ("Founder", 8),
    ("Data Scientist", 2), ("Senior Data Scientist", 3), ("Machine Learning Engineer", 2),
    ("Director of Data Science", 6), ("Analytics Manager", 5), ("Data Engineer", 2),
    ("Registered Nurse", 2), ("Clinical Informatics Specialist", 2), ("Pharmacist", 2),
    ("Director of Nursing", 6), ("Chief Medical Officer", 7), ("Physician", 2),
    ("Product Manager", 2), ("Senior Product Manager", 3), ("Director of Product", 6),
    ("UX Designer", 2), ("Senior UX Researcher", 3),
    ("Account Executive", 2), ("Regional Sales Director", 6), ("Customer Success Manager", 5),
    ("Marketing Coordinator", 2), ("Head of Marketing", 7),
    ("Financial Analyst", 2), ("Controller", 2), ("Chief Financial Officer", 7),
    ("Technical Recruiter", 2), ("HR Business Partner", 2),
    ("General Counsel", 7), ("Compliance Analyst", 2),
    ("Operations Manager", 5), ("Supply Chain Analyst", 2),
    ("Professor of Computer Science", 2), ("Research Fellow", 4), ("Graduate Student", 1),
    ("", 0), ("", 0),  # deliberate blanks: exports really do contain these
]

_FIRST = """James Mary Robert Patricia John Jennifer Michael Linda David Elizabeth William
Barbara Richard Susan Joseph Jessica Thomas Sarah Charles Karen Priya Wei Ahmed Sofia Luca
Amara Kenji Ingrid Mateo Fatima Dmitri Chioma Yusuf Anika Tomas Leila Ravi Hana Olu Nadia""".split()

_LAST = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez
Hernandez Lopez Gonzalez Wilson Anderson Thomas Taylor Moore Jackson Martin Patel Nguyen
Kim Okafor Rossi Novak Andersson Silva Haddad Ivanov Okonkwo Demir Sharma Dubois Kowalski""".split()

_DATE_FORMATS = ["%d %b %Y", "%d %b %Y", "%d %b %Y", "%b %d, %Y"]  # mostly canonical, some drift


def generate(n: int = 600, seed: int = 42, end: date | None = None) -> list[dict[str, str]]:
    """Build `n` synthetic connection records with planted structure."""
    rng = random.Random(seed)
    end = end or date(2026, 6, 30)

    # Zipf-ish employer pool: a few dominant employers, a long tail of one-offs.
    pool: list[str] = []
    for rank, stem in enumerate(_COMPANY_STEMS, start=1):
        weight = max(int(140 / rank), 1)
        pool.extend([stem] * weight)
    tail = [f"{rng.choice(_LAST)} {rng.choice(['Group', 'Partners', 'Labs', 'Studio', 'Clinic'])}"
            for _ in range(120)]
    pool.extend(tail)

    # Three eras separated by dormancy, with burst months inside each.
    span_start = end - timedelta(days=365 * 11)
    eras = [
        (span_start, span_start + timedelta(days=365 * 4), 0.30),
        (span_start + timedelta(days=365 * 5), span_start + timedelta(days=365 * 8), 0.38),
        (span_start + timedelta(days=int(365 * 8.7)), end, 0.32),
    ]

    # Allocate exactly `n` rows: floor each share, then hand the remainder to the last era.
    allocations = [int(n * share) for _, _, share in eras]
    allocations[-1] += n - sum(allocations)

    rows: list[dict[str, str]] = []
    for era_index, ((start, stop, _share), count) in enumerate(zip(eras, allocations)):
        days = max((stop - start).days, 1)
        burst_offsets = [rng.randrange(days) for _ in range(2)]
        for _ in range(count):
            if rng.random() < 0.22:  # burst membership
                offset = rng.choice(burst_offsets) + rng.randrange(-10, 10)
            else:
                offset = rng.randrange(days)
            when = start + timedelta(days=max(min(offset, days), 0))

            title, base_rank = rng.choice(_TITLES)
            # Seniority drift: later eras skew senior.
            if title and rng.random() < 0.18 * era_index and base_rank in (2, 3):
                title = rng.choice(["Director of Operations", "VP of Product", "Senior Director"])

            # Legal-suffix drift is applied per row, so "Contoso" and "Contoso, Inc."
            # coexist in the same file -- exactly what entity resolution must absorb.
            company = (rng.choice(pool) + rng.choice(_SUFFIXES)) if rng.random() > 0.04 else ""
            first, last = rng.choice(_FIRST), rng.choice(_LAST)
            rows.append(
                {
                    "First Name": first,
                    "Last Name": last,
                    "URL": f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}-{rng.randrange(100, 999)}",
                    "Email Address": "",
                    "Company": company,
                    "Position": title,
                    "Connected On": when.strftime(rng.choice(_DATE_FORMATS)),
                }
            )

    rows.sort(key=lambda r: r["Connected On"])
    return rows


def write_sample(path: str | Path, n: int = 600, seed: int = 42) -> Path:
    """Write a synthetic export, including LinkedIn's real-world Notes preamble."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = generate(n=n, seed=seed)
    fields = ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"]

    with target.open("w", encoding="utf-8", newline="") as fh:
        fh.write('Notes:\n"When exporting your connection data, you may notice that some '
                 'of the email addresses are missing. ...."\n\n')
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


if __name__ == "__main__":  # pragma: no cover
    print(write_sample("data/sample/Connections.csv"))
