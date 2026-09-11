/**
 * Browser-side CSV ingest and enrichment.
 *
 * This mirrors the Python rules in `netlab.core.parsing` and `netlab.core.normalize` so
 * the tool still works with the Python engine stopped. The two implementations are kept
 * in deliberate lockstep; `tests/test_parity.py` asserts they agree on the sample export.
 */

/** RFC-4180 tolerant reader: handles quoted fields, escaped quotes, and CRLF. */
export function parseCSV(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\r') { /* normalized away */ }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim() !== ''));
}

const COLUMN_ALIASES = {
  firstName:   ['first name', 'firstname', 'first'],
  lastName:    ['last name', 'lastname', 'last'],
  url:         ['url', 'profile url', 'public profile url'],
  company:     ['company', 'current company', 'organization'],
  position:    ['position', 'title', 'current position', 'job title'],
  connectedOn: ['connected on', 'connectedon', 'connected date'],
};

const norm = (s) => String(s).replace(/\ufeff/g, '').trim().toLowerCase().replace(/\s+/g, ' ');

/** LinkedIn prepends a variable-length "Notes:" preamble; find the true header. */
function findHeaderRow(rows) {
  for (let i = 0; i < Math.min(rows.length, 25); i++) {
    const cells = new Set(rows[i].map(norm));
    const hasFirst = COLUMN_ALIASES.firstName.some((a) => cells.has(a));
    const hasLast = COLUMN_ALIASES.lastName.some((a) => cells.has(a));
    if (hasFirst && hasLast) return i;
  }
  return -1;
}

const DATE_PATTERNS = [
  /^(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})$/,      // 15 Mar 2022
  /^([A-Za-z]{3,})\s+(\d{1,2}),\s*(\d{4})$/,     // Mar 15, 2022
  /^(\d{4})-(\d{2})-(\d{2})$/,                   // ISO
];
const MONTHS = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
  jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
};

/** Explicit parsing rather than `new Date(str)`, whose behavior is locale-dependent. */
export function parseConnectedOn(value) {
  const v = String(value || '').trim();
  if (!v) return null;
  let m;
  if ((m = v.match(DATE_PATTERNS[0]))) {
    const month = MONTHS[m[2].slice(0, 3).toLowerCase()];
    if (month === undefined) return null;
    return new Date(Date.UTC(+m[3], month, +m[1]));
  }
  if ((m = v.match(DATE_PATTERNS[1]))) {
    const month = MONTHS[m[1].slice(0, 3).toLowerCase()];
    if (month === undefined) return null;
    return new Date(Date.UTC(+m[3], month, +m[2]));
  }
  if ((m = v.match(DATE_PATTERNS[2]))) {
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  }
  const fallback = new Date(v);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

const LEGAL_SUFFIX = /[,\s]+(?:inc\.?|llc\.?|ltd\.?|limited|corp\.?|corporation|co\.?|plc|gmbh|s\.a\.|sa|ag|bv|nv|pty|llp|lp|pc|pllc)\s*$/i;
const ALIASES = {
  'ibm corporation': 'IBM', 'alphabet': 'Google', 'facebook': 'Meta',
  'meta platforms': 'Meta', 'microsoft corporation': 'Microsoft',
  'amazon web services': 'Amazon', aws: 'Amazon', pwc: 'PwC',
  'ernst & young': 'EY', 'self employed': 'Self-Employed',
  'self-employed': 'Self-Employed', freelance: 'Self-Employed',
  independent: 'Self-Employed', 'n/a': '', none: '', '-': '',
};

export function canonicalCompany(raw) {
  if (!raw) return '';
  let s = String(raw).normalize('NFKC').replace(/[\u2018\u2019\u201c\u201d`'"]/g, '')
    .replace(/\s+/g, ' ').trim().replace(/^[\s,\-–—]+|[\s,\-–—]+$/g, '');
  if (!s) return '';
  s = s.replace(/\s*\([^)]*\)\s*$/, '');
  for (let i = 0; i < 2; i++) {
    const stripped = s.replace(LEGAL_SUFFIX, '').replace(/[\s,]+$/, '');
    if (stripped === s) break;
    s = stripped;
  }
  if (!s) return '';
  const alias = ALIASES[s.toLowerCase()];
  if (alias !== undefined) return alias;
  if (s === s.toUpperCase() && s.length > 4 && s.includes(' ')) {
    s = s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return s;
}

export const SENIORITY_LADDER = [
  'unknown', 'student', 'individual_contributor', 'senior',
  'staff_principal', 'manager', 'director', 'executive', 'founder_owner',
];

// Order is significant: "VP of Engineering" must resolve to executive, not manager.
const SENIORITY_RULES = [
  ['founder_owner', /\b(founder|co-?founder|owner|proprietor|managing partner|partner)\b/i],
  ['executive', /\b(chief|c[etofimdpr]o\b|cxo|president|vice president|vp|svp|evp|avp|head of|global head|general manager|gm|board member|managing director)\b/i],
  ['director', /\b(director|dir\.|dean|chair)\b/i],
  ['manager', /\b(manager|mgr|supervisor|team lead|team leader|foreman|superintendent)\b/i],
  ['staff_principal', /\b(principal|staff|distinguished|fellow|architect|lead|master)\b/i],
  ['senior', /\b(senior|sr\.?|sme|iii)\b/i],
  ['student', /\b(student|intern|trainee|apprentice|resident|fellowship|candidate|phd)\b/i],
  ['individual_contributor', /\b(engineer|developer|analyst|scientist|designer|consultant|associate|coordinator|administrator|technician|nurse|rn|representative|assistant|officer|advisor|agent|clerk|writer|recruiter|accountant|attorney|pharmacist|therapist|teacher|professor|instructor|controller|counsel|specialist|paralegal)\b/i],
];

const FUNCTION_RULES = [
  ['data_ai', /\b(data scien|machine learning|ml engineer|ai\b|artificial intelligence|data engineer|analytics|statistic|biostat|nlp|mlops|data analyst|business intelligence|research scientist)/i],
  ['engineering', /\b(software|engineer|engineering|developer|development|devops|sre|programmer|architect|infrastructure|platform|cloud|security|cyber|qa|full.?stack|backend|frontend|systems)/i],
  ['product', /\b(product manager|product owner|product lead|cpo|product manage|program manager|technical program|scrum|agile coach)/i],
  ['design', /\b(design|ux|ui|user experience|creative|brand|illustrat)/i],
  ['healthcare', /\b(nurse|nursing|rn\b|bsn|physician|doctor|md\b|clinical|pharmac|patient|health|medical|surgeon|therap|radiolog|care team)/i],
  ['sales', /\b(sales|account executive|account manager|business development|bdr|sdr|revenue|partnership|customer success|client)/i],
  ['marketing', /\b(marketing|growth|seo|content|communications|brand manager|demand gen|social media|public relations)/i],
  ['finance', /\b(financ|account|audit|controller|treasur|investment|equity|banking|actuar|tax|cfo|fp&a)/i],
  ['people_ops', /\b(human resources|hr\b|recruit|talent|people ops|people operations|chro|benefits|compensation)/i],
  ['legal', /\b(legal|attorney|counsel|paralegal|compliance|contract|privacy officer|regulatory)/i],
  ['operations', /\b(operations|supply chain|logistics|procurement|manufactur|quality|facilities|project manager|coo\b)/i],
  ['education_research', /\b(professor|lecturer|teacher|instructor|research|faculty|academic|postdoc|dean)/i],
];

export function classifySeniority(title) {
  if (!title) return ['unknown', 0];
  for (const [label, re] of SENIORITY_RULES) {
    if (re.test(title)) return [label, SENIORITY_LADDER.indexOf(label)];
  }
  return ['unknown', 0];
}

export function classifyFunction(title) {
  if (!title) return 'unclassified';
  for (const [label, re] of FUNCTION_RULES) if (re.test(title)) return label;
  return 'unclassified';
}

/** Parse + enrich in one pass. Throws a descriptive Error on unusable input. */
export function parseConnections(text) {
  const rows = parseCSV(text);
  if (!rows.length) throw new Error('The file is empty.');

  const headerIdx = findHeaderRow(rows);
  if (headerIdx === -1) {
    throw new Error(
      'No header row containing "First Name" and "Last Name" was found. ' +
      'Confirm this is Connections.csv from the LinkedIn data export archive.'
    );
  }

  const header = rows[headerIdx].map(norm);
  const columns = {};
  for (const [field, aliases] of Object.entries(COLUMN_ALIASES)) {
    const idx = aliases.map((a) => header.indexOf(a)).find((i) => i >= 0);
    if (idx !== undefined) columns[field] = idx;
  }

  const report = {
    rows_scanned: rows.length, rows_parsed: 0, rows_skipped: 0,
    header_row_index: headerIdx, detected_columns: columns,
    missing_company: 0, missing_position: 0, unparsed_dates: 0, warnings: [],
  };

  const cell = (row, key) => {
    const i = columns[key];
    return i === undefined || i >= row.length ? '' : String(row[i]).trim();
  };

  const people = [];
  for (let i = headerIdx + 1; i < rows.length; i++) {
    const row = rows[i];
    const first = cell(row, 'firstName');
    const last = cell(row, 'lastName');
    if (!first && !last) { report.rows_skipped++; continue; }

    const companyRaw = cell(row, 'company');
    const position = cell(row, 'position').replace(/\s+/g, ' ').trim();
    const connectedRaw = cell(row, 'connectedOn');
    const connectedOn = parseConnectedOn(connectedRaw);
    const [seniority, seniorityRank] = classifySeniority(position);

    if (!companyRaw) report.missing_company++;
    if (!position) report.missing_position++;
    if (!connectedOn) report.unparsed_dates++;

    people.push({
      name: `${first} ${last}`.trim(),
      initials: `${(first[0] || '?').toUpperCase()}.${(last[0] || '?').toUpperCase()}.`,
      url: cell(row, 'url'),
      companyRaw,
      company: canonicalCompany(companyRaw),
      position,
      connectedOn,
      connected_on: connectedOn ? connectedOn.toISOString().slice(0, 10) : null,
      seniority,
      seniority_rank: seniorityRank,
      function: classifyFunction(position),
    });
  }

  report.rows_parsed = people.length;
  report.completeness = {
    company: 1 - report.missing_company / Math.max(people.length, 1),
    position: 1 - report.missing_position / Math.max(people.length, 1),
    connected_on: 1 - report.unparsed_dates / Math.max(people.length, 1),
  };

  if (!people.length) {
    throw new Error('The header was found but zero connection rows followed.');
  }
  return { people, report };
}
