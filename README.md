# netlab

**Local-first network analysis for your LinkedIn connections export.**

Navigate to https://www.linkedin.com/mypreferences/d/download-my-data to request your archive (connections.csv).  

It can take a day to generate...

Drop in `Connections.csv`, get a force-directed graph plus a statistical read on your
professional network: employer concentration, temporal bursts, seniority drift, functional
homophily, and unsupervised career-era segmentation. Nothing is uploaded. Nothing is stored.

[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-0a9edc)](tests/)
[![Code style](https://img.shields.io/badge/lint-ruff-d7ff64)](https://docs.astral.sh/ruff/)

---

## Table of contents

- [What this actually analyzes](#what-this-actually-analyzes)
- [Quickstart](#quickstart)
- [Getting your LinkedIn export](#getting-your-linkedin-export)
- [The analysis](#the-analysis)
- [Architecture](#architecture)
- [CLI reference](#cli-reference)
- [HTTP API reference](#http-api-reference)
- [Configuration](#configuration)
- [Privacy model](#privacy-model)
- [Local development](#local-development)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## What this actually analyzes

Most "visualize your LinkedIn network" tools render a dense interconnected mesh. That mesh
is fabricated. A LinkedIn export contains **exactly one hop** — you to each connection —
and LinkedIn exposes no second-degree data through the export or any public API.

What the file genuinely is: a **bipartite affiliation network** of people and employers,
time-stamped by connection date. That is still analytically rich, and netlab works with the
structure that actually exists:

| Layer | Status | What it is |
| --- | --- | --- |
| `person → employer` | **Observed** | The real bipartite graph in the file |
| `person → person` | **Derived, closed-form** | The one-mode projection — a disjoint union of cliques, since each person has one employer. Reported analytically, never materialized, and explicitly labeled as a structural artifact |
| `employer → employer` | **Inferred** | Employers whose connections repeatedly appeared in the same month. The only non-trivial topology recoverable from a one-hop export — and flagged as a hypothesis, not a finding |

Every inferred quantity is labeled `inferred` in the output. The **Method** tab in the UI
exists specifically to keep observation and construction separable.

---

## Quickstart

```bash
git clone https://github.com/your-org/linkedin-network-lab.git
cd linkedin-network-lab

python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

netlab serve                                          # → http://127.0.0.1:8787
```

Open the URL, drop in `Connections.csv`, and the analysis populates immediately. No export
of your own yet? Click **try the synthetic sample** — a seeded, generated network with
planted structure.

Prefer the terminal:

```bash
netlab analyze ~/Downloads/Connections.csv --summary
netlab analyze ~/Downloads/Connections.csv --markdown --redact --out network-report.md
netlab analyze ~/Downloads/Connections.csv --json | jq '.companies.concentration'
```

---

## Getting your LinkedIn export

1. LinkedIn → **Me** → **Settings & Privacy**
2. **Data privacy** → **Get a copy of your data**
3. Select **Connections** (not the full archive — you only need this one file)
4. **Request archive**

Delivery takes 10 minutes to 24 hours. The archive contains `Connections.csv` with:
`First Name`, `Last Name`, `URL`, `Email Address`, `Company`, `Position`, `Connected On`.

The parser tolerates the variations LinkedIn actually emits: a variable-length `Notes:`
preamble, shifting column order, missing optional columns, locale-dependent date formats,
and Excel's cp1252 re-encoding (the classic `'charmap' codec can't decode byte 0x9d`
failure). Every anomaly is recorded in an ingest report rather than silently dropped.

---

## The analysis

### Employer concentration

Diversity measures borrowed from ecology, concentration measures from antitrust:

| Metric | Reading |
| --- | --- |
| **Gini coefficient** | 0 = evenly spread across employers, 1 = fully concentrated |
| **Normalized HHI** | Concentration, rescaled so it is comparable across networks of different sizes |
| **Shannon entropy `H`** | Raw diversity, in nats |
| **Pielou evenness** | `H / H_max` — is the distribution lumpy or flat? |
| **Effective employers** | `exp(H)`, the Hill number of order 1. *"You have 300 employers on paper but effectively 42 that matter."* |
| **Singleton rate** | Share of employers represented by one person — Granovetter's weak ties, structurally |
| **Power-law α** | Discrete MLE ([Clauset, Shalizi & Newman 2009](https://arxiv.org/abs/0706.1062)) with the `x_min − 0.5` correction. α < 2 indicates extreme hub dominance |

The gap between the raw employer count and the effective count is usually the most
surprising number in the report.

### Temporal dynamics

- **Dense monthly series** — zero-activity months are rendered, never collapsed.
- **Burst detection** via the Iglewicz–Hoaglin modified z-score (median/MAD). A mean-based
  z-score would be dragged around by the very bursts it is meant to find. `|z| > 3.5`
  flags a month; bursts usually map to a job change, a conference, or an onboarding cohort.
- **Accumulation half-life** — the date by which half your network existed, expressed as a
  fraction of the elapsed span. Front-loaded, linear, or back-loaded.
- **Duty cycle** — the share of months containing any new connection. Most networks are
  episodic, not continuous.
- **Velocity** — trailing-12 versus prior-12 months.

### Composition

Free-text titles are mapped onto two orthogonal axes by an ordered rule cascade:

- **Seniority** — an 8-step ordinal ladder from `student` through `founder_owner`. Order is
  load-bearing: *"VP of Engineering"* must resolve to `executive`, not `manager`.
- **Function** — 13 nominal domains (`data_ai`, `engineering`, `healthcare`, `legal`, …).

From those: leadership share, **functional homophily** (concentration in your modal
domain — the structural-hole trade-off), effective function count, and **seniority drift**,
an OLS regression of mean seniority rank on connection year. The R² is always reported
alongside the slope so a noisy fit is never read as a trend.

Rule-based rather than model-based, deliberately: deterministic output, zero inference
cost, fully auditable, and no data leaves the machine.

### Career eras

Non-parametric 1-D change detection. Sort by date, compute inter-arrival gaps, cut wherever
a gap exceeds `max(45 days, 3 × median gap)`, merge undersized fragments forward. No `k` to
choose — the cuts correspond to real dormancy rather than to an arbitrary cluster count.

Each era is labeled with its anchor employer, dominant function, mean seniority, and
**distinctive title terms** ranked by log-odds against the whole corpus. Log-odds rather
than raw frequency, because raw frequency just returns "engineer" for every segment of a
technologist's network.

### Findings

The insight engine is deterministic — rules over computed statistics, no language model, no
randomness. The same export always produces the same narrative, which is what makes the
output safe to drop into a scheduled pipeline. Each finding carries a confidence derived
from sample size or fit quality, and findings that would mislead at low `n` are suppressed
rather than hedged.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser  ·  static files, no build step, zero dependencies      │
│  ┌───────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────────┐  │
│  │ csv.js    │→ │analysis  │→ │ dock.js │  │ graph.js         │  │
│  │ (ingest)  │  │  .js     │  │ (panels)│  │ (force + canvas) │  │
│  └───────────┘  └──────────┘  └─────────┘  └──────────────────┘  │
│         ↑ fallback engine — always works, even offline           │
└─────────────────────────────────────────────────────────────────┘
                              │  optional: POST /api/analyze
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  netlab.api  ·  FastAPI, loopback, stateless, no egress          │
├─────────────────────────────────────────────────────────────────┤
│  netlab.core  ·  stdlib only — importable from a notebook,       │
│                  a CLI, a cron job, or an Azure Function         │
│                                                                   │
│   parsing → normalize → analytics → insights → report            │
│                              ↑                                    │
│                          metrics (pure functions)                │
└─────────────────────────────────────────────────────────────────┘
```

Three decisions worth calling out:

1. **The core has zero third-party dependencies.** `pip install netlab` pulls nothing. The
   web framework is an optional extra, so the analytics run anywhere Python runs — including
   locked-down environments where dependency review is a multi-week process.
2. **Two engines, one rule set.** The browser implementation mirrors the Python one so the
   tool still works with the server stopped. `tests/test_parity.py` executes the JavaScript
   modules under Node and diffs them against Python, so the two cannot silently drift.
3. **The Python service is an accelerator, never a dependency.** If `/api/health` does not
   answer, the UI degrades to the browser engine and labels the reduced sections honestly
   instead of hiding them.

---

## CLI reference

```
netlab serve   [--host HOST] [--port PORT] [--reload]
netlab analyze FILE [--json | --markdown | --summary] [--pretty] [--out PATH]
                    [--redact] [--cluster-by MODE] [--no-graph] [--title TITLE]
netlab sample  [--out PATH] [--count N] [--seed N]
```

| Flag | Effect |
| --- | --- |
| `--summary` | Human-readable digest of the top findings |
| `--markdown` | Full Markdown report artifact |
| `--json` | Complete analysis document (default) |
| `--redact` | Replace names with initials and strip profile URLs — use for anything shareable |
| `--cluster-by` | `company` · `year` · `function` · `seniority` · `none` |
| `--no-graph` | Omit the render payload; smaller, faster, no names |

Logs go to **stderr**, data to **stdout**, so pipelines compose cleanly:

```bash
netlab analyze Connections.csv --json \
  | jq '{effective: .companies.concentration.effective_companies,
         gini: .companies.concentration.gini,
         bursts: [.temporal.bursts[].month]}'
```

---

## HTTP API reference

Interactive docs at `http://127.0.0.1:8787/docs` once the server is running.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Version, schema version, and active privacy settings |
| `GET` | `/api/sample?count=600&seed=42` | Synthetic `Connections.csv`, generated in memory |
| `POST` | `/api/analyze` | Full analysis document. Form fields: `file`, `cluster_by`, `redact`, `include_graph` |
| `POST` | `/api/report` | Markdown report. Form fields: `file`, `redact` (defaults to `true`) |
| `GET` | `/` | The bundled UI |

```bash
curl -s -F "file=@Connections.csv" -F "redact=true" \
     http://127.0.0.1:8787/api/analyze | jq '.insights[0]'
```

Errors return `422` with `{ error, detail, correlation_id }`. Every response carries an
`x-correlation-id` header for tracing a single run end to end.

---

## Configuration

All settings are environment variables with restrictive defaults. Copy `.env.example` to
`.env` for reference; nothing is required to run.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NETLAB_HOST` | `127.0.0.1` | Bind address. Anything else logs a security warning at startup |
| `NETLAB_PORT` | `8787` | Listen port |
| `NETLAB_LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `NETLAB_LOG_JSON` | `false` | Single-line JSON records for a log collector |
| `NETLAB_REDACT` | `false` | Force redaction on every response |
| `NETLAB_ALLOW_PERSISTENCE` | `false` | Reserved; no code path writes analysis data to disk |
| `NETLAB_MAX_UPLOAD_MB` | `64` | Upload ceiling. A 30k-connection export is roughly 4 MB |
| `NETLAB_MAX_GRAPH_NODES` | `6000` | Render cap; the analysis still covers every row |
| `NETLAB_CORS_ORIGINS` | *(empty)* | Same-origin only, which is correct for the bundled UI |

---

## Privacy model

This tool processes a file containing the names, employers, and profile URLs of everyone
you know. The design treats that as the constraint it is:

- **No egress.** The server process never opens an outbound connection. There is no
  telemetry, no analytics SDK, no CDN, no font fetch, no update check. Verify it yourself
  with `lsof -i` or Wireshark while a run is in flight.
- **No persistence.** Uploaded bytes live in the request scope and are dropped when the
  response is written. No database, no cache, no temp file, nothing to purge.
- **Loopback by default.** Binding beyond `127.0.0.1` emits an explicit startup warning.
- **Logs carry counts, never contents.** Row counts, durations, and error classes only.
  Log files never become a shadow copy of your export.
- **No third-party JavaScript.** Three static files, no build step, no CDN. Nothing in the
  privacy path that you did not clone.
- **Redaction is first-class.** `--redact` replaces names with initials and strips URLs.
  The Markdown report redacts by default, because the report is the artifact people share.
- **Browser-only mode.** Stop the Python process entirely and the tool still works. The
  file never leaves the tab.

**Be considerate with the output.** Your connections did not consent to being analyzed.
Redact before sharing anything, and think twice before publishing employer-level
aggregates that identify individuals in small clusters.

---

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

netlab sample --out data/sample/Connections.csv --count 800   # synthetic fixture
netlab serve --reload                                          # auto-reload on save
```

Common tasks are wrapped in the `Makefile`:

```bash
make install    # editable install with dev extras
make sample     # regenerate the synthetic export
make dev        # serve with auto-reload
make test       # pytest with coverage
make lint       # ruff + mypy
make format     # ruff --fix
make report     # render a Markdown report from the sample
make clean
```

**Requirements:** Python 3.10+. Node.js is optional and used only by the parity test.

The front end has no build step by design — `src/netlab/web/` is served verbatim. Edit,
refresh, done. No bundler, no transpiler, no `node_modules` in the privacy path.

---

## Testing

```bash
make test                      # full suite with coverage
pytest tests/test_metrics.py   # one module
pytest -k parity -v            # cross-engine agreement only
```

| Suite | Covers |
| --- | --- |
| `test_parsing.py` | Notes preamble, cp1252 bytes, quoted commas, missing columns, date formats — each case is a real-world failure, not a hypothetical |
| `test_normalize.py` | Canonicalization cascade, ladder precedence (`VP of Engineering` → `executive`), idempotence |
| `test_metrics.py` | Estimators against closed-form values, not golden snapshots |
| `test_analytics.py` | Section shapes, invariants, determinism, degenerate inputs |
| `test_api.py` | HTTP contract, error envelopes, redaction, correlation IDs |
| `test_cli.py` | Exit codes, output modes, seeded reproducibility |
| `test_parity.py` | Runs the JS modules under Node and diffs against Python |

---

## Project layout

```
linkedin-network-lab/
├── src/netlab/
│   ├── core/                  # stdlib-only analytics — the reusable part
│   │   ├── models.py          # dataclasses, taxonomy constants, error types
│   │   ├── parsing.py         # tolerant CSV ingest + ParseReport
│   │   ├── normalize.py       # entity resolution, seniority + function rules
│   │   ├── metrics.py         # pure statistical primitives
│   │   ├── analytics.py       # the analysis sections
│   │   ├── insights.py        # deterministic narrative generation
│   │   ├── report.py          # Markdown rendering
│   │   └── pipeline.py        # single orchestration entry point
│   ├── web/                   # static UI — no build step
│   │   ├── index.html
│   │   ├── styles.css
│   │   ├── app.js             # controller; holds no statistics
│   │   └── lib/               # csv · analysis · graph · dock · api · format
│   ├── api.py                 # FastAPI app
│   ├── cli.py                 # argparse CLI
│   ├── config.py              # env-driven settings
│   ├── logging_setup.py       # text + JSON formatters
│   └── sampledata.py          # seeded synthetic generator
├── tests/
├── scripts/parity_check.mjs   # Node harness for the parity test
├── data/sample/               # generated, git-ignored
└── docs/ARCHITECTURE.md
```

---

## Limitations

Stated plainly, because the alternative is a tool that overclaims:

- **One hop only.** No second-degree structure exists in the file. Communities you might
  expect to see are not detectable here.
- **Titles are free text.** The rule cascade resolves roughly 80–90% of realistic titles.
  The remainder land in `unknown` / `unclassified`, and the classified rate is always shown.
- **Employers are a single string.** No industry, size, or geography, and no history — only
  the employer at export time. A connection who changed jobs appears under the new one.
- **`Connected On` is acquisition, not relationship.** It records when the tie was formed,
  never its strength or whether it stayed warm.
- **Entity resolution is conservative.** Deterministic rules only. `Acme` and `Acme Global
  Holdings` stay separate; fuzzy matching would merge them at the cost of reproducibility.
- **Co-occurrence is a hypothesis.** Two employers appearing in the same months suggests
  shared context. It does not establish it.
- **Small networks.** Below roughly 100 connections, concentration and drift statistics are
  unstable. The insight engine suppresses them rather than reporting noise.

---

## Roadmap

- [ ] Optional `Positions.csv` join for employer tenure and career-path edges
- [ ] Louvain community detection over the inferred employer graph
- [ ] Comparative mode — diff two exports to quantify network change over time
- [ ] Parquet export for downstream notebook work
- [ ] Configurable taxonomy via YAML, so non-tech networks can supply their own rules

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Two hard rules: **never commit a real
`Connections.csv`**, and any change to a classification rule must ship with a test case and
the matching edit to the JavaScript mirror.

---

## License

[MIT](LICENSE). Not affiliated with, endorsed by, or connected to LinkedIn Corporation.
