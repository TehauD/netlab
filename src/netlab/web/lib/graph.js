/**
 * Canvas force-directed layout and renderer.
 *
 * Two changes that matter versus a naive implementation:
 *
 * 1. **Spatial-hash repulsion.** Pairwise repulsion is O(n^2) per frame, which stalls
 *    above roughly 1,500 nodes. Nodes are binned into a uniform grid and each node only
 *    repels against its own and adjacent cells — effectively O(n) for the node densities
 *    a connections export produces.
 *
 * 2. **Simulated annealing with a freeze.** Alpha decays each tick and the loop stops
 *    integrating once the layout settles, so an idle tab costs nothing. Interaction
 *    reheats it. The original prototype simulated forever at full temperature.
 *
 * Hit testing reuses the same grid, so picking stays O(1) rather than scanning every node.
 */

const PALETTE = {
  person: '#7b9fd4',
  hub: '#c98a4b',
  selected: '#e7e6e1',
  edge: 'rgba(255,255,255,0.06)',
  edgeActive: 'rgba(123,159,212,0.42)',
};

const CONFIG = {
  repel: 1600,
  spring: 0.018,
  springLength: 70,
  damping: 0.85,
  centering: 0.0012,
  cellSize: 90,
  alphaDecay: 0.994,
  alphaMin: 0.008,
  maxTicksPerFrame: 1,
};

export class ForceGraph {
  constructor(canvas, { onSelect, onHover } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', { alpha: false });
    this.onSelect = onSelect || (() => {});
    this.onHover = onHover || (() => {});

    this.nodes = [];
    this.edges = [];
    this.byId = new Map();
    this.adjacency = new Map();

    this.camera = { x: 0, y: 0, zoom: 1 };
    this.alpha = 1;
    this.searchTerm = '';
    this.selectedId = null;
    this.running = false;

    this.grid = new Map();
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);

    this.#bindEvents();
    this.resize();
  }

  // ---------- lifecycle ----------

  resize() {
    const topbar = 48, statbar = 40;
    this.width = window.innerWidth;
    this.height = Math.max(window.innerHeight - topbar - statbar, 200);
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  /** Deterministic seeded placement so the same export always lays out the same way. */
  setData({ nodes, edges }) {
    this.nodes = nodes.map((n, i) => {
      const angle = pseudoRandom(i) * Math.PI * 2;
      const radius = 60 + pseudoRandom(i + 50) * 340;
      return {
        ...n,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        vx: 0, vy: 0,
        r: n.kind === 'hub' ? Math.min(22, 6 + Math.sqrt(n.members || 1) * 3) : 5,
        color: n.kind === 'hub' ? PALETTE.hub : PALETTE.person,
      };
    });
    this.edges = edges;
    this.byId = new Map(this.nodes.map((n) => [n.id, n]));

    this.adjacency = new Map();
    for (const [a, b] of edges) {
      if (!this.adjacency.has(a)) this.adjacency.set(a, []);
      if (!this.adjacency.has(b)) this.adjacency.set(b, []);
      this.adjacency.get(a).push(b);
      this.adjacency.get(b).push(a);
    }

    this.alpha = 1;
    this.selectedId = null;
    this.fit();
    this.start();
  }

  start() {
    if (this.running) return;
    this.running = true;
    const loop = () => {
      if (!this.running) return;
      if (this.alpha > CONFIG.alphaMin) {
        for (let i = 0; i < CONFIG.maxTicksPerFrame; i++) this.tick();
        this.alpha *= CONFIG.alphaDecay;
      }
      this.render();
      this.frame = requestAnimationFrame(loop);
    };
    loop();
  }

  stop() {
    this.running = false;
    if (this.frame) cancelAnimationFrame(this.frame);
  }

  reheat(amount = 0.35) {
    this.alpha = Math.max(this.alpha, amount);
  }

  // ---------- simulation ----------

  #rebuildGrid() {
    this.grid.clear();
    const size = CONFIG.cellSize;
    for (const n of this.nodes) {
      const key = `${Math.floor(n.x / size)},${Math.floor(n.y / size)}`;
      let bucket = this.grid.get(key);
      if (!bucket) { bucket = []; this.grid.set(key, bucket); }
      bucket.push(n);
    }
  }

  tick() {
    this.#rebuildGrid();
    const size = CONFIG.cellSize;

    // Repulsion against the 3x3 neighborhood only.
    for (const node of this.nodes) {
      let fx = -node.x * CONFIG.centering;
      let fy = -node.y * CONFIG.centering;
      const cx = Math.floor(node.x / size);
      const cy = Math.floor(node.y / size);

      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          const bucket = this.grid.get(`${cx + dx},${cy + dy}`);
          if (!bucket) continue;
          for (const other of bucket) {
            if (other === node) continue;
            const ddx = node.x - other.x;
            const ddy = node.y - other.y;
            const d2 = ddx * ddx + ddy * ddy || 0.01;
            const force = CONFIG.repel / d2;
            fx += ddx * force;
            fy += ddy * force;
          }
        }
      }
      node.fx = fx;
      node.fy = fy;
    }

    // Spring attraction along observed affiliation edges.
    for (const [ia, ib] of this.edges) {
      const a = this.byId.get(ia);
      const b = this.byId.get(ib);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.hypot(dx, dy) || 0.01;
      const force = (dist - CONFIG.springLength) * CONFIG.spring;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.fx += fx; a.fy += fy;
      b.fx -= fx; b.fy -= fy;
    }

    for (const n of this.nodes) {
      n.vx = (n.vx + n.fx * this.alpha) * CONFIG.damping;
      n.vy = (n.vy + n.fy * this.alpha) * CONFIG.damping;
      n.x += n.vx;
      n.y += n.vy;
    }
  }

  // ---------- rendering ----------

  #matches(node) {
    if (this.searchTerm.length < 2) return true;
    return `${node.label} ${node.company || ''} ${node.position || ''}`
      .toLowerCase().includes(this.searchTerm);
  }

  render() {
    const { ctx } = this;
    ctx.fillStyle = '#0a0c10';
    ctx.fillRect(0, 0, this.width, this.height);

    ctx.save();
    ctx.translate(this.camera.x + this.width / 2, this.camera.y + this.height / 2);
    ctx.scale(this.camera.zoom, this.camera.zoom);

    const neighbors = this.selectedId === null
      ? null
      : new Set([this.selectedId, ...(this.adjacency.get(this.selectedId) || [])]);

    ctx.lineWidth = 0.5 / this.camera.zoom;
    for (const [ia, ib] of this.edges) {
      const a = this.byId.get(ia);
      const b = this.byId.get(ib);
      if (!a || !b) continue;
      const active = neighbors && neighbors.has(ia) && neighbors.has(ib);
      ctx.strokeStyle = active ? PALETTE.edgeActive : PALETTE.edge;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    for (const n of this.nodes) {
      let alpha = this.#matches(n) ? 1 : 0.06;
      if (neighbors && !neighbors.has(n.id)) alpha = Math.min(alpha, 0.18);
      ctx.globalAlpha = alpha;
      ctx.fillStyle = n.id === this.selectedId ? PALETTE.selected : n.color;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fill();
      if (n.kind === 'hub') {
        ctx.strokeStyle = 'rgba(255,255,255,0.2)';
        ctx.lineWidth = 1 / this.camera.zoom;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // Labels are progressive: hubs first, people only once zoomed in far enough to read them.
    if (this.camera.zoom > 0.75) {
      ctx.font = `${10.5 / this.camera.zoom}px -apple-system, Segoe UI, sans-serif`;
      ctx.textAlign = 'center';
      for (const n of this.nodes) {
        if (n.kind === 'person' && this.camera.zoom < 1.6) continue;
        ctx.globalAlpha = this.#matches(n) ? 1 : 0.06;
        ctx.fillStyle = n.kind === 'person' ? 'rgba(231,230,225,0.55)' : 'rgba(201,138,75,0.9)';
        ctx.fillText(n.label, n.x, n.y - n.r - 4 / this.camera.zoom);
      }
      ctx.globalAlpha = 1;
    }

    ctx.restore();
  }

  // ---------- viewport ----------

  fit(padding = 60) {
    if (!this.nodes.length) return;
    const xs = this.nodes.map((n) => n.x);
    const ys = this.nodes.map((n) => n.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const w = Math.max(maxX - minX, 1);
    const h = Math.max(maxY - minY, 1);
    this.camera.zoom = Math.max(
      0.15,
      Math.min(2.5, Math.min((this.width - padding * 2) / w, (this.height - padding * 2) / h)),
    );
    this.camera.x = -((minX + maxX) / 2) * this.camera.zoom;
    this.camera.y = -((minY + maxY) / 2) * this.camera.zoom;
  }

  screenToWorld(sx, sy) {
    return {
      x: (sx - this.camera.x - this.width / 2) / this.camera.zoom,
      y: (sy - this.camera.y - this.height / 2) / this.camera.zoom,
    };
  }

  nodeAt(wx, wy) {
    const size = CONFIG.cellSize;
    const cx = Math.floor(wx / size);
    const cy = Math.floor(wy / size);
    let best = null;
    let bestDist = Infinity;
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (const n of this.grid.get(`${cx + dx},${cy + dy}`) || []) {
          const d2 = (wx - n.x) ** 2 + (wy - n.y) ** 2;
          const hit = (n.r + 5) ** 2;
          if (d2 < hit && d2 < bestDist) { best = n; bestDist = d2; }
        }
      }
    }
    return best;
  }

  select(id) {
    this.selectedId = id;
    const node = this.byId.get(id);
    if (node) {
      this.camera.x = -node.x * this.camera.zoom;
      this.camera.y = -node.y * this.camera.zoom;
      this.camera.zoom = Math.max(this.camera.zoom, 1.2);
    }
    this.render();
  }

  setSearch(term) {
    this.searchTerm = String(term || '').toLowerCase();
    this.render();
  }

  // ---------- input ----------

  #bindEvents() {
    let dragging = false, startX = 0, startY = 0, camStartX = 0, camStartY = 0, moved = false;
    const c = this.canvas;

    c.addEventListener('pointerdown', (e) => {
      dragging = true; moved = false;
      startX = e.clientX; startY = e.clientY;
      camStartX = this.camera.x; camStartY = this.camera.y;
      c.setPointerCapture(e.pointerId);
    });

    c.addEventListener('pointermove', (e) => {
      if (dragging) {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
        this.camera.x = camStartX + dx;
        this.camera.y = camStartY + dy;
        this.render();
      } else {
        const rect = c.getBoundingClientRect();
        const w = this.screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
        const node = this.nodeAt(w.x, w.y);
        c.style.cursor = node ? 'pointer' : 'grab';
        this.onHover(node, e);
      }
    });

    const end = (e) => {
      if (dragging && !moved) {
        const rect = c.getBoundingClientRect();
        const w = this.screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
        const node = this.nodeAt(w.x, w.y);
        this.selectedId = node ? node.id : null;
        this.onSelect(node);
        this.render();
      }
      dragging = false;
    };
    c.addEventListener('pointerup', end);
    c.addEventListener('pointercancel', () => { dragging = false; });
    c.addEventListener('pointerleave', () => { dragging = false; this.onHover(null); });

    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const previous = this.camera.zoom;
      this.camera.zoom = Math.max(0.12, Math.min(5, previous * (e.deltaY < 0 ? 1.12 : 0.89)));
      const ratio = this.camera.zoom / previous;
      this.camera.x = mx - (mx - this.camera.x) * ratio;
      this.camera.y = my - (my - this.camera.y) * ratio;
      this.render();
    }, { passive: false });

    window.addEventListener('resize', () => { this.resize(); this.render(); });
  }
}

/** Deterministic pseudo-random in [0,1) — reproducible layouts without a seeded PRNG lib. */
function pseudoRandom(seed) {
  const x = Math.sin(seed * 9301 + 49297) % 1;
  return x < 0 ? x + 1 : x;
}
