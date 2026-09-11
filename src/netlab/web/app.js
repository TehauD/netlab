/**
 * Application controller.
 *
 * Responsibilities: engine selection, file intake, state, and wiring the graph renderer to
 * the analysis dock. All analysis lives in ./lib; this file holds no statistics.
 *
 * Engine strategy — the Python service is an *optional accelerator*, never a dependency:
 *   1. Probe `/api/health` once at boot.
 *   2. If reachable, POST the file for the full analysis (eras, power-law fit, inferred
 *      employer adjacency).
 *   3. If not, or if the request fails, parse and analyze in this tab and label the
 *      degraded sections honestly rather than hiding them.
 */

import { parseConnections } from './lib/csv.js';
import { analyze as analyzeLocal, graphPayload } from './lib/analysis.js';
import { analyzeRemote, probeEngine, reportRemote } from './lib/api.js';
import { ForceGraph } from './lib/graph.js';
import { renderTab } from './lib/dock.js';
import { dateLabel, esc, fixed, num } from './lib/format.js';

const el = (id) => document.getElementById(id);

const dom = {
  canvas: el('graph'),
  statusPill: el('statusPill'),
  enginePill: el('enginePill'),
  onboardEngine: el('onboardEngine'),
  onboard: el('onboard'),
  dropzone: el('dropzone'),
  fileInput: el('fileInput'),
  errBanner: el('errBanner'),
  search: el('search'),
  clusterMode: el('clusterMode'),
  redactToggle: el('redactToggle'),
  loadBtn: el('loadBtn'),
  exportBtn: el('exportBtn'),
  fitBtn: el('fitBtn'),
  sampleBtn: el('sampleBtn'),
  dock: el('dock'),
  dockBody: el('dockBody'),
  dockTabs: el('dockTabs'),
  dockToggle: el('dockToggle'),
  detailTab: el('detailTab'),
  tooltip: el('tooltip'),
  legendHub: el('legendHub'),
  stats: {
    people: el('statPeople'),
    companies: el('statCompanies'),
    effective: el('statEffective'),
    gini: el('statGini'),
    top: el('statTop'),
    span: el('statSpan'),
  },
};

const state = {
  engine: null,        // health document from the Python service, or null
  file: null,          // retained so cluster/redact changes can re-run analysis
  people: null,        // browser-parsed records (browser engine only)
  doc: null,           // analysis document currently rendered
  activeTab: 'insights',
  selectedNode: null,
};

const graph = new ForceGraph(dom.canvas, {
  onSelect: handleSelect,
  onHover: handleHover,
});

// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------

async function initEngine() {
  state.engine = await probeEngine();
  const usingPython = Boolean(state.engine);
  dom.enginePill.textContent = usingPython ? `engine: python ${state.engine.version}` : 'engine: browser';
  dom.enginePill.className = `pill ${usingPython ? 'ok' : ''}`;
  dom.onboardEngine.textContent = usingPython
    ? 'local engine online — full analysis available'
    : 'browser engine — start `netlab serve` for eras + inferred adjacency';
  dom.onboardEngine.className = `pill ${usingPython ? 'ok' : 'warn'}`;
  dom.sampleBtn.disabled = !usingPython;
  dom.sampleBtn.title = usingPython
    ? 'Load a synthetic export to explore the tool'
    : 'The synthetic sample is served by the local Python engine';
}

// ---------------------------------------------------------------------------
// Intake
// ---------------------------------------------------------------------------

async function loadFile(file) {
  if (!file) return;
  showError('');
  setStatus('reading…', '');
  state.file = file;

  try {
    const clusterBy = dom.clusterMode.value;
    const redact = dom.redactToggle.checked;

    if (state.engine) {
      state.doc = await analyzeRemote(file, { clusterBy, redact });
      state.people = null;
    } else {
      const text = await file.text();
      const { people, report } = parseConnections(text);
      state.people = people;
      state.doc = analyzeLocal(people, report);
      state.doc.graph = graphPayload(people, clusterBy, redact);
    }

    applyDocument();
    setStatus(`${num(state.doc.overview.connections)} connections`, 'ok');
    dom.onboard.classList.add('hidden');
    dom.exportBtn.disabled = false;
  } catch (err) {
    console.error(err);
    setStatus('parse failed', 'err');
    showError(err.message || 'Could not read this file.');
    dom.onboard.classList.remove('hidden');
  }
}

/** Re-derive the graph when clustering or redaction changes, without re-reading the file. */
async function rebuildGraph() {
  if (!state.doc) return;
  const clusterBy = dom.clusterMode.value;
  const redact = dom.redactToggle.checked;
  dom.legendHub.textContent = { company: 'Employer', year: 'Year', function: 'Function', seniority: 'Seniority', none: '—' }[clusterBy];

  if (state.people) {
    state.doc.graph = graphPayload(state.people, clusterBy, redact);
  } else if (state.file && state.engine) {
    setStatus('re-clustering…', '');
    try {
      state.doc = await analyzeRemote(state.file, { clusterBy, redact });
      setStatus(`${num(state.doc.overview.connections)} connections`, 'ok');
    } catch (err) {
      showError(err.message);
      return;
    }
  }
  graph.setData(state.doc.graph);
  renderDock();
}

async function loadSample() {
  try {
    setStatus('fetching sample…', '');
    const response = await fetch('./api/sample');
    if (!response.ok) throw new Error(`Sample unavailable (${response.status}).`);
    const blob = await response.blob();
    await loadFile(new File([blob], 'Connections-sample.csv', { type: 'text/csv' }));
  } catch (err) {
    showError(err.message);
    setStatus('sample failed', 'err');
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function applyDocument() {
  const doc = state.doc;
  graph.setData(doc.graph);
  updateStats(doc);
  state.selectedNode = null;
  dom.detailTab.hidden = true;
  renderDock();
}

function updateStats(doc) {
  const ov = doc.overview;
  const conc = doc.companies.available ? doc.companies.concentration : null;
  const largest = doc.companies.available ? doc.companies.largest[0] : null;

  dom.stats.people.textContent = num(ov.connections);
  dom.stats.companies.textContent = num(ov.distinct_companies);
  dom.stats.effective.textContent = conc ? num(conc.effective_companies, 0) : '—';
  dom.stats.gini.textContent = conc ? fixed(conc.gini, 2) : '—';
  dom.stats.top.textContent = largest ? `${largest.company} (${largest.count})` : '—';
  dom.stats.span.textContent = ov.first_connection
    ? `${dateLabel(ov.first_connection)} → ${dateLabel(ov.last_connection)}`
    : '—';
}

function renderDock() {
  dom.dockBody.innerHTML = renderTab(state.activeTab, state.doc, state.selectedNode);
  dom.dockBody.scrollTop = 0;
}

function handleSelect(node) {
  state.selectedNode = node;
  dom.detailTab.hidden = !node;
  if (node) {
    state.activeTab = 'detail';
    setActiveTabButton('detail');
    renderDock();
    openDock(true);
  }
}

function handleHover(node, event) {
  if (!node || !event) {
    dom.tooltip.style.opacity = '0';
    return;
  }
  dom.tooltip.querySelector('.t-name').textContent = node.label;
  dom.tooltip.querySelector('.t-detail').textContent = node.kind === 'hub'
    ? `${num(node.members)} connections`
    : [node.position, node.company].filter(Boolean).join(' · ') || 'Connection';
  dom.tooltip.style.opacity = '1';

  const pad = 14;
  const rect = dom.tooltip.getBoundingClientRect();
  let x = event.clientX + pad;
  let y = event.clientY - 8;
  if (x + rect.width > window.innerWidth - 8) x = event.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight - 8) y = window.innerHeight - rect.height - 8;
  dom.tooltip.style.left = `${Math.max(x, 6)}px`;
  dom.tooltip.style.top = `${Math.max(y, 6)}px`;
}

function setActiveTabButton(name) {
  for (const btn of dom.dockTabs.querySelectorAll('button')) {
    btn.classList.toggle('active', btn.dataset.tab === name);
  }
}

function openDock(open) {
  dom.dock.classList.toggle('open', open);
  dom.dockToggle.setAttribute('aria-expanded', String(open));
}

function setStatus(text, kind) {
  dom.statusPill.textContent = text;
  dom.statusPill.className = `pill ${kind || ''}`;
}

function showError(message) {
  dom.errBanner.innerHTML = message ? esc(message) : '';
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function handleExport() {
  if (!state.doc) return;
  const stamp = new Date().toISOString().slice(0, 10);

  // The graph payload is bulky and carries names; the analysis document alone is the artifact.
  const { graph: _graph, ...document_ } = state.doc;
  download(`netlab-analysis-${stamp}.json`, JSON.stringify(document_, null, 2), 'application/json');

  if (state.engine && state.file) {
    try {
      const markdown = await reportRemote(state.file, { redact: dom.redactToggle.checked });
      download(`netlab-report-${stamp}.md`, markdown, 'text/markdown');
    } catch (err) {
      console.warn('Markdown report unavailable:', err.message);
    }
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

dom.dropzone.addEventListener('click', () => dom.fileInput.click());
dom.dropzone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); dom.fileInput.click(); }
});
dom.fileInput.addEventListener('change', (e) => loadFile(e.target.files[0]));

for (const type of ['dragenter', 'dragover']) {
  dom.dropzone.addEventListener(type, (e) => { e.preventDefault(); dom.dropzone.classList.add('dragover'); });
}
for (const type of ['dragleave', 'drop']) {
  dom.dropzone.addEventListener(type, () => dom.dropzone.classList.remove('dragover'));
}
dom.dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  loadFile(e.dataTransfer.files[0]);
});
// Swallow stray drops so the browser never navigates away from the app.
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => e.preventDefault());

dom.loadBtn.addEventListener('click', () => {
  dom.onboard.classList.remove('hidden');
  showError('');
});
dom.sampleBtn.addEventListener('click', loadSample);
dom.exportBtn.addEventListener('click', handleExport);
dom.exportBtn.disabled = true;
dom.fitBtn.addEventListener('click', () => { graph.fit(); graph.render(); });

dom.clusterMode.addEventListener('change', rebuildGraph);
dom.redactToggle.addEventListener('change', rebuildGraph);

let searchTimer;
dom.search.addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  const value = e.target.value;
  searchTimer = setTimeout(() => graph.setSearch(value), 90);
});

dom.dockTabs.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-tab]');
  if (!btn) return;
  state.activeTab = btn.dataset.tab;
  setActiveTabButton(state.activeTab);
  renderDock();
});

dom.dockToggle.addEventListener('click', () => openDock(!dom.dock.classList.contains('open')));

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { openDock(false); dom.onboard.classList.add('hidden'); }
  if (e.key === '/' && document.activeElement !== dom.search) { e.preventDefault(); dom.search.focus(); }
  if (e.key.toLowerCase() === 'f' && !e.metaKey && !e.ctrlKey && document.activeElement !== dom.search) {
    graph.fit(); graph.render();
  }
});

// Pause the simulation when the tab is hidden — an idle background tab should cost nothing.
document.addEventListener('visibilitychange', () => {
  if (document.hidden) graph.stop();
  else if (state.doc) graph.start();
});

initEngine();
