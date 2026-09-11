/**
 * Analysis dock rendering.
 *
 * Each tab is a pure function from the analysis document to an HTML string. No state, no
 * DOM diffing — the document is small and tab switches are infrequent, so a full re-render
 * is simpler and fast enough. Every value that originates in the CSV is escaped.
 */

import { esc, pct, fixed, num, titleCase, monthLabel, dateLabel } from './format.js';

const unavailable = (reason) =>
  `<p class="empty-note">${esc(reason || 'Not available for this export.')}</p>`;

// ---------- shared partials ----------

function barList(items, { max, warm = false } = {}) {
  const ceiling = max ?? Math.max(...items.map((i) => i.value), 1);
  return items.map((item) => `
    <div class="bar-row">
      <span class="label" title="${esc(item.label)}">${esc(item.label)}</span>
      <span class="track"><span class="fill${warm ? ' warm' : ''}"
        style="width:${Math.max((item.value / ceiling) * 100, 1.5)}%"></span></span>
      <span class="value">${esc(item.display ?? num(item.value))}</span>
    </div>`).join('');
}

function kvTable(rows, headers = ['Statistic', 'Value']) {
  return `
    <table class="kv">
      <thead><tr><th>${esc(headers[0])}</th><th style="text-align:right">${esc(headers[1])}</th></tr></thead>
      <tbody>${rows.map(([k, v, title]) => `
        <tr><td${title ? ` title="${esc(title)}"` : ''}>${esc(k)}</td>
        <td class="num">${esc(v)}</td></tr>`).join('')}
      </tbody>
    </table>`;
}

/**
 * Inline SVG sparkline. Chosen over a charting library because the entire UI ships as
 * three static files with no build step and no third-party code in the privacy path.
 */
function sparkline(series, { height = 96, highlight = [] } = {}) {
  if (!series.length) return '';
  const width = 360;
  const max = Math.max(...series.map((p) => p.count), 1);
  const step = width / Math.max(series.length - 1, 1);
  const y = (v) => height - 14 - (v / max) * (height - 26);

  const line = series.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${y(p.count).toFixed(1)}`).join(' ');
  const area = `${line} L${width},${height - 14} L0,${height - 14} Z`;
  const flagged = new Set(highlight);

  const marks = series.map((p, i) => (flagged.has(p.month)
    ? `<circle cx="${(i * step).toFixed(1)}" cy="${y(p.count).toFixed(1)}" r="2.6" fill="#c98a4b"><title>${esc(monthLabel(p.month))}: ${p.count}</title></circle>`
    : '')).join('');

  const first = series[0].month;
  const last = series[series.length - 1].month;

  return `
    <svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img"
         aria-label="Connections per month">
      <path d="${area}" fill="rgba(123,159,212,0.12)"></path>
      <path d="${line}" fill="none" stroke="#7b9fd4" stroke-width="1.4"></path>
      ${marks}
      <text x="0" y="${height - 2}" fill="#6a6a64" font-size="9">${esc(monthLabel(first))}</text>
      <text x="${width}" y="${height - 2}" fill="#6a6a64" font-size="9" text-anchor="end">${esc(monthLabel(last))}</text>
      <text x="0" y="10" fill="#6a6a64" font-size="9">peak ${max}/mo</text>
    </svg>`;
}

// ---------- tabs ----------

const TABS = {
  insights(doc) {
    const items = doc.insights || [];
    if (!items.length) return unavailable('No findings met the reporting threshold.');
    return `
      <h3 class="section-title">Findings</h3>
      <p class="section-sub">Rule-derived, deterministic — the same export always yields the same
      findings. Confidence reflects sample size and fit quality, not certainty.</p>
      ${items.map((i) => `
        <article class="card">
          <div class="meta">
            <span class="tag ${esc(i.confidence)}">${esc(i.confidence)}</span>
            <span class="tag kind">${esc(titleCase(i.kind))}</span>
          </div>
          <h4>${esc(i.title)}</h4>
          <p>${esc(i.detail)}</p>
        </article>`).join('')}`;
  },

  concentration(doc) {
    const c = doc.companies;
    if (!c.available) return unavailable(c.reason);
    const k = c.concentration;
    return `
      <h3 class="section-title">Employer concentration</h3>
      <p class="section-sub">How evenly your network spreads across employers. Measures borrowed
      from ecology (diversity) and antitrust (concentration).</p>
      ${kvTable([
        ['Distinct employers', num(c.distinct)],
        ['Effective employers', num(k.effective_companies, 0), 'exp(Shannon entropy) — Hill number of order 1'],
        ['Gini coefficient', fixed(k.gini, 3), '0 = perfectly even, 1 = fully concentrated'],
        ['Normalized HHI', fixed(k.hhi_normalized, 3), 'Size-independent concentration'],
        ['Pielou evenness', fixed(k.pielou_evenness, 3), 'H / H-max'],
        ['Top-10 share', pct(k.top_10_share)],
        ['Singleton rate', pct(k.singleton_rate), 'Employers represented by exactly one person'],
        ['Power-law alpha', k.powerlaw_alpha ?? '—', 'Discrete MLE, Clauset et al.'],
        ['Tail regime', titleCase(k.tail_regime)],
      ])}
      <h4 style="margin:1.1rem 0 .5rem;font-size:.72rem;color:#9a9a92;text-transform:uppercase;letter-spacing:.06em">Largest clusters</h4>
      ${barList(c.largest.slice(0, 14).map((e) => ({ label: e.company, value: e.count })), { warm: true })}
      <p class="note">The gap between distinct and effective employer counts is the headline:
      a long tail of one-off affiliations inflates the raw count without adding structural weight.</p>`;
  },

  timeline(doc) {
    const t = doc.temporal;
    if (!t.available) return unavailable(t.reason);
    const v = t.velocity;
    return `
      <h3 class="section-title">Temporal dynamics</h3>
      <p class="section-sub">Connections per month across the full span. Amber markers flag burst
      months — a modified z-score above 3.5 against the median.</p>
      ${sparkline(t.monthly, { highlight: t.bursts.map((b) => b.month) })}
      ${kvTable([
        ['Active months', `${num(t.active_months)} / ${num(t.total_months)}`],
        ['Duty cycle', pct(t.duty_cycle), 'Share of months with any new connection'],
        ['Median month', fixed(t.median_month, 1)],
        ['Peak month', `${monthLabel(t.peak_month?.month)} (${num(t.peak_month?.count)})`],
        ['Burst months', num(t.bursts.length)],
        ['Volume in bursts', pct(t.burst_share_of_volume)],
        ['Accumulation half-life', dateLabel(t.accumulation_half_life)],
        ['Elapsed at half-life', pct(t.half_life_elapsed_fraction)],
        ['Longest dormancy', `${num(t.longest_dormancy?.days)} days`],
        ['Trailing 12m vs prior', `${num(v.trailing_12m)} vs ${num(v.prior_12m)} (${titleCase(v.direction)})`],
      ])}
      ${t.bursts.length ? `
        <h4 style="margin:1.1rem 0 .5rem;font-size:.72rem;color:#9a9a92;text-transform:uppercase;letter-spacing:.06em">Burst months</h4>
        ${barList(t.bursts.slice(0, 10).map((b) => ({
          label: monthLabel(b.month), value: b.count, display: `${b.count} · z${b.z}`,
        })), { warm: true })}
        <p class="note">Bursts typically encode a real event — a job change, a conference, a team
        onboarding. Cross-reference the dates against your own history before interpreting.</p>` : ''}`;
  },

  composition(doc) {
    const { seniority: s, function: f } = doc.composition;
    const sen = s.distribution.filter((d) => d.count > 0 && d.tier !== 'unknown');
    const fns = f.distribution.filter((d) => d.function !== 'unclassified').slice(0, 12);
    const drift = s.drift;

    return `
      <h3 class="section-title">Composition</h3>
      <p class="section-sub">Titles mapped onto two orthogonal axes: an ordinal seniority ladder and
      a nominal functional domain. Rule-based, so every assignment is auditable.</p>

      <h4 style="margin:.2rem 0 .5rem;font-size:.72rem;color:#9a9a92;text-transform:uppercase;letter-spacing:.06em">Seniority ladder</h4>
      ${barList(sen.map((d) => ({ label: titleCase(d.tier), value: d.count })))}
      ${kvTable([
        ['Titles classified', pct(s.classified_rate)],
        ['Mean ladder rank', fixed(s.mean_rank, 2), '0 = unknown … 8 = founder/owner'],
        ['Manager and above', pct(s.leadership_share)],
      ])}

      <h4 style="margin:1.1rem 0 .5rem;font-size:.72rem;color:#9a9a92;text-transform:uppercase;letter-spacing:.06em">Functional domains</h4>
      ${barList(fns.map((d) => ({ label: titleCase(d.function), value: d.count })), { warm: true })}
      ${kvTable([
        ['Modal function', titleCase(f.modal || '—')],
        ['Homophily index', pct(f.homophily_index)],
        ['Effective functions', fixed(f.effective_functions, 1)],
        ['Pielou evenness', fixed(f.evenness, 3)],
      ])}

      ${drift.available ? `
        <h4 style="margin:1.1rem 0 .5rem;font-size:.72rem;color:#9a9a92;text-transform:uppercase;letter-spacing:.06em">Seniority drift</h4>
        ${barList(drift.by_year.map((p) => ({
          label: String(p.year), value: p.mean_rank, display: fixed(p.mean_rank, 2),
        })), { max: 8 })}
        <p class="note">OLS slope ${fixed(drift.slope_rank_per_year, 3)} ladder-steps per year,
        R² ${fixed(drift.r_squared, 2)} — read as <strong>${esc(drift.interpretation)}</strong>.
        A low R² means year-to-year noise, not a trend.</p>`
      : `<p class="note">${esc(drift.reason || 'Insufficient data for drift analysis.')}</p>`}`;
  },

  eras(doc) {
    const e = doc.eras;
    if (!e.available) return unavailable(e.reason);
    return `
      <h3 class="section-title">Career eras</h3>
      <p class="section-sub">Non-parametric gap segmentation: the timeline is cut wherever the
      interval between consecutive connections exceeds ${num(e.gap_threshold_days)} days
      (3× the median gap). No cluster count to choose — the cuts are real dormancy.</p>
      ${e.eras.map((era, i) => `
        <article class="card">
          <div class="meta">
            <span class="tag">Era ${i + 1}</span>
            <span class="tag kind">${esc(dateLabel(era.start))} → ${esc(dateLabel(era.end))}</span>
          </div>
          <h4>${num(era.count)} connections · ${fixed(era.rate_per_month, 1)}/month</h4>
          <p>
            ${era.top_companies.length ? `Anchored on <strong>${esc(era.top_companies[0].company)}</strong>
            (${era.top_companies[0].count}).` : ''}
            ${era.top_functions.length ? ` Dominant function: ${esc(titleCase(era.top_functions[0].function))}.` : ''}
            ${era.mean_seniority_rank !== null ? ` Mean seniority ${fixed(era.mean_seniority_rank, 1)}.` : ''}
          </p>
          ${era.distinctive_terms.length ? `<p style="margin-top:.4rem">
            <span style="color:#6a6a64;font-size:.62rem;text-transform:uppercase;letter-spacing:.06em">Distinctive titles:</span>
            ${era.distinctive_terms.map((t) => esc(t.term)).join(' · ')}</p>` : ''}
        </article>`).join('')}
      <p class="note">Distinctive terms are ranked by log-odds against the whole corpus, not raw
      frequency — otherwise every era would just say "engineer".</p>`;
  },

  quality(doc) {
    const dq = doc.data_quality;
    const ing = dq.ingest || {};
    const comp = ing.completeness || {};
    const er = dq.entity_resolution || {};
    const st = doc.structure || {};
    const co = st.company_cooccurrence || {};

    return `
      <h3 class="section-title">Method &amp; data quality</h3>
      <p class="section-sub">What was observed, what was inferred, and where the ceiling sits.</p>

      <article class="card">
        <h4>Observed vs inferred</h4>
        <p><strong>Observed:</strong> the people → employer bipartite graph and the connection date.
        That is the entirety of what a LinkedIn export contains.</p>
        <p style="margin-top:.4rem"><strong>Inferred:</strong> employer adjacency from monthly
        co-occurrence, era boundaries, seniority and function labels. Each is a model of the data,
        not a fact about it.</p>
      </article>

      <article class="card">
        <h4>The one-hop ceiling</h4>
        <p>${esc(st.projection?.note || '')}</p>
        ${st.projection ? kvTable([
          ['Implied projection edges', num(st.projection.edges)],
          ['Mean degree', fixed(st.projection.mean_degree, 1)],
          ['Components', num(st.projection.components)],
          ['Largest component', pct(st.projection.largest_component_share)],
          ['Isolates', pct(st.projection.isolate_share)],
        ]) : ''}
      </article>

      <article class="card">
        <h4>Entity resolution</h4>
        ${kvTable([
          ['Raw employer strings', num(er.raw_distinct)],
          ['After canonicalization', num(er.canonical_distinct)],
          ['Variants merged', num(er.merged)],
          ['Merge rate', pct(dq.resolution_merge_rate)],
        ])}
        <p class="note">Legal suffixes, casing, and known aliases are collapsed by a deterministic
        rule cascade — no fuzzy matching, so results reproduce exactly across runs.</p>
      </article>

      <article class="card">
        <h4>Field completeness</h4>
        ${kvTable([
          ['Rows parsed', num(ing.rows_parsed)],
          ['Rows skipped', num(ing.rows_skipped)],
          ['Employer populated', pct(comp.company)],
          ['Title populated', pct(comp.position)],
          ['Date parsed', pct(comp.connected_on)],
        ])}
        ${(ing.warnings || []).length
          ? `<p class="note">${ing.warnings.map(esc).join('<br>')}</p>` : ''}
      </article>

      ${co.available ? `
        <article class="card">
          <h4>Inferred employer adjacency</h4>
          ${kvTable([
            ['Method', co.method],
            ['Employers linked', num(co.nodes)],
            ['Edges', num(co.edges)],
            ['Components', num(co.components)],
            ['Largest component', num(co.largest_component)],
          ])}
          ${co.top_edges?.length ? barList(co.top_edges.slice(0, 8).map((e) => ({
            label: `${e.source} ↔ ${e.target}`, value: e.weight, display: `${e.weight} mo`,
          })), { warm: true }) : ''}
          <p class="note">A hypothesis generator, not a finding. Co-occurrence in time suggests
          shared context; it does not establish it.</p>
        </article>` : `<article class="card"><h4>Inferred employer adjacency</h4>
          ${unavailable(co.reason)}</article>`}

      <p class="note">Engine: ${esc(doc.engine || 'python')} · schema ${esc(doc.schema_version)} ·
      ${num(doc.runtime_ms)} ms. No connection data was transmitted off this machine.</p>`;
  },

  detail(doc, node) {
    if (!node) return unavailable('Select a node in the graph to inspect it.');
    if (node.kind === 'hub') {
      const sample = node.sample || [];
      return `
        <h3 class="section-title">${esc(node.label)}</h3>
        <p class="section-sub">${num(node.members)} connections in this cluster</p>
        <table class="kv"><tbody>
          ${sample.map((m) => `<tr><td>${esc(m)}</td></tr>`).join('')}
          ${node.members > sample.length
            ? `<tr><td style="color:#6a6a64">+${num(node.members - sample.length)} more</td></tr>` : ''}
        </tbody></table>`;
    }
    return `
      <h3 class="section-title">${esc(node.label)}</h3>
      <p class="section-sub">${esc(node.position || 'No title recorded')}</p>
      ${kvTable([
        ['Employer', node.company || '—'],
        ['Connected', dateLabel(node.connected_on)],
        ['Seniority', titleCase(node.seniority || 'unknown')],
        ['Function', titleCase(node.function || 'unclassified')],
      ], ['Field', 'Value'])}
      ${node.url ? `<p style="margin-top:.7rem"><a href="${esc(node.url)}" target="_blank"
        rel="noopener noreferrer" style="color:#7b9fd4;font-size:.74rem">Open LinkedIn profile ↗</a></p>` : ''}`;
  },
};

export function renderTab(name, doc, selectedNode) {
  if (!doc) return '<p class="empty-note">Load a Connections.csv to populate the analysis.</p>';
  const fn = TABS[name] || TABS.insights;
  try {
    return fn(doc, selectedNode);
  } catch (err) {
    console.error(`Failed to render "${name}" tab`, err);
    return `<p class="empty-note">This panel could not be rendered: ${esc(err.message)}</p>`;
  }
}

export const TAB_NAMES = Object.keys(TABS);
