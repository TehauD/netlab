# Contributing

Thanks for taking an interest. This project has a narrow scope and two non-negotiable
rules; everything else is negotiable.

## The two hard rules

1. **Never commit a real `Connections.csv`.** It contains other people's names, employers,
   and profile URLs. `.gitignore` blocks `data/` and `*.csv`, and CI fails the build if an
   export file is ever tracked. Use `make sample` for fixtures.
2. **Rule changes ship in pairs.** The seniority and function taxonomies exist in both
   `src/netlab/core/normalize.py` and `src/netlab/web/lib/csv.js`. Changing one without the
   other breaks `tests/test_parity.py`, which is exactly what it is there to catch.

## Getting set up

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make sample
make test
```

Node.js is optional — it powers only the cross-engine parity test, which skips cleanly when
Node is unavailable.

## Before you open a PR

```bash
make format     # ruff --fix
make lint       # ruff + mypy
make test       # pytest with coverage
```

Coverage must stay at or above 80%.

## Design commitments

These are not preferences; changes that violate them will be declined.

- **The core stays dependency-free.** `netlab.core` imports from the standard library only.
  Anything needing a third-party package belongs in `api.py` or behind an optional extra.
- **No egress, ever.** No telemetry, no analytics SDK, no CDN, no font fetch, no update
  check. The privacy claim in the README must remain verifiable with `lsof -i`.
- **No persistence by default.** Uploaded bytes live in the request scope and die with it.
- **Deterministic output.** Same input, same output — no randomness, no wall-clock
  dependence, no model calls in the analysis path. This is what makes the tool safe to
  schedule.
- **No build step for the front end.** `src/netlab/web/` is served verbatim. No bundler, no
  transpiler, no `node_modules` in the privacy path.
- **Honest labeling.** Anything inferred must be labeled inferred. We do not draw edges that
  are not in the data, and we do not present a model of the data as a fact about it.

## Adding an analysis

1. Put pure statistical helpers in `core/metrics.py` with a docstring naming the estimator
   and its source.
2. Add the section builder to `core/analytics.py` and register it in `core/pipeline.py`.
3. Add matching rules to `core/insights.py` — including a suppression threshold, so the
   finding stays silent when `n` is too small to support it.
4. Render it in `web/lib/dock.js`.
5. Test the estimator against a closed-form value, not a golden snapshot.

## Commit style

Conventional commits, informally enforced:

```
feat(analytics): add Louvain communities over the inferred employer graph
fix(parsing): tolerate a BOM in Excel-resaved exports
docs(readme): clarify the one-hop limitation
test(parity): cover the seniority ladder edge cases
```

## Reporting a bug

Include the Python version, the OS, the command or endpoint, and the **structure** of the
failing input — column names, row count, a synthetic row that reproduces it. Please do not
attach your real export.

## Security

For anything that could expose user data, open a private security advisory rather than a
public issue.
