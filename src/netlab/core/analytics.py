"""Network analysis over a first-degree LinkedIn export.

## The honest structural framing

A LinkedIn Connections export is **not** a social graph. It contains exactly one hop:
you -> each connection. There are no connection-to-connection edges, because LinkedIn
does not expose second-degree ties through the export or any public API. Any tool that
renders "your network" as a richly interconnected mesh from this file is fabricating the
edges.

What the file genuinely is: a **bipartite affiliation network** of people and employers,
stamped with an acquisition date. That is still analytically rich, so this module works
with the structure that actually exists:

  * `people -> companies`  -- a real, observed bipartite graph.
  * `people -> people`     -- the one-mode projection. Because each person is affiliated
                              with exactly one company in the export, this projection is a
                              disjoint union of cliques. Its graph statistics are therefore
                              computable in closed form, and we do so analytically rather
                              than materializing O(k^2) edges. We report it *and* label the
                              limitation instead of dressing it up as emergent structure.
  * `company -> company`   -- an *inferred* graph from temporal co-occurrence: two employers
                              are linked when new connections from both appeared in the same
                              month, repeatedly. This is the only genuinely non-trivial
                              structure recoverable from the data, and it tends to surface
                              real-world context (a job change, a conference, a project).

Every inferred quantity is labeled `inferred` in the output so an analyst can separate
observation from construction.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

from . import metrics
from .models import SENIORITY_LADDER, Connection, ParseReport
from .normalize import resolution_gain

log = logging.getLogger(__name__)

MIN_ERA_SIZE_FLOOR = 5
BURST_Z_THRESHOLD = 3.5
COOCCURRENCE_MIN_WEIGHT = 2
COOCCURRENCE_MIN_COMPANY_SIZE = 2

_TOKEN = re.compile(r"[a-z][a-z+#.]{2,}")
_TITLE_STOPWORDS = frozenset(
    """the and for of at in to with a an on by from is are as senior sr jr ii iii
    new global north south east west world group team dept department""".split()
)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_range(start: date, end: date) -> list[str]:
    """Dense month index so a chart never silently hides a gap of zero activity."""
    keys, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return keys


def _dated(connections: Sequence[Connection]) -> list[Connection]:
    return sorted((c for c in connections if c.connected_on), key=lambda c: c.connected_on)  # type: ignore[arg-type,return-value]


def _share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


# --------------------------------------------------------------------------------------
# Section: overview + data quality
# --------------------------------------------------------------------------------------

def overview(connections: Sequence[Connection]) -> dict[str, Any]:
    dated = _dated(connections)
    companies = [c.company for c in connections if c.company]
    return {
        "connections": len(connections),
        "distinct_companies": len(set(companies)),
        "with_company": len(companies),
        "with_position": sum(1 for c in connections if c.position),
        "with_date": len(dated),
        "first_connection": dated[0].connected_on.isoformat() if dated else None,
        "last_connection": dated[-1].connected_on.isoformat() if dated else None,
        "span_days": (dated[-1].connected_on - dated[0].connected_on).days if len(dated) > 1 else 0,
    }


def data_quality(connections: Sequence[Connection], report: ParseReport) -> dict[str, Any]:
    """Ingest fidelity + what entity resolution actually merged.

    Exposed prominently because every downstream metric inherits this ceiling.
    """
    gain = resolution_gain(connections)
    return {
        "ingest": report.to_dict(),
        "entity_resolution": gain,
        "resolution_merge_rate": _share(gain["merged"], max(gain["raw_distinct"], 1)),
    }


# --------------------------------------------------------------------------------------
# Section: employer concentration
# --------------------------------------------------------------------------------------

def company_profile(connections: Sequence[Connection], top_n: int = 25) -> dict[str, Any]:
    counts = Counter(c.company for c in connections if c.company)
    if not counts:
        return {"available": False, "reason": "No company values present in this export."}

    sizes = list(counts.values())
    singletons = sum(1 for v in sizes if v == 1)
    alpha = metrics.powerlaw_alpha(sizes)

    return {
        "available": True,
        "distinct": len(counts),
        "largest": [{"company": k, "count": v} for k, v in counts.most_common(top_n)],
        "size_distribution": dict(sorted(Counter(sizes).items())),
        "concentration": {
            "gini": metrics.gini(sizes),
            "hhi_normalized": metrics.hhi(sizes),
            "shannon_entropy": metrics.shannon_entropy(sizes),
            "pielou_evenness": metrics.pielou_evenness(sizes),
            "effective_companies": metrics.effective_count(sizes),
            "top_10_share": metrics.top_k_share(sizes, 10),
            "singleton_rate": _share(singletons, len(counts)),
            "powerlaw_alpha": alpha,
            "tail_regime": _tail_regime(alpha),
        },
        "median_cluster_size": metrics.median(sizes),
        "p95_cluster_size": round(metrics.percentile(sizes, 95), 2),
    }


def _tail_regime(alpha: float | None) -> str:
    if alpha is None:
        return "insufficient_data"
    if alpha < 2.0:
        return "extreme_hub_dominance"
    if alpha < 3.0:
        return "heavy_tailed"
    return "thin_tailed"


# --------------------------------------------------------------------------------------
# Section: temporal dynamics
# --------------------------------------------------------------------------------------

def temporal_profile(connections: Sequence[Connection]) -> dict[str, Any]:
    dated = _dated(connections)
    if len(dated) < 2:
        return {"available": False, "reason": "Fewer than two parseable connection dates."}

    first, last = dated[0].connected_on, dated[-1].connected_on
    assert first and last

    monthly_counts = Counter(_month_key(c.connected_on) for c in dated)  # type: ignore[arg-type]
    index = _month_range(first, last)
    series = [{"month": k, "count": monthly_counts.get(k, 0)} for k in index]
    values = [p["count"] for p in series]

    zs = metrics.modified_zscores(values)
    bursts = [
        {"month": series[i]["month"], "count": values[i], "z": zs[i]}
        for i in range(len(series))
        if zs[i] >= BURST_Z_THRESHOLD
    ]

    yearly = Counter(c.connected_on.year for c in dated)  # type: ignore[union-attr]
    years_sorted = sorted(yearly)

    # Accumulation half-life: the date by which half the network had been formed.
    half_target = len(dated) / 2
    running, half_life = 0, None
    for c in dated:
        running += 1
        if running >= half_target:
            half_life = c.connected_on
            break

    dormancy = _longest_dormancy(dated)
    trailing = _velocity(dated, last)

    return {
        "available": True,
        "monthly": series,
        "yearly": [{"year": y, "count": yearly[y]} for y in years_sorted],
        "active_months": sum(1 for v in values if v > 0),
        "total_months": len(values),
        "duty_cycle": _share(sum(1 for v in values if v > 0), len(values)),
        "median_month": metrics.median(values),
        "peak_month": max(series, key=lambda p: p["count"]) if series else None,
        "bursts": bursts,
        "burst_share_of_volume": _share(sum(b["count"] for b in bursts), len(dated)),
        "accumulation_half_life": half_life.isoformat() if half_life else None,
        "half_life_elapsed_fraction": _share_of_span(first, last, half_life),
        "longest_dormancy": dormancy,
        "velocity": trailing,
    }


def _longest_dormancy(dated: Sequence[Connection]) -> dict[str, Any] | None:
    best = None
    for prev, cur in zip(dated, dated[1:]):
        gap = (cur.connected_on - prev.connected_on).days  # type: ignore[operator]
        if best is None or gap > best["days"]:
            best = {
                "days": gap,
                "from": prev.connected_on.isoformat(),  # type: ignore[union-attr]
                "to": cur.connected_on.isoformat(),  # type: ignore[union-attr]
            }
    return best


def _velocity(dated: Sequence[Connection], last: date) -> dict[str, Any]:
    """Trailing-12 vs prior-12 month rate. A directional read on networking cadence."""
    cutoff_recent = last - timedelta(days=365)
    cutoff_prior = last - timedelta(days=730)
    recent = sum(1 for c in dated if c.connected_on and c.connected_on > cutoff_recent)
    prior = sum(1 for c in dated if c.connected_on and cutoff_prior < c.connected_on <= cutoff_recent)
    if prior == 0:
        change = None
    else:
        change = round((recent - prior) / prior, 4)
    return {
        "trailing_12m": recent,
        "prior_12m": prior,
        "pct_change": change,
        "direction": "expanding" if change is not None and change > 0.1
        else "contracting" if change is not None and change < -0.1
        else "steady",
    }


def _share_of_span(first: date, last: date, point: date | None) -> float | None:
    if point is None or last == first:
        return None
    return round((point - first).days / (last - first).days, 4)


# --------------------------------------------------------------------------------------
# Section: seniority and function composition
# --------------------------------------------------------------------------------------

def composition_profile(connections: Sequence[Connection]) -> dict[str, Any]:
    classified = [c for c in connections if c.seniority != "unknown"]
    seniority_counts = Counter(c.seniority for c in connections)
    function_counts = Counter(c.function for c in connections)

    known_functions = {k: v for k, v in function_counts.items() if k != "unclassified"}
    modal_function = max(known_functions, key=lambda k: known_functions[k]) if known_functions else None

    drift = _seniority_drift(connections)

    return {
        "seniority": {
            "distribution": [
                {"tier": tier, "count": seniority_counts.get(tier, 0), "rank": i}
                for i, tier in enumerate(SENIORITY_LADDER)
            ],
            "classified_rate": _share(len(classified), len(connections)),
            "mean_rank": round(
                sum(c.seniority_rank for c in classified) / len(classified), 3
            ) if classified else 0.0,
            "leadership_share": _share(
                sum(1 for c in connections if c.seniority in
                    {"manager", "director", "executive", "founder_owner"}),
                max(len(classified), 1),
            ),
            "drift": drift,
        },
        "function": {
            "distribution": [
                {"function": k, "count": v}
                for k, v in sorted(function_counts.items(), key=lambda kv: -kv[1])
            ],
            "entropy": metrics.shannon_entropy(list(known_functions.values())),
            "evenness": metrics.pielou_evenness(list(known_functions.values())),
            "effective_functions": metrics.effective_count(list(known_functions.values())),
            "modal": modal_function,
            "homophily_index": _share(
                known_functions.get(modal_function, 0), sum(known_functions.values())
            ) if modal_function else None,
        },
    }


def _seniority_drift(connections: Sequence[Connection]) -> dict[str, Any]:
    """Regress mean seniority rank on connection year.

    Interpretation: a positive slope means newer connections skew more senior than older
    ones -- the signature of a network maturing alongside a career. r_squared is reported
    so a noisy fit is not read as a trend.
    """
    by_year: dict[int, list[int]] = defaultdict(list)
    for c in connections:
        if c.connected_on and c.seniority != "unknown":
            by_year[c.connected_on.year].append(c.seniority_rank)

    points = [
        {"year": y, "mean_rank": round(sum(v) / len(v), 3), "n": len(v)}
        for y, v in sorted(by_year.items())
        if len(v) >= 3
    ]
    if len(points) < 3:
        return {"available": False, "reason": "Fewer than three years with sufficient data.",
                "by_year": points}

    slope, intercept, r2 = metrics.ols_slope(
        [p["year"] for p in points], [p["mean_rank"] for p in points]
    )
    return {
        "available": True,
        "by_year": points,
        "slope_rank_per_year": slope,
        "intercept": intercept,
        "r_squared": r2,
        "interpretation": "rising" if slope > 0.02 and r2 > 0.3
        else "falling" if slope < -0.02 and r2 > 0.3
        else "flat",
    }


# --------------------------------------------------------------------------------------
# Section: graph structure
# --------------------------------------------------------------------------------------

def structure_profile(connections: Sequence[Connection]) -> dict[str, Any]:
    counts = Counter(c.company for c in connections if c.company)
    n_people = len(connections)
    n_companies = len(counts)
    affiliations = sum(counts.values())

    # --- Observed bipartite layer -------------------------------------------------
    bipartite = {
        "people": n_people,
        "companies": n_companies,
        "edges": affiliations,
        "density": round(affiliations / (n_people * n_companies), 6) if n_people and n_companies else 0.0,
        "unaffiliated_people": n_people - affiliations,
    }

    # --- One-mode projection, computed in closed form -----------------------------
    # Each person belongs to one company, so the projection is a disjoint union of
    # cliques. Materializing it would be O(sum k^2) edges for zero informational gain.
    sizes = list(counts.values())
    proj_edges = sum(k * (k - 1) // 2 for k in sizes)
    degree_sum = sum(k * (k - 1) for k in sizes)
    possible = n_people * (n_people - 1) / 2 if n_people > 1 else 0
    projection = {
        "note": "Disjoint union of cliques -- each person has exactly one employer in the "
                "export, so components are companies by construction. Reported for "
                "completeness, not as discovered structure.",
        "edges": proj_edges,
        "mean_degree": round(degree_sum / n_people, 3) if n_people else 0.0,
        "max_degree": (max(sizes) - 1) if sizes else 0,
        "density": round(proj_edges / possible, 6) if possible else 0.0,
        "components": n_companies + (n_people - affiliations),
        "largest_component_share": _share(max(sizes), n_people) if sizes else 0.0,
        "isolate_share": _share(
            (n_people - affiliations) + sum(1 for k in sizes if k == 1), n_people
        ),
    }

    cooccurrence = company_cooccurrence(connections, counts)

    return {"bipartite": bipartite, "projection": projection, "company_cooccurrence": cooccurrence}


def company_cooccurrence(
    connections: Sequence[Connection],
    counts: Counter | None = None,
    min_weight: int = COOCCURRENCE_MIN_WEIGHT,
) -> dict[str, Any]:
    """INFERRED company-to-company graph built from temporal co-occurrence.

    Hypothesis: when connections from two different employers enter the network in the
    same month, repeatedly, those employers share a real-world context -- a conference, a
    client engagement, a team that dispersed, a hiring wave. This is the only non-trivial
    topology recoverable from a single-hop export, and it is explicitly an inference.
    """
    counts = counts or Counter(c.company for c in connections if c.company)
    eligible = {k for k, v in counts.items() if v >= COOCCURRENCE_MIN_COMPANY_SIZE}
    if len(eligible) < 2:
        return {"available": False, "reason": "Too few multi-person employers to infer co-occurrence."}

    by_month: dict[str, set[str]] = defaultdict(set)
    for c in connections:
        if c.connected_on and c.company in eligible:
            by_month[_month_key(c.connected_on)].add(c.company)

    weights: Counter[tuple[str, str]] = Counter()
    for companies in by_month.values():
        ordered = sorted(companies)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                weights[(ordered[i], ordered[j])] += 1

    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in weights.items()
        if w >= min_weight
    ]
    if not edges:
        return {
            "available": False,
            "reason": f"No employer pair co-occurred in at least {min_weight} distinct months.",
            "candidate_companies": len(eligible),
        }

    degree: Counter[str] = Counter()
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1

    components = _components([(e["source"], e["target"]) for e in edges])
    nodes_in_graph = len(degree)
    possible = nodes_in_graph * (nodes_in_graph - 1) / 2

    return {
        "available": True,
        "inferred": True,
        "method": "monthly co-occurrence of newly added connections",
        "min_weight": min_weight,
        "nodes": nodes_in_graph,
        "edges": len(edges),
        "density": round(len(edges) / possible, 6) if possible else 0.0,
        "components": len(components),
        "largest_component": max((len(c) for c in components), default=0),
        "top_edges": sorted(edges, key=lambda e: -e["weight"])[:30],
        "bridges": [
            {"company": k, "degree": v, "size": counts[k]}
            for k, v in degree.most_common(15)
        ],
    }


def _components(edges: Sequence[tuple[str, str]]) -> list[set[str]]:
    """Connected components via union-find with path compression."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    groups: dict[str, set[str]] = defaultdict(set)
    for node in list(parent):
        groups[find(node)].add(node)
    return list(groups.values())


# --------------------------------------------------------------------------------------
# Section: career eras (unsupervised temporal segmentation)
# --------------------------------------------------------------------------------------

@dataclass(slots=True)
class Era:
    start: date
    end: date
    members: list[Connection]


def detect_eras(connections: Sequence[Connection]) -> dict[str, Any]:
    """Segment the timeline into 'chapters' using gap-based 1-D change detection.

    Method: sort by connection date, compute inter-arrival gaps, and cut wherever a gap
    exceeds max(45 days, 3 x median gap). Undersized fragments are merged forward. This is
    a non-parametric alternative to k-means on dates -- no k to choose, and the cut points
    correspond to real dormancy rather than to an arbitrary cluster count.
    """
    dated = _dated(connections)
    if len(dated) < 12:
        return {"available": False, "reason": "Fewer than twelve dated connections."}

    gaps = [
        (cur.connected_on - prev.connected_on).days  # type: ignore[operator]
        for prev, cur in zip(dated, dated[1:])
    ]
    threshold = max(45.0, 3 * metrics.median(gaps))
    min_size = max(MIN_ERA_SIZE_FLOOR, int(len(dated) * 0.02))

    segments: list[list[Connection]] = [[dated[0]]]
    for gap, conn in zip(gaps, dated[1:]):
        if gap > threshold and len(segments[-1]) >= min_size:
            segments.append([conn])
        else:
            segments[-1].append(conn)

    # Merge any trailing undersized segment back into its predecessor.
    merged: list[list[Connection]] = []
    for seg in segments:
        if merged and len(seg) < min_size:
            merged[-1].extend(seg)
        else:
            merged.append(seg)

    global_tokens = _token_counts(dated)
    eras = [
        _describe_era(Era(seg[0].connected_on, seg[-1].connected_on, seg), global_tokens, len(dated))  # type: ignore[arg-type]
        for seg in merged
    ]
    return {
        "available": True,
        "method": "gap-based segmentation",
        "gap_threshold_days": round(threshold, 1),
        "min_segment_size": min_size,
        "count": len(eras),
        "eras": eras,
    }


def _token_counts(connections: Iterable[Connection]) -> Counter[str]:
    tokens: Counter[str] = Counter()
    for c in connections:
        for t in _TOKEN.findall(c.position.lower()):
            if t not in _TITLE_STOPWORDS:
                tokens[t] += 1
    return tokens


def _describe_era(era: Era, global_tokens: Counter[str], global_n: int) -> dict[str, Any]:
    companies = Counter(c.company for c in era.members if c.company)
    functions = Counter(c.function for c in era.members if c.function != "unclassified")
    ranks = [c.seniority_rank for c in era.members if c.seniority != "unknown"]
    span_days = max((era.end - era.start).days, 1)

    return {
        "start": era.start.isoformat(),
        "end": era.end.isoformat(),
        "span_days": span_days,
        "count": len(era.members),
        "rate_per_month": round(len(era.members) / (span_days / 30.44), 2),
        "top_companies": [{"company": k, "count": v} for k, v in companies.most_common(5)],
        "top_functions": [{"function": k, "count": v} for k, v in functions.most_common(4)],
        "mean_seniority_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "distinctive_terms": _distinctive_terms(era.members, global_tokens, global_n),
    }


def _distinctive_terms(
    members: Sequence[Connection], global_tokens: Counter[str], global_n: int, k: int = 6
) -> list[dict[str, Any]]:
    """Log-odds ratio with add-one smoothing -- terms over-represented inside this era.

    Preferred over raw frequency because raw frequency just returns "engineer" for every
    segment of a technologist's network.
    """
    local = _token_counts(members)
    local_total = max(sum(local.values()), 1)
    global_total = max(sum(global_tokens.values()), 1)
    scored: list[tuple[float, str, int]] = []
    for term, count in local.items():
        if count < 2:
            continue
        p_local = (count + 1) / (local_total + 2)
        p_global = (global_tokens.get(term, 0) + 1) / (global_total + 2)
        scored.append((math.log(p_local / p_global), term, count))
    scored.sort(reverse=True)
    return [{"term": t, "count": c, "log_odds": round(s, 3)} for s, t, c in scored[:k]]


# --------------------------------------------------------------------------------------
# Visualization payload
# --------------------------------------------------------------------------------------

def graph_payload(
    connections: Sequence[Connection],
    cluster_by: str = "company",
    redact: bool = False,
    max_nodes: int = 6000,
) -> dict[str, Any]:
    """Emit a render-ready bipartite node/edge payload for the canvas front end."""
    if cluster_by not in {"company", "year", "function", "seniority", "none"}:
        cluster_by = "company"

    people = list(connections)[:max_nodes]
    truncated = len(connections) > len(people)

    nodes: list[dict[str, Any]] = []
    edges: list[list[int]] = []
    hub_index: dict[str, int] = {}
    hub_members: dict[int, list[str]] = defaultdict(list)

    for i, c in enumerate(people):
        nodes.append(
            {
                "id": i,
                "kind": "person",
                "label": c.to_public_dict(redact)["name"],
                **{k: v for k, v in c.to_public_dict(redact).items() if k != "name"},
            }
        )

    def hub_key(c: Connection) -> str:
        if cluster_by == "company":
            return c.company
        if cluster_by == "year":
            return str(c.connected_on.year) if c.connected_on else "Undated"
        if cluster_by == "function":
            return c.function
        if cluster_by == "seniority":
            return c.seniority
        return ""

    if cluster_by != "none":
        next_id = len(nodes)
        for i, c in enumerate(people):
            key = hub_key(c)
            if not key:
                continue
            if key not in hub_index:
                hub_index[key] = next_id
                nodes.append({"id": next_id, "kind": "hub", "label": key, "members": 0})
                next_id += 1
            hid = hub_index[key]
            hub_members[hid].append(nodes[i]["label"])
            edges.append([i, hid])
        for hid, members in hub_members.items():
            node = next(n for n in nodes if n["id"] == hid)
            node["members"] = len(members)
            node["sample"] = members[:60]

    return {
        "cluster_by": cluster_by,
        "redacted": redact,
        "truncated": truncated,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
