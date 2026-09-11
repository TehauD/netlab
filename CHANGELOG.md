# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-09-11

First production release. Promotes the single-file prototype into a packaged,
tested, documented tool.

### Added

- **Python analytics core** (`netlab.core`) — dependency-free, importable from a notebook,
  a CLI, or a serverless function.
- **Employer concentration** — Gini, normalized HHI, Shannon entropy, Pielou evenness,
  effective employer count (Hill order 1), top-k share, singleton rate, and a discrete
  power-law MLE with tail-regime classification.
- **Temporal dynamics** — dense monthly series, burst detection via modified z-score,
  accumulation half-life, duty cycle, longest dormancy, trailing-12 velocity.
- **Composition** — an 8-step ordinal seniority ladder and 13 functional domains derived
  from free-text titles, plus leadership share, functional homophily, and an OLS seniority
  drift regression reported with its R².
- **Career-era segmentation** — non-parametric gap-based change detection with log-odds
  distinctive-term extraction per era.
- **Inferred employer adjacency** — a company-to-company graph built from monthly
  co-occurrence, with union-find components and bridge ranking. Explicitly labeled inferred.
- **Deterministic insight engine** — rule-derived findings with confidence levels and
  low-`n` suppression. No model calls in the analysis path.
- **Entity resolution** — a deterministic canonicalization cascade for employer names, with
  a merge-rate report quantifying what it bought.
- **FastAPI local service** — `/api/health`, `/api/analyze`, `/api/report`, `/api/sample`,
  OpenAPI docs, correlation IDs, and a structured error envelope.
- **CLI** — `serve`, `analyze`, and `sample`, with JSON, Markdown, and summary output modes.
- **Redaction mode** — names to initials, URLs stripped. Default-on for the Markdown report.
- **Seeded synthetic generator** — plants a Zipf employer distribution, three eras, hiring
  bursts, seniority drift, and deliberate dirt, so the repo is demonstrable without real data.
- **Test suite** — 79 tests across ingest, taxonomy, estimators, sections, HTTP contract,
  CLI, and cross-engine parity.
- **CI** — 3 operating systems × 3 Python versions, lint, type-check, wheel verification,
  and a guard that fails the build if a connections export is ever committed.

### Changed

- **Ingest hardened** — Notes-preamble detection, alias-based column mapping, a four-codec
  decode ladder (fixes the `'charmap' codec can't decode byte 0x9d` failure on
  Excel-resaved exports), explicit multi-format date parsing, and a `ParseReport` surfaced
  in the UI.
- **Front end restructured** — the inline single-file prototype is now HTML, CSS, and six ES
  modules with no build step and no third-party JavaScript.
- **Force layout rewritten** — spatial-hash repulsion replaces the `O(n²)` pairwise loop,
  with simulated annealing and a freeze so an idle tab costs nothing. Hit testing reuses the
  same grid.
- **Clustering extended** — employer, year, function, seniority, or none.
- **Logs moved to stderr** — stdout stays a clean data channel for shell pipelines.

### Security

- Loopback binding by default, with an explicit startup warning when overridden.
- Stateless request handling: no database, no cache, no temp file.
- No outbound network calls from any code path.
- Logs record counts, durations, and error classes — never connection contents.
- Upload ceiling and graph-node caps to bound resource use.

[1.0.0]: https://github.com/your-org/linkedin-network-lab/releases/tag/v1.0.0
