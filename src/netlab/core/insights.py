"""Deterministic insight generation.

No language model, no randomness: each insight is a rule over computed statistics, so the
same export always produces the same narrative. That property is what makes the output
safe to drop into a scheduled pipeline or a report artifact.

Each insight carries a `confidence` derived from the sample size or fit quality behind it,
and a `kind` so the UI can rank and filter. Insights that would be misleading at low n are
suppressed rather than hedged.
"""

from __future__ import annotations

from typing import Any

Insight = dict[str, Any]


def _mk(title: str, detail: str, kind: str, confidence: str, evidence: dict[str, Any]) -> Insight:
    return {
        "title": title,
        "detail": detail,
        "kind": kind,
        "confidence": confidence,
        "evidence": evidence,
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def generate(analysis: dict[str, Any]) -> list[Insight]:
    """Produce a ranked list of findings from a completed analysis document."""
    out: list[Insight] = []
    ov = analysis.get("overview", {})
    n = ov.get("connections", 0)
    if n == 0:
        return out

    out += _concentration_insights(analysis, n)
    out += _temporal_insights(analysis, n)
    out += _composition_insights(analysis, n)
    out += _structure_insights(analysis)
    out += _era_insights(analysis)
    out += _quality_insights(analysis, n)

    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda i: (order.get(i["confidence"], 3), i["kind"]))
    return out


# --------------------------------------------------------------------------------------

def _concentration_insights(analysis: dict[str, Any], n: int) -> list[Insight]:
    comp = analysis.get("companies", {})
    if not comp.get("available"):
        return []
    c = comp["concentration"]
    out: list[Insight] = []

    effective = c["effective_companies"]
    out.append(
        _mk(
            "Your network is narrower than the headline count suggests",
            f"{comp['distinct']:,} distinct employers appear, but the entropy-adjusted "
            f"effective count is {effective:,.0f}. The top 10 employers hold "
            f"{_pct(c['top_10_share'])} of all affiliations "
            f"(Gini {c['gini']:.2f}, normalized HHI {c['hhi_normalized']:.3f}).",
            kind="concentration",
            confidence="high" if n >= 150 else "medium",
            evidence={"effective_companies": effective, "gini": c["gini"],
                      "top_10_share": c["top_10_share"]},
        )
    )

    if c["singleton_rate"] >= 0.5:
        out.append(
            _mk(
                "Half your employer graph is single-person outposts",
                f"{_pct(c['singleton_rate'])} of employers are represented by exactly one "
                "connection. These are weak-tie bridges in Granovetter's sense: they carry "
                "the non-redundant information your dense clusters cannot.",
                kind="structure",
                confidence="high" if n >= 100 else "medium",
                evidence={"singleton_rate": c["singleton_rate"]},
            )
        )

    regime = c["tail_regime"]
    if regime in {"heavy_tailed", "extreme_hub_dominance"} and c["powerlaw_alpha"]:
        out.append(
            _mk(
                "Employer cluster sizes follow a heavy-tailed regime",
                f"Fitted power-law exponent alpha = {c['powerlaw_alpha']}, consistent with "
                f"a distribution regime of {regime.replace('_', ' ')}: a handful of employers "
                "dominate "
                "while the long tail thins out quickly. Networks assembled through a small "
                "number of workplaces look like this.",
                kind="distribution",
                confidence="medium",
                evidence={"alpha": c["powerlaw_alpha"], "regime": regime},
            )
        )
    return out


def _temporal_insights(analysis: dict[str, Any], n: int) -> list[Insight]:
    t = analysis.get("temporal", {})
    if not t.get("available"):
        return []
    out: list[Insight] = []

    frac = t.get("half_life_elapsed_fraction")
    if frac is not None and t.get("accumulation_half_life"):
        if frac <= 0.35:
            phrasing = "front-loaded -- most of your network was built early and has since plateaued"
        elif frac >= 0.65:
            phrasing = "back-loaded -- your network has accelerated in recent years"
        else:
            phrasing = "roughly linear -- accumulation has been steady across the span"
        out.append(
            _mk(
                "Network accumulation is " + phrasing.split(" -- ")[0],
                f"Half of all connections existed by {t['accumulation_half_life']}, which is "
                f"{_pct(frac)} of the way through your {analysis['overview']['span_days'] // 365} "
                f"year span. Growth is {phrasing}.",
                kind="temporal",
                confidence="high",
                evidence={"half_life": t["accumulation_half_life"], "elapsed_fraction": frac},
            )
        )

    bursts = t.get("bursts", [])
    if bursts:
        top = max(bursts, key=lambda b: b["count"])
        out.append(
            _mk(
                f"{len(bursts)} statistically anomalous networking months",
                f"Months exceeding a modified z-score of 3.5 against the median account for "
                f"{_pct(t['burst_share_of_volume'])} of all connections. The largest was "
                f"{top['month']} with {top['count']} new connections (z = {top['z']}). "
                "Bursts of this shape usually map to a job change, a conference, or an "
                "onboarding cohort.",
                kind="temporal",
                confidence="high" if n >= 100 else "medium",
                evidence={"bursts": bursts[:5]},
            )
        )

    v = t.get("velocity", {})
    if v.get("prior_12m"):
        out.append(
            _mk(
                f"Connection velocity is {v['direction']}",
                f"{v['trailing_12m']} connections in the trailing 12 months versus "
                f"{v['prior_12m']} in the prior 12 -- a change of {_pct(v['pct_change'])}.",
                kind="temporal",
                confidence="medium",
                evidence=v,
            )
        )

    dc = t.get("duty_cycle", 0)
    if dc < 0.5:
        out.append(
            _mk(
                "Networking is episodic, not continuous",
                f"Only {_pct(dc)} of months in your active span contain any new connection "
                f"({t['active_months']} of {t['total_months']}). The longest dormant stretch "
                f"ran {t['longest_dormancy']['days']} days.",
                kind="temporal",
                confidence="high",
                evidence={"duty_cycle": dc, "dormancy": t.get("longest_dormancy")},
            )
        )
    return out


def _composition_insights(analysis: dict[str, Any], n: int) -> list[Insight]:
    comp = analysis.get("composition", {})
    if not comp:
        return []
    out: list[Insight] = []
    sen, fn = comp["seniority"], comp["function"]

    if sen["classified_rate"] >= 0.4:
        out.append(
            _mk(
                f"{_pct(sen['leadership_share'])} of classified titles sit at manager level or above",
                f"Mean position on the 8-step seniority ladder is {sen['mean_rank']:.2f}. "
                f"Titles were classifiable for {_pct(sen['classified_rate'])} of connections; "
                "the remainder are free-text titles that no rule set resolves cleanly.",
                kind="composition",
                confidence="high" if n >= 150 else "medium",
                evidence={"leadership_share": sen["leadership_share"], "mean_rank": sen["mean_rank"]},
            )
        )

    drift = sen.get("drift", {})
    if drift.get("available") and drift["interpretation"] != "flat":
        direction = "more senior" if drift["interpretation"] == "rising" else "more junior"
        out.append(
            _mk(
                f"New connections are trending {direction} over time",
                f"Regressing mean seniority rank on connection year yields a slope of "
                f"{drift['slope_rank_per_year']:+.3f} ladder-steps per year "
                f"(R-squared = {drift['r_squared']:.2f}). Interpret alongside the fit quality: "
                "a low R-squared means year-to-year noise, not a trend.",
                kind="composition",
                confidence="medium" if drift["r_squared"] > 0.5 else "low",
                evidence=drift,
            )
        )

    if fn["modal"] and fn["homophily_index"]:
        out.append(
            _mk(
                f"Functional homophily: {_pct(fn['homophily_index'])} concentrated in {fn['modal'].replace('_', ' ')}",
                f"Functional diversity sits at {fn['evenness']:.2f} on the Pielou evenness scale "
                f"({fn['effective_functions']:.1f} effective functions out of "
                f"{len(fn['distribution'])} observed). High homophily means deep domain access "
                "and thin cross-domain reach -- the classic structural-hole trade-off.",
                kind="composition",
                confidence="high" if n >= 150 else "medium",
                evidence={"modal": fn["modal"], "homophily": fn["homophily_index"],
                          "evenness": fn["evenness"]},
            )
        )
    return out


def _structure_insights(analysis: dict[str, Any]) -> list[Insight]:
    st = analysis.get("structure", {})
    if not st:
        return []
    out: list[Insight] = []
    co = st.get("company_cooccurrence", {})
    if co.get("available"):
        top = co["top_edges"][0] if co["top_edges"] else None
        detail = (
            f"{co['edges']} employer pairs co-occurred in at least {co['min_weight']} distinct "
            f"months, spanning {co['nodes']} employers across {co['components']} "
            f"component{'' if co['components'] == 1 else 's'}."
        )
        if top:
            detail += (
                f" The strongest link is {top['source']} <-> {top['target']} "
                f"({top['weight']} shared months)."
            )
        out.append(
            _mk(
                "Inferred employer adjacency from temporal co-occurrence",
                detail + " This layer is inferred, not observed -- treat it as a hypothesis "
                "generator for shared real-world context, not as fact.",
                kind="structure",
                confidence="medium",
                evidence={"edges": co["edges"], "top": co["top_edges"][:3]},
            )
        )

    proj = st.get("projection", {})
    if proj:
        out.append(
            _mk(
                "The one-hop export ceiling",
                f"The person-to-person projection resolves to {proj['components']} disjoint "
                f"cliques with a mean degree of {proj['mean_degree']:.1f}, because each person "
                "carries exactly one employer. Genuine second-degree topology is simply not "
                "present in this file -- any tool showing it is inventing edges.",
                kind="methodology",
                confidence="high",
                evidence={"components": proj["components"], "mean_degree": proj["mean_degree"]},
            )
        )
    return out


def _era_insights(analysis: dict[str, Any]) -> list[Insight]:
    eras = analysis.get("eras", {})
    if not eras.get("available") or eras["count"] < 2:
        return []
    segments = eras["eras"]
    busiest = max(segments, key=lambda e: e["rate_per_month"])
    terms = ", ".join(t["term"] for t in busiest["distinctive_terms"][:4]) or "no distinctive terms"
    top_co = busiest["top_companies"][0]["company"] if busiest["top_companies"] else "n/a"
    return [
        _mk(
            f"{eras['count']} distinct networking chapters detected",
            f"Gap-based segmentation (cut threshold {eras['gap_threshold_days']:.0f} days) splits "
            f"your timeline into {eras['count']} eras. The densest ran "
            f"{busiest['start']} to {busiest['end']} at {busiest['rate_per_month']:.1f} "
            f"connections/month, centered on {top_co}. Titles distinctive to that window: {terms}.",
            kind="temporal",
            confidence="medium",
            evidence={"count": eras["count"], "busiest": busiest["start"]},
        )
    ]


def _quality_insights(analysis: dict[str, Any], n: int) -> list[Insight]:
    dq = analysis.get("data_quality", {})
    if not dq:
        return []
    out: list[Insight] = []
    er = dq["entity_resolution"]
    if er["merged"] > 0:
        out.append(
            _mk(
                f"Entity resolution merged {er['merged']} duplicate employer strings",
                f"{er['raw_distinct']} raw company strings collapsed to {er['canonical_distinct']} "
                f"canonical employers ({_pct(dq['resolution_merge_rate'])} reduction). Without this "
                "pass, concentration metrics would be understated and clusters fragmented.",
                kind="data_quality",
                confidence="high",
                evidence=er,
            )
        )
    completeness = dq["ingest"].get("completeness", {})
    weak = [k for k, v in completeness.items() if v < 0.85]
    if weak:
        out.append(
            _mk(
                "Field completeness limits some metrics",
                "Below 85% populated: " + ", ".join(
                    f"{k} ({_pct(completeness[k])})" for k in weak
                ) + ". Metrics derived from these fields inherit that ceiling.",
                kind="data_quality",
                confidence="high",
                evidence=completeness,
            )
        )
    return out
