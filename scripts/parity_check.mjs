/**
 * Cross-engine parity harness.
 *
 * Runs the browser ingest + analytics modules under Node against a CSV path and prints a
 * comparable summary as JSON. `tests/test_parity.py` diffs this against the Python engine
 * so the two implementations cannot silently drift.
 *
 * Usage: node scripts/parity_check.mjs path/to/Connections.csv
 */

import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const webDir = new URL('../src/netlab/web/lib/', import.meta.url);
const { parseConnections } = await import(new URL('csv.js', webDir));
const { analyze } = await import(new URL('analysis.js', webDir));

// The browser analytics module measures its own runtime; Node has performance globally.
const path = process.argv[2];
if (!path) {
  console.error('usage: node scripts/parity_check.mjs <Connections.csv>');
  process.exit(2);
}

const text = readFileSync(path, 'utf8');
const { people, report } = parseConnections(text);
const doc = analyze(people, report);

process.stdout.write(JSON.stringify({
  connections: doc.overview.connections,
  distinct_companies: doc.overview.distinct_companies,
  with_company: doc.overview.with_company,
  with_position: doc.overview.with_position,
  with_date: doc.overview.with_date,
  first_connection: doc.overview.first_connection,
  last_connection: doc.overview.last_connection,
  gini: doc.companies.concentration.gini,
  hhi: doc.companies.concentration.hhi_normalized,
  entropy: doc.companies.concentration.shannon_entropy,
  effective_companies: doc.companies.concentration.effective_companies,
  singleton_rate: doc.companies.concentration.singleton_rate,
  total_months: doc.temporal.total_months,
  active_months: doc.temporal.active_months,
  burst_months: doc.temporal.bursts.length,
  half_life: doc.temporal.accumulation_half_life,
  mean_seniority_rank: doc.composition.seniority.mean_rank,
  modal_function: doc.composition.function.modal,
  projection_edges: doc.structure.projection.edges,
  merged_companies: doc.data_quality.entity_resolution.merged,
  top_companies: doc.companies.largest.slice(0, 5).map((e) => [e.company, e.count]),
}, null, 2));
