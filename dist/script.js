/* =========================================================
   NETWORK — LinkedIn connections graph
   Pure client-side file parsing. No network calls, no API,
   no server. The CSV never leaves this browser tab.
   ========================================================= */

let N = [];
let C = [];
let NM = {};
let adj = {};
let clusterMode = 'company';
let searchTerm = '';
let rawPeople = []; // parsed people records, kept so we can rebuild on cluster-mode change

let camX = 0, camY = 0, zoom = 1, drag = false, dsx, dsy, csx, csy;

const cv = document.getElementById('g'), cx = cv.getContext('2d');
let W, H;
function resize() { W = cv.width = innerWidth; H = cv.height = innerHeight - 48; cv.style.top = '48px'; }
addEventListener('resize', resize);
resize();

// ---------- robust CSV parsing (handles quoted fields containing commas) ----------
function parseCSV(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i], next = text[i + 1];
    if (inQuotes) {
      if (c === '"' && next === '"') { field += '"'; i++; }
      else if (c === '"') { inQuotes = false; }
      else { field += c; }
    } else {
      if (c === '"') inQuotes = true;
      else if (c === ',') { row.push(field); field = ''; }
      else if (c === '\r') { /* skip */ }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
      else field += c;
    }
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.length > 1 || (r.length === 1 && r[0].trim() !== ''));
}

// LinkedIn's export prepends a few "Notes:" lines before the real header.
// Find the row that actually looks like the connections header.
function findHeaderRow(rows) {
  for (let i = 0; i < rows.length; i++) {
    const lower = rows[i].map(c => c.trim().toLowerCase());
    if (lower.includes('first name') && lower.includes('last name')) {
      return i;
    }
  }
  return -1;
}

function parseLinkedInCSV(text) {
  const rows = parseCSV(text);
  const headerIdx = findHeaderRow(rows);
  if (headerIdx === -1) {
    throw new Error('Could not find a header row with "First Name" / "Last Name". Is this the Connections.csv from LinkedIn\'s data export?');
  }
  const header = rows[headerIdx].map(h => h.trim().toLowerCase());
  const col = name => header.indexOf(name);

  const idxFirst = col('first name');
  const idxLast = col('last name');
  const idxUrl = col('url');
  const idxCompany = col('company');
  const idxPosition = col('position');
  const idxConnected = col('connected on');

  const people = [];
  for (let i = headerIdx + 1; i < rows.length; i++) {
    const r = rows[i];
    if (!r || r.length < 2) continue;
    const first = (r[idxFirst] || '').trim();
    const last = (r[idxLast] || '').trim();
    if (!first && !last) continue;
    people.push({
      name: `${first} ${last}`.trim(),
      url: idxUrl >= 0 ? (r[idxUrl] || '').trim() : '',
      company: idxCompany >= 0 ? (r[idxCompany] || '').trim() : '',
      position: idxPosition >= 0 ? (r[idxPosition] || '').trim() : '',
      connectedOn: idxConnected >= 0 ? (r[idxConnected] || '').trim() : '',
    });
  }
  return people;
}

// ---------- normalization ----------
function normalizeCompany(name) {
  if (!name) return '';
  return name
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/,?\s*(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?)$/i, '')
    .trim();
}

function parseConnectedDate(str) {
  // LinkedIn format: "15 Mar 2022" or similar; be lenient
  const d = new Date(str);
  return isNaN(d) ? null : d;
}

// ---------- build graph ----------
function buildGraph(people) {
  N = []; C = []; NM = {}; adj = {};
  let idCounter = 0;

  const personNodes = people.map(p => {
    const id = idCounter++;
    const node = {
      id, kind: 'person', l: p.name || '(unnamed)',
      company: normalizeCompany(p.company), position: p.position,
      url: p.url, connectedOn: p.connectedOn,
      r: 5, color: '#7b9fd4',
    };
    N.push(node); NM[id] = node; adj[id] = [];
    return node;
  });

  if (clusterMode === 'company') {
    const companyIndex = {};
    personNodes.forEach(p => {
      if (!p.company) return;
      if (!companyIndex[p.company]) {
        const cid = idCounter++;
        const cnode = { id: cid, kind: 'company', l: p.company, r: 6, color: '#c98a4b', members: [] };
        companyIndex[p.company] = cid;
        N.push(cnode); NM[cid] = cnode; adj[cid] = [];
      }
      const cid = companyIndex[p.company];
      NM[cid].members.push(p.l);
      C.push([p.id, cid]);
      adj[p.id].push(cid); adj[cid].push(p.id);
    });
    // size company nodes by cluster size
    Object.values(companyIndex).forEach(cid => {
      const n = NM[cid];
      n.r = Math.min(22, 6 + Math.sqrt(n.members.length) * 3);
    });
  } else if (clusterMode === 'recency') {
    const yearIndex = {};
    personNodes.forEach(p => {
      const d = parseConnectedDate(p.connectedOn);
      const year = d ? String(d.getFullYear()) : 'Unknown';
      if (!yearIndex[year]) {
        const yid = idCounter++;
        const ynode = { id: yid, kind: 'year', l: year, r: 6, color: '#c98a4b', members: [] };
        yearIndex[year] = yid;
        N.push(ynode); NM[yid] = ynode; adj[yid] = [];
      }
      const yid = yearIndex[year];
      NM[yid].members.push(p.l);
      C.push([p.id, yid]);
      adj[p.id].push(yid); adj[yid].push(p.id);
    });
    Object.values(yearIndex).forEach(yid => {
      const n = NM[yid];
      n.r = Math.min(22, 6 + Math.sqrt(n.members.length) * 3);
    });
  }
  // 'none' mode: no cluster nodes, people just float

  const rng = s => { let x = Math.sin(s * 9301 + 49297) % 1; return x < 0 ? x + 1 : x; };
  N.forEach((n, i) => {
    const a = rng(i) * Math.PI * 2;
    const rad = 60 + rng(i + 50) * 320;
    n.x = Math.cos(a) * rad; n.y = Math.sin(a) * rad;
    n.vx = 0; n.vy = 0;
  });

  updateStats(personNodes);
}

function updateStats(personNodes) {
  document.getElementById('statPeople').textContent = personNodes.length;
  const companies = new Set(personNodes.map(p => p.company).filter(Boolean));
  document.getElementById('statCompanies').textContent = companies.size;

  const companyCounts = {};
  personNodes.forEach(p => { if (p.company) companyCounts[p.company] = (companyCounts[p.company] || 0) + 1; });
  const top = Object.entries(companyCounts).sort((a, b) => b[1] - a[1])[0];
  document.getElementById('statTopCompany').textContent = top ? `${top[0]} (${top[1]})` : '—';

  const dates = personNodes.map(p => parseConnectedDate(p.connectedOn)).filter(Boolean).sort((a, b) => a - b);
  if (dates.length) {
    const fmt = d => d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    document.getElementById('statSpan').textContent = `${fmt(dates[0])} → ${fmt(dates[dates.length - 1])}`;
  } else {
    document.getElementById('statSpan').textContent = '—';
  }
}

// ---------- force simulation ----------
function step() {
  const REPEL = 1600, SPRING = 0.018, SPRING_LEN = 70, DAMP = 0.85, CENTER = 0.0012;
  for (let i = 0; i < N.length; i++) {
    const a = N[i];
    let fx = -a.x * CENTER, fy = -a.y * CENTER;
    for (let j = 0; j < N.length; j++) {
      if (i === j) continue;
      const b = N[j];
      let dx = a.x - b.x, dy = a.y - b.y;
      let d2 = dx * dx + dy * dy || 0.01;
      if (d2 < 140000) {
        const f = REPEL / d2;
        fx += dx * f; fy += dy * f;
      }
    }
    a.fx = fx; a.fy = fy;
  }
  C.forEach(([ia, ib]) => {
    const a = NM[ia], b = NM[ib];
    if (!a || !b) return;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const force = (dist - SPRING_LEN) * SPRING;
    const fx = (dx / dist) * force, fy = (dy / dist) * force;
    a.fx += fx; a.fy += fy;
    b.fx -= fx; b.fy -= fy;
  });
  N.forEach(n => {
    n.vx = (n.vx + n.fx) * DAMP;
    n.vy = (n.vy + n.fy) * DAMP;
    n.x += n.vx; n.y += n.vy;
  });
}

// ---------- interaction ----------
cv.addEventListener('mousedown', e => { drag = true; dsx = e.clientX; dsy = e.clientY; csx = camX; csy = camY; });
cv.addEventListener('mousemove', e => { if (drag) { camX = csx + (e.clientX - dsx); camY = csy + (e.clientY - dsy); } else doHover(e); });
cv.addEventListener('mouseup', () => drag = false);
cv.addEventListener('mouseleave', () => { drag = false; hideTT(); });
cv.addEventListener('click', doClick);
cv.addEventListener('wheel', e => {
  e.preventDefault();
  const oz = zoom;
  zoom = Math.max(.15, Math.min(4, zoom * (e.deltaY < 0 ? 1.1 : .9)));
  const r = cv.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  camX = mx - (mx - camX) * (zoom / oz);
  camY = my - (my - camY) * (zoom / oz);
}, { passive: false });

function s2w(sx, sy) { return { x: (sx - camX - W / 2) / zoom, y: (sy - camY - H / 2) / zoom }; }

function nodeAt(wx, wy) {
  for (const n of N) {
    const dx = wx - n.x, dy = wy - n.y;
    if (dx * dx + dy * dy < (n.r + 5) * (n.r + 5)) return n;
  }
  return null;
}

const ttel = document.getElementById('tt'), ttn = document.getElementById('ttn'), ttd = document.getElementById('ttd');
function showTT(x, y, n) {
  ttn.textContent = n.l;
  ttd.textContent = n.kind === 'person' ? (n.position || n.company || 'Connection') : `${(n.members || []).length} connections`;
  ttel.style.opacity = '1';
  let tx = x + 12, ty = y - 8;
  if (tx + 250 > W) tx = x - 260;
  if (ty < 5) ty = 5;
  ttel.style.left = tx + 'px'; ttel.style.top = ty + 'px';
}
function hideTT() { ttel.style.opacity = '0'; }

function doHover(e) {
  const r = cv.getBoundingClientRect();
  const w = s2w(e.clientX - r.left, e.clientY - r.top);
  const n = nodeAt(w.x, w.y);
  if (n) { showTT(e.clientX, e.clientY, n); cv.style.cursor = 'pointer'; }
  else { hideTT(); cv.style.cursor = 'grab'; }
}

function doClick(e) {
  const r = cv.getBoundingClientRect();
  const w = s2w(e.clientX - r.left, e.clientY - r.top);
  const n = nodeAt(w.x, w.y);
  if (n) openPanel(n);
}

function escapeHTML(s) { return String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function openPanel(n) {
  let h = `<h3>${escapeHTML(n.l)}</h3>`;
  h += `<span class="tg" style="background:${n.color}22;color:${n.color}">${n.kind}</span>`;
  if (n.kind === 'person') {
    if (n.position) h += `<div class="sec"><h4>Position</h4><p>${escapeHTML(n.position)}</p></div>`;
    if (n.company) h += `<div class="sec"><h4>Company</h4><p>${escapeHTML(n.company)}</p></div>`;
    if (n.connectedOn) h += `<div class="sec"><h4>Connected on</h4><p>${escapeHTML(n.connectedOn)}</p></div>`;
    if (n.url) h += `<div class="sec"><h4>Profile</h4><p><a href="${escapeHTML(n.url)}" target="_blank" rel="noopener">${escapeHTML(n.url)}</a></p></div>`;
  } else {
    const members = n.members || [];
    h += `<div class="sec"><h4>${members.length} connection${members.length === 1 ? '' : 's'}</h4><ul>`;
    h += members.slice(0, 60).map(m => `<li>${escapeHTML(m)}</li>`).join('');
    if (members.length > 60) h += `<li style="color:#6a6a64">+${members.length - 60} more</li>`;
    h += `</ul></div>`;
  }
  document.getElementById('pd').innerHTML = h;
  document.getElementById('pn').classList.add('open');
  document.getElementById('po').classList.add('open');
}
function closePanel() {
  document.getElementById('pn').classList.remove('open');
  document.getElementById('po').classList.remove('open');
}

document.getElementById('search').addEventListener('input', e => { searchTerm = e.target.value.toLowerCase(); });
document.getElementById('clusterMode').addEventListener('change', e => {
  clusterMode = e.target.value;
  if (rawPeople.length) buildGraph(rawPeople);
});

// ---------- render ----------
function render() {
  cx.clearRect(0, 0, W, H);
  cx.save();
  cx.translate(camX + W / 2, camY + H / 2);
  cx.scale(zoom, zoom);

  cx.lineWidth = 0.5 / zoom;
  C.forEach(([ia, ib]) => {
    const a = NM[ia], b = NM[ib];
    if (!a || !b) return;
    cx.strokeStyle = 'rgba(255,255,255,0.06)';
    cx.beginPath(); cx.moveTo(a.x, a.y); cx.lineTo(b.x, b.y); cx.stroke();
  });

  N.forEach(n => {
    let alpha = 1;
    if (searchTerm.length > 1) {
      const haystack = (n.l + ' ' + (n.company || '')).toLowerCase();
      if (!haystack.includes(searchTerm)) alpha = 0.06;
    }
    cx.globalAlpha = alpha;
    cx.fillStyle = n.color;
    cx.beginPath(); cx.arc(n.x, n.y, n.r, 0, Math.PI * 2); cx.fill();
    if (n.kind !== 'person') {
      cx.strokeStyle = 'rgba(255,255,255,0.2)'; cx.lineWidth = 1 / zoom; cx.stroke();
    }
  });
  cx.globalAlpha = 1;

  if (zoom > 0.9) {
    cx.font = `${10.5 / zoom}px -apple-system, sans-serif`;
    cx.textAlign = 'center';
    N.forEach(n => {
      if (n.kind === 'person' && zoom < 1.6) return; // declutter at low zoom
      let alpha = 1;
      if (searchTerm.length > 1) {
        const haystack = (n.l + ' ' + (n.company || '')).toLowerCase();
        if (!haystack.includes(searchTerm)) alpha = 0.06;
      }
      cx.globalAlpha = alpha;
      cx.fillStyle = n.kind === 'person' ? 'rgba(231,230,225,0.5)' : 'rgba(201,138,75,0.85)';
      cx.fillText(n.l, n.x, n.y - n.r - 4 / zoom);
    });
    cx.globalAlpha = 1;
  }

  cx.restore();
}

function loop() {
  if (N.length) { step(); render(); }
  requestAnimationFrame(loop);
}
loop();

// ---------- file loading ----------
function handleFile(file) {
  if (!file) return;
  setConnStatus('reading file…', '');
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const people = parseLinkedInCSV(e.target.result);
      if (!people.length) {
        throw new Error('Parsed the file but found 0 connections. Double check this is Connections.csv from the LinkedIn export, not a different file from the archive.');
      }
      rawPeople = people;
      buildGraph(people);
      setConnStatus(`${people.length} connections loaded`, 'live');
      document.getElementById('emptyState').classList.add('hidden');
    } catch (err) {
      console.error(err);
      setConnStatus('parse failed', '');
      alert(err.message || 'Could not parse this file.');
    }
  };
  reader.onerror = () => {
    setConnStatus('read failed', '');
    alert('Could not read the file.');
  };
  reader.readAsText(file);
}

function setConnStatus(text, kind) {
  const el = document.getElementById('connStatus');
  el.textContent = text;
  el.className = 'conn-status' + (kind ? ' ' + kind : '');
}

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => handleFile(e.target.files[0]));
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  handleFile(file);
});

document.getElementById('loadNewBtn').addEventListener('click', () => {
  document.getElementById('emptyState').classList.remove('hidden');
});