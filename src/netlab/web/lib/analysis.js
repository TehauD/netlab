/**
 * Browser fallback analytics.
 *
 * Emits the same document shape as `netlab.core.pipeline.analyze` so the dock renders
 * identically regardless of engine. Sections that are expensive or genuinely better in
 * Python — era segmentation, power-law fitting, inferred employer adjacency — are marked
 * unavailable here with an explicit pointer to the local engine rather than approximated
 * badly.
 */

import { SENIORITY_LADDER } from './csv.js';

export const SCHEMA_VERSION = '1.0.0';

// ---------- statistical primitives (ports of netlab.core.metrics) ----------

const round = (v, d = 4) => Math.round(v * 10 ** d) / 10 ** d;

export function gini(values) {
  const v = values.filter((x) => x >= 0).sort((a, b) => a - b);
  const total = v.reduce((a, b) => a + b, 0);
  if (!v.length || total === 0) return 0;
  const cum = v.reduce((acc, x, i) => acc + (i + 1) * x, 0);
  return round((2 * cum) / (v.length * total) - (v.length + 1) / v.length);
}

export function hhi(values) {
  const v = values.filter((x) => x > 0);
  const n = v.length;
  if (n <= 1) return n === 1 ? 1 : 0;
  const total = v.reduce((a, b) => a + b, 0);
  const raw = v.reduce((acc, x) => acc + (x / total) ** 2, 0);
  return round(Math.max((raw - 1 / n) / (1 - 1 / n), 0));
}

export function entropy(values) {
  const v = values.filter((x) => x > 0);
  const total = v.reduce((a, b) => a + b, 0);
  if (total <= 0 || v.length <= 1) return 0;
  return round(-v.reduce((acc, x) => acc + (x / total) * Math.log(x / total), 0));
}

export const evenness = (values) => {
  const v = values.filter((x) => x > 0);
  return v.length <= 1 ? 0 : round(entropy(v) / Math.log(v.length));
};

export const effectiveCount = (values) =>
  values.length ? round(Math.exp(entropy(values)), 2) : 0;

export function topKShare(values, k = 10) {
  const v = [...values].sort((a, b) => b - a);
  const total = v.reduce((a, b) => a + b, 0);
  return total ? round(v.slice(0, k).reduce((a, b) => a + b, 0) / total) : 0;
}

export function median(values) {
  const v = [...values].sort((a, b) => a - b);
  if (!v.length) return 0;
  const mid = v.length >> 1;
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

/** Iglewicz–Hoaglin modified z-scores: outlier-resistant burst detection. */
export function modifiedZ(values) {
  if (!values.length) return [];
  const m = median(values);
  const dev = median(values.map((x) => Math.abs(x - m)));
  if (dev === 0) {
    const meanAbs = values.reduce((a, x) => a + Math.abs(x - m), 0) / values.length;
    return meanAbs === 0 ? values.map(() => 0) : values.map((x) => round(0.7979 * (x - m) / meanAbs, 3));
  }
  return values.map((x) => round((0.6745 * (x - m)) / dev, 3));
}

export function olsSlope(xs, ys) {
  const n = Math.min(xs.length, ys.length);
  if (n < 2) return [0, 0, 0];
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0);
  if (sxx === 0) return [0, my, 0];
  const sxy = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0);
  const syy = ys.reduce((a, y) => a + (y - my) ** 2, 0);
  return [round(sxy / sxx), round(my - (sxy / sxx) * mx), syy ? round(sxy ** 2 / (sxx * syy)) : 0];
}

// ---------- section builders ----------

const share = (part, whole) => (whole ? round(part / whole) : 0);
const monthKey = (d) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;

function countBy(items, keyFn) {
  const map = new Map();
  for (const item of items) {
    const k = keyFn(item);
    if (k === '' || k === null || k === undefined) continue;
    map.set(k, (map.get(k) || 0) + 1);
  }
  return map;
}

function buildOverview(people) {
  const dated = people.filter((p) => p.connectedOn).sort((a, b) => a.connectedOn - b.connectedOn);
  const companies = people.filter((p) => p.company);
  return {
    connections: people.length,
    distinct_companies: new Set(companies.map((p) => p.company)).size,
    with_company: companies.length,
    with_position: people.filter((p) => p.position).length,
    with_date: dated.length,
    first_connection: dated.length ? dated[0].connected_on : null,
    last_connection: dated.length ? dated[dated.length - 1].connected_on : null,
    span_days: dated.length > 1
      ? Math.round((dated[dated.length - 1].connectedOn - dated[0].connectedOn) / 86400000)
      : 0,
  };
}

function buildCompanies(people) {
  const counts = countBy(people, (p) => p.company);
  if (!counts.size) return { available: false, reason: 'No employer values present in this export.' };
  const sizes = [...counts.values()];
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  return {
    available: true,
    distinct: counts.size,
    largest: sorted.slice(0, 25).map(([company, count]) => ({ company, count })),
    concentration: {
      gini: gini(sizes),
      hhi_normalized: hhi(sizes),
      shannon_entropy: entropy(sizes),
      pielou_evenness: evenness(sizes),
      effective_companies: effectiveCount(sizes),
      top_10_share: topKShare(sizes, 10),
      singleton_rate: share(sizes.filter((s) => s === 1).length, counts.size),
      powerlaw_alpha: null,
      tail_regime: 'requires_local_engine',
    },
    median_cluster_size: median(sizes),
  };
}

function buildTemporal(people) {
  const dated = people.filter((p) => p.connectedOn).sort((a, b) => a.connectedOn - b.connectedOn);
  if (dated.length < 2) return { available: false, reason: 'Fewer than two parseable dates.' };

  const first = dated[0].connectedOn;
  const last = dated[dated.length - 1].connectedOn;
  const counts = countBy(dated, (p) => monthKey(p.connectedOn));

  const series = [];
  const cursor = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), 1));
  const end = new Date(Date.UTC(last.getUTCFullYear(), last.getUTCMonth(), 1));
  while (cursor <= end) {
    const key = monthKey(cursor);
    series.push({ month: key, count: counts.get(key) || 0 });
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }

  const values = series.map((s) => s.count);
  const zs = modifiedZ(values);
  const bursts = series
    .map((s, i) => ({ ...s, z: zs[i] }))
    .filter((s) => s.z >= 3.5);

  let running = 0, halfLife = null;
  for (const p of dated) {
    running++;
    if (running >= dated.length / 2) { halfLife = p.connected_on; break; }
  }

  const yearCounts = countBy(dated, (p) => p.connectedOn.getUTCFullYear());
  const yearMs = 365 * 86400000;
  const trailing = dated.filter((p) => last - p.connectedOn <= yearMs).length;
  const prior = dated.filter((p) => last - p.connectedOn > yearMs && last - p.connectedOn <= 2 * yearMs).length;
  const pctChange = prior ? round((trailing - prior) / prior) : null;

  let dormancy = null;
  for (let i = 1; i < dated.length; i++) {
    const days = Math.round((dated[i].connectedOn - dated[i - 1].connectedOn) / 86400000);
    if (!dormancy || days > dormancy.days) {
      dormancy = { days, from: dated[i - 1].connected_on, to: dated[i].connected_on };
    }
  }

  const spanDays = Math.max((last - first) / 86400000, 1);
  const halfDays = halfLife ? (new Date(`${halfLife}T00:00:00Z`) - first) / 86400000 : null;

  return {
    available: true,
    monthly: series,
    yearly: [...yearCounts.entries()].sort((a, b) => a[0] - b[0]).map(([year, count]) => ({ year, count })),
    active_months: values.filter((v) => v > 0).length,
    total_months: values.length,
    duty_cycle: share(values.filter((v) => v > 0).length, values.length),
    median_month: median(values),
    peak_month: series.reduce((a, b) => (b.count > a.count ? b : a), series[0]),
    bursts,
    burst_share_of_volume: share(bursts.reduce((a, b) => a + b.count, 0), dated.length),
    accumulation_half_life: halfLife,
    half_life_elapsed_fraction: halfDays === null ? null : round(halfDays / spanDays),
    longest_dormancy: dormancy,
    velocity: {
      trailing_12m: trailing,
      prior_12m: prior,
      pct_change: pctChange,
      direction: pctChange === null ? 'unknown'
        : pctChange > 0.1 ? 'expanding' : pctChange < -0.1 ? 'contracting' : 'steady',
    },
  };
}

function buildComposition(people) {
  const seniorityCounts = countBy(people, (p) => p.seniority);
  const functionCounts = countBy(people, (p) => p.function);
  const classified = people.filter((p) => p.seniority !== 'unknown');

  const known = new Map([...functionCounts].filter(([k]) => k !== 'unclassified'));
  const knownValues = [...known.values()];
  const modal = knownValues.length
    ? [...known.entries()].sort((a, b) => b[1] - a[1])[0][0]
    : null;

  const byYear = new Map();
  for (const p of classified) {
    if (!p.connectedOn) continue;
    const y = p.connectedOn.getUTCFullYear();
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y).push(p.seniority_rank);
  }
  const points = [...byYear.entries()]
    .filter(([, v]) => v.length >= 3)
    .sort((a, b) => a[0] - b[0])
    .map(([year, v]) => ({ year, mean_rank: round(v.reduce((a, b) => a + b, 0) / v.length, 3), n: v.length }));

  let drift = { available: false, reason: 'Fewer than three years with sufficient data.', by_year: points };
  if (points.length >= 3) {
    const [slope, intercept, r2] = olsSlope(points.map((p) => p.year), points.map((p) => p.mean_rank));
    drift = {
      available: true, by_year: points, slope_rank_per_year: slope, intercept, r_squared: r2,
      interpretation: slope > 0.02 && r2 > 0.3 ? 'rising'
        : slope < -0.02 && r2 > 0.3 ? 'falling' : 'flat',
    };
  }

  const leadership = people.filter((p) =>
    ['manager', 'director', 'executive', 'founder_owner'].includes(p.seniority)).length;

  return {
    seniority: {
      distribution: SENIORITY_LADDER.map((tier, rank) => ({
        tier, rank, count: seniorityCounts.get(tier) || 0,
      })),
      classified_rate: share(classified.length, people.length),
      mean_rank: classified.length
        ? round(classified.reduce((a, p) => a + p.seniority_rank, 0) / classified.length, 3) : 0,
      leadership_share: share(leadership, Math.max(classified.length, 1)),
      drift,
    },
    function: {
      distribution: [...functionCounts.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([fn, count]) => ({ function: fn, count })),
      entropy: entropy(knownValues),
      evenness: evenness(knownValues),
      effective_functions: effectiveCount(knownValues),
      modal,
      homophily_index: modal ? share(known.get(modal), knownValues.reduce((a, b) => a + b, 0)) : null,
    },
  };
}

function buildStructure(people) {
  const counts = countBy(people, (p) => p.company);
  const sizes = [...counts.values()];
  const n = people.length;
  const affiliations = sizes.reduce((a, b) => a + b, 0);
  const edges = sizes.reduce((a, k) => a + (k * (k - 1)) / 2, 0);
  const degreeSum = sizes.reduce((a, k) => a + k * (k - 1), 0);
  const possible = n > 1 ? (n * (n - 1)) / 2 : 0;

  return {
    bipartite: {
      people: n,
      companies: counts.size,
      edges: affiliations,
      density: n && counts.size ? round(affiliations / (n * counts.size), 6) : 0,
      unaffiliated_people: n - affiliations,
    },
    projection: {
      note: 'Disjoint union of cliques — each person has exactly one employer in the export, '
          + 'so components are companies by construction. Reported for completeness, not as '
          + 'discovered structure.',
      edges,
      mean_degree: n ? round(degreeSum / n, 3) : 0,
      max_degree: sizes.length ? Math.max(...sizes) - 1 : 0,
      density: possible ? round(edges / possible, 6) : 0,
      components: counts.size + (n - affiliations),
      largest_component_share: sizes.length ? share(Math.max(...sizes), n) : 0,
      isolate_share: share((n - affiliations) + sizes.filter((s) => s === 1).length, n),
    },
    company_cooccurrence: {
      available: false,
      reason: 'Inferred employer adjacency requires the local Python engine (netlab serve).',
    },
  };
}

// ---------- insights (subset of the Python rule set) ----------

const pct = (v) => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(1)}%`);

function buildInsights(doc) {
  const out = [];
  const n = doc.overview.connections;
  const c = doc.companies.available ? doc.companies.concentration : null;

  if (c) {
    out.push({
      title: 'Your network is narrower than the headline count suggests',
      detail: `${doc.companies.distinct.toLocaleString()} distinct employers appear, but the `
        + `entropy-adjusted effective count is ${Math.round(c.effective_companies)}. The top 10 `
        + `hold ${pct(c.top_10_share)} of all affiliations (Gini ${c.gini.toFixed(2)}).`,
      kind: 'concentration', confidence: n >= 150 ? 'high' : 'medium', evidence: c,
    });
    if (c.singleton_rate >= 0.5) {
      out.push({
        title: 'Half your employer graph is single-person outposts',
        detail: `${pct(c.singleton_rate)} of employers are represented by exactly one connection. `
          + 'These are weak-tie bridges: they carry the non-redundant information your dense '
          + 'clusters cannot.',
        kind: 'structure', confidence: 'high', evidence: c,
      });
    }
  }

  const t = doc.temporal;
  if (t.available) {
    if (t.bursts.length) {
      const top = t.bursts.reduce((a, b) => (b.count > a.count ? b : a));
      out.push({
        title: `${t.bursts.length} statistically anomalous networking months`,
        detail: `Months above a 3.5 modified z-score carry ${pct(t.burst_share_of_volume)} of all `
          + `connections. The largest was ${top.month} with ${top.count} (z = ${top.z}). Bursts of `
          + 'this shape usually map to a job change, a conference, or an onboarding cohort.',
        kind: 'temporal', confidence: 'high', evidence: { bursts: t.bursts.slice(0, 5) },
      });
    }
    if (t.half_life_elapsed_fraction !== null) {
      const f = t.half_life_elapsed_fraction;
      const shape = f <= 0.35 ? 'front-loaded' : f >= 0.65 ? 'back-loaded' : 'roughly linear';
      out.push({
        title: `Network accumulation is ${shape}`,
        detail: `Half of all connections existed by ${t.accumulation_half_life}, which is `
          + `${pct(f)} of the way through the span.`,
        kind: 'temporal', confidence: 'high', evidence: { half_life: t.accumulation_half_life },
      });
    }
    if (t.duty_cycle < 0.5) {
      out.push({
        title: 'Networking is episodic, not continuous',
        detail: `Only ${pct(t.duty_cycle)} of months contain any new connection `
          + `(${t.active_months} of ${t.total_months}). Longest dormant stretch: `
          + `${t.longest_dormancy?.days ?? '—'} days.`,
        kind: 'temporal', confidence: 'high', evidence: { duty_cycle: t.duty_cycle },
      });
    }
  }

  const fn = doc.composition.function;
  if (fn.modal) {
    out.push({
      title: `Functional homophily: ${pct(fn.homophily_index)} in ${fn.modal.replace(/_/g, ' ')}`,
      detail: `Functional diversity is ${fn.evenness.toFixed(2)} on the Pielou evenness scale `
        + `(${fn.effective_functions.toFixed(1)} effective functions). High homophily means deep `
        + 'domain access and thin cross-domain reach.',
      kind: 'composition', confidence: n >= 150 ? 'high' : 'medium', evidence: fn,
    });
  }

  out.push({
    title: 'The one-hop export ceiling',
    detail: `The person-to-person projection resolves to ${doc.structure.projection.components} `
      + 'disjoint cliques, because each person carries exactly one employer. Genuine '
      + 'second-degree topology is not present in this file — any tool showing it is inventing edges.',
    kind: 'methodology', confidence: 'high', evidence: doc.structure.projection,
  });

  const order = { high: 0, medium: 1, low: 2 };
  return out.sort((a, b) => order[a.confidence] - order[b.confidence]);
}

/**
 * Build the render payload: a bipartite people/hub graph.
 * Mirrors `netlab.core.analytics.graph_payload` so both engines feed the same renderer.
 */
export function graphPayload(people, clusterBy = 'company', redact = false, maxNodes = 6000) {
  const subset = people.slice(0, maxNodes);
  const nodes = subset.map((p, id) => ({
    id,
    kind: 'person',
    label: redact ? p.initials : p.name,
    company: p.company,
    position: p.position,
    connected_on: p.connected_on,
    seniority: p.seniority,
    seniority_rank: p.seniority_rank,
    function: p.function,
    url: redact ? '' : p.url,
  }));
  const edges = [];

  const keyFor = (p) => {
    if (clusterBy === 'company') return p.company;
    if (clusterBy === 'year') return p.connectedOn ? String(p.connectedOn.getUTCFullYear()) : 'Undated';
    if (clusterBy === 'function') return p.function;
    if (clusterBy === 'seniority') return p.seniority;
    return '';
  };

  if (clusterBy !== 'none') {
    const hubIndex = new Map();
    const members = new Map();
    let nextId = nodes.length;
    subset.forEach((p, i) => {
      const key = keyFor(p);
      if (!key) return;
      if (!hubIndex.has(key)) {
        hubIndex.set(key, nextId);
        nodes.push({ id: nextId, kind: 'hub', label: key, members: 0, sample: [] });
        members.set(nextId, []);
        nextId++;
      }
      const hid = hubIndex.get(key);
      members.get(hid).push(nodes[i].label);
      edges.push([i, hid]);
    });
    for (const [hid, list] of members) {
      const node = nodes.find((n) => n.id === hid);
      node.members = list.length;
      node.sample = list.slice(0, 60);
    }
  }

  return {
    cluster_by: clusterBy,
    redacted: redact,
    truncated: people.length > subset.length,
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
  };
}

/** Assemble the full analysis document from enriched people records. */
export function analyze(people, report) {
  const started = performance.now();
  const doc = {
    schema_version: SCHEMA_VERSION,
    engine: 'browser',
    overview: buildOverview(people),
    data_quality: {
      ingest: report,
      entity_resolution: {
        raw_distinct: new Set(people.map((p) => p.companyRaw).filter(Boolean)).size,
        canonical_distinct: new Set(people.map((p) => p.company).filter(Boolean)).size,
        merged: 0,
      },
    },
    companies: buildCompanies(people),
    temporal: buildTemporal(people),
    composition: buildComposition(people),
    structure: buildStructure(people),
    eras: { available: false, reason: 'Era segmentation requires the local Python engine (netlab serve).' },
  };
  const er = doc.data_quality.entity_resolution;
  er.merged = Math.max(er.raw_distinct - er.canonical_distinct, 0);
  doc.data_quality.resolution_merge_rate = share(er.merged, Math.max(er.raw_distinct, 1));
  doc.insights = buildInsights(doc);
  doc.runtime_ms = round(performance.now() - started, 2);
  return doc;
}
