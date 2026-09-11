# Architecture

Design notes for anyone extending the project. The README covers usage; this covers why the
code is shaped the way it is.

## Layering

```
netlab.core        stdlib only, pure functions, no I/O beyond file reads
  ├── models       dataclasses, taxonomy constants, error hierarchy
  ├── parsing      bytes → Connection[] + ParseReport
  ├── normalize    entity resolution + title taxonomy (the enrichment pass)
  ├── metrics      statistical primitives — every function is total and pure
  ├── analytics    section builders over enriched connections
  ├── insights     rules over computed statistics → findings
  ├── report       analysis document → Markdown
  └── pipeline     the single orchestration entry point

netlab.api         FastAPI wrapper. Stateless, loopback, no egress.
netlab.cli         argparse wrapper. stdout = data, stderr = logs.
netlab.web         static UI. Mirrors the core rules in JavaScript.
```

**The dependency direction is strictly inward.** `api` and `cli` import `core`; `core`
imports nothing but the standard library. This is what lets the analytics run in a notebook,
a cron job, or a serverless function without dragging a web framework along.

## Why the core has no dependencies

Three reasons, in order of weight:

1. **Deployment reach.** Regulated environments treat every transitive dependency as review
   surface. A zero-dependency analytics package installs where a pandas-based one does not.
2. **Supply-chain surface.** This code handles a contact list. Every package in the import
   path is a party to that data.
3. **Startup cost.** `netlab analyze` completes a 600-connection export in roughly 20 ms.
   Importing pandas alone would cost an order of magnitude more than the analysis.

The trade is that `metrics.py` reimplements Gini, entropy, and OLS. All three are a handful
of lines, and each is tested against a closed-form value.

## The two-engine arrangement

The browser implements the same ingest and a subset of the same analytics. This is
duplication, and it is deliberate:

- The tool must work with the Python process stopped — that is the strongest form of the
  privacy claim.
- A user should never get different numbers depending on whether a background service
  happened to be running.

The drift risk is real, so `tests/test_parity.py` executes the JavaScript modules under Node
via `scripts/parity_check.mjs` and diffs 20 statistics against Python. Exact agreement is
required for counts, dates, and labels; 1e-3 tolerance for floating-point statistics.

Sections that are genuinely better in Python — era segmentation, power-law fitting, inferred
employer adjacency — are **not** approximated in the browser. They report
`available: false` with a pointer to `netlab serve`. Degrading honestly beats degrading
quietly.

## Data model

`Connection` carries both raw and derived fields. The raw fields are never mutated, so
enrichment is idempotent and re-runnable with a changed rule set — which matters because the
taxonomy is the part most likely to be edited.

`ParseReport` is a first-class output, not a log line. Every metric inherits the ingest
ceiling, so completeness is rendered in the UI rather than buried.

## Performance

| Concern | Approach |
| --- | --- |
| One-mode projection | Computed in closed form. Materializing it is `O(Σk²)` edges for zero informational gain, since the projection is a disjoint union of cliques |
| Force-layout repulsion | Uniform spatial hash, 3×3 neighborhood only. Naive pairwise is `O(n²)` per frame and stalls above ~1,500 nodes |
| Layout convergence | Simulated annealing with a freeze at `alpha < 0.008`. An idle tab costs nothing; interaction reheats |
| Hit testing | Reuses the layout grid — `O(1)` picking instead of a full scan |
| Render cap | `NETLAB_MAX_GRAPH_NODES` caps *rendering* only. The analysis always covers every row |

Measured: 600 connections analyze in ~20 ms; 10,000 in well under a second.

## Determinism

No randomness, no wall-clock dependence, and no model calls in the analysis path:

- Insights are rules over statistics, not generated text.
- Entity resolution is a rule cascade, not fuzzy matching.
- Graph layout seeds from a deterministic hash of the node index, so the same export lays
  out identically every time.
- The synthetic generator is seeded.

`TestDeterminism::test_repeat_runs_are_identical` asserts byte-identical documents across
runs. This is the property that makes the output safe to commit as an artifact or schedule
in a pipeline.

## Error handling

`NetlabError` → `ParseError` is the only user-facing hierarchy. The API maps it to `422`
with `{error, detail, correlation_id}`; the CLI maps it to exit code 1. Unexpected
exceptions are deliberately not caught — a stack trace is more useful than a swallowed bug.

Parse failures are downgraded to report warnings wherever a partial result still has value.
A missing `Company` column disables employer metrics; it does not fail the run.

## Extension points

- **Taxonomy** — `_SENIORITY_RULES` and `_FUNCTION_RULES` in `normalize.py`, mirrored in
  `web/lib/csv.js`. Order is load-bearing: first match wins.
- **Sections** — add a builder to `analytics.py`, register it in `pipeline.py`, render it in
  `web/lib/dock.js`.
- **Insights** — add a rule function to `insights.py` and include it in `generate()`.
  Always include a suppression threshold.
- **Output formats** — `report.py` is the template for a new renderer. Consume the analysis
  document; never reach back into `Connection` objects.

## Deliberate non-goals

- **No LinkedIn API integration.** It would require OAuth, a server round trip, and terms
  acceptance — and would break every privacy property above.
- **No second-degree inference.** The data is not there. Inventing it is the specific
  failure mode this project exists to avoid.
- **No account required, no hosted version.** A hosted deployment would mean uploading
  contact lists to someone else's machine, which is the problem, not the product.
