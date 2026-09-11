"""Markdown report rendering.

Turns the analysis document into a self-contained artifact suitable for committing to a
repo, attaching to a PR, or emailing. Rendering is pure string formatting so it can run
anywhere the core runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_markdown(analysis: dict[str, Any], *, title: str = "Network Analysis") -> str:
    ov = analysis["overview"]
    lines: list[str] = [
        f"# {title}",
        "",
        f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"schema {analysis['schema_version']} · {analysis['runtime_ms']:.0f} ms*",
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Connections | {ov['connections']:,} |",
        f"| Distinct employers | {ov['distinct_companies']:,} |",
        f"| Date range | {ov['first_connection']} → {ov['last_connection']} |",
        f"| Span | {ov['span_days'] // 365} years ({ov['span_days']:,} days) |",
        f"| Titles present | {_pct(ov['with_position'] / max(ov['connections'], 1))} |",
        "",
    ]

    findings = analysis.get("insights", [])
    if findings:
        lines += ["## Findings", ""]
        for f in findings:
            lines += [
                f"### {f['title']}",
                f"*{f['kind']} · confidence: {f['confidence']}*",
                "",
                f["detail"],
                "",
            ]

    comp = analysis.get("companies", {})
    if comp.get("available"):
        c = comp["concentration"]
        lines += [
            "## Employer concentration",
            "",
            "| Statistic | Value | Reading |",
            "| --- | --- | --- |",
            f"| Gini | {c['gini']:.3f} | 0 = even, 1 = concentrated |",
            f"| Normalized HHI | {c['hhi_normalized']:.3f} | size-independent concentration |",
            f"| Shannon entropy | {c['shannon_entropy']:.3f} | nats |",
            f"| Pielou evenness | {c['pielou_evenness']:.3f} | H / H-max |",
            f"| Effective employers | {c['effective_companies']:,.0f} | exp(H), Hill order 1 |",
            f"| Top-10 share | {_pct(c['top_10_share'])} | mass in the head |",
            f"| Singleton rate | {_pct(c['singleton_rate'])} | one-person employers |",
            f"| Power-law alpha | {c['powerlaw_alpha'] or 'n/a'} | {c['tail_regime'].replace('_', ' ')} |",
            "",
            "### Largest clusters",
            "",
            "| Employer | Connections |",
            "| --- | --- |",
        ]
        lines += [f"| {e['company']} | {e['count']} |" for e in comp["largest"][:15]]
        lines.append("")

    t = analysis.get("temporal", {})
    if t.get("available"):
        lines += [
            "## Temporal dynamics",
            "",
            f"- Active in {t['active_months']} of {t['total_months']} months "
            f"(duty cycle {_pct(t['duty_cycle'])}).",
            f"- Half the network existed by **{t['accumulation_half_life']}** "
            f"({_pct(t['half_life_elapsed_fraction'])} through the span).",
            f"- Peak month: {t['peak_month']['month']} with {t['peak_month']['count']} connections.",
            f"- {len(t['bursts'])} burst months above a 3.5 modified z-score, carrying "
            f"{_pct(t['burst_share_of_volume'])} of total volume.",
            f"- Velocity: {t['velocity']['trailing_12m']} in trailing 12m vs "
            f"{t['velocity']['prior_12m']} prior ({t['velocity']['direction']}).",
            "",
        ]

    eras = analysis.get("eras", {})
    if eras.get("available"):
        lines += [
            "## Detected eras",
            "",
            "| Window | Connections | Rate/mo | Anchor employer | Distinctive title terms |",
            "| --- | --- | --- | --- | --- |",
        ]
        for e in eras["eras"]:
            anchor = e["top_companies"][0]["company"] if e["top_companies"] else "—"
            terms = ", ".join(t["term"] for t in e["distinctive_terms"][:4]) or "—"
            lines.append(
                f"| {e['start']} → {e['end']} | {e['count']} | {e['rate_per_month']:.1f} | {anchor} | {terms} |"
            )
        lines.append("")

    st = analysis.get("structure", {})
    if st:
        bp, pr = st["bipartite"], st["projection"]
        lines += [
            "## Structure",
            "",
            f"- Observed bipartite layer: {bp['people']:,} people × {bp['companies']:,} employers, "
            f"{bp['edges']:,} affiliation edges.",
            f"- One-mode projection: {pr['edges']:,} implied edges, mean degree "
            f"{pr['mean_degree']:.1f}, largest component {_pct(pr['largest_component_share'])}.",
            f"  - {pr['note']}",
            "",
        ]
        co = st.get("company_cooccurrence", {})
        if co.get("available"):
            lines += [
                f"- Inferred employer adjacency: {co['nodes']} employers, {co['edges']} edges, "
                f"{co['components']} components (method: {co['method']}).",
                "",
            ]

    lines += [
        "---",
        "",
        "*All computation is local. No connection data was transmitted anywhere during analysis.*",
        "",
    ]
    return "\n".join(lines)
