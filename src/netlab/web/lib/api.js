/**
 * Local engine client.
 *
 * Every call is same-origin against 127.0.0.1. If the Python process is not running, the
 * probe fails fast and the app silently falls back to the in-browser engine — the UI never
 * blocks on a service that is optional by design.
 */

const HEALTH_TIMEOUT_MS = 1200;

async function withTimeout(promise, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await promise(controller.signal);
  } finally {
    clearTimeout(timer);
  }
}

/** Returns the health document, or null when the local engine is unreachable. */
export async function probeEngine() {
  try {
    const response = await withTimeout(
      (signal) => fetch('./api/health', { signal, cache: 'no-store' }),
      HEALTH_TIMEOUT_MS,
    );
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/** Upload a file for server-side analysis. Throws with the server's detail on failure. */
export async function analyzeRemote(file, { clusterBy = 'company', redact = false } = {}) {
  const form = new FormData();
  form.append('file', file, file.name || 'Connections.csv');
  form.append('cluster_by', clusterBy);
  form.append('redact', String(redact));
  form.append('include_graph', 'true');

  const response = await fetch('./api/analyze', { method: 'POST', body: form });
  if (!response.ok) {
    let detail = `Engine returned ${response.status}.`;
    try {
      const body = await response.json();
      detail = body.detail || body.error || detail;
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  const doc = await response.json();
  doc.engine = 'python';
  return doc;
}

/** Request the Markdown report artifact from the local engine. */
export async function reportRemote(file, { redact = true } = {}) {
  const form = new FormData();
  form.append('file', file, file.name || 'Connections.csv');
  form.append('redact', String(redact));
  const response = await fetch('./api/report', { method: 'POST', body: form });
  if (!response.ok) throw new Error(`Engine returned ${response.status}.`);
  return response.text();
}
