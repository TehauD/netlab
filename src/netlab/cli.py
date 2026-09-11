"""Command line interface.

Three verbs, argparse only (no click/typer dependency):

    netlab serve                     # launch the local UI + API
    netlab analyze FILE [--json|--markdown|--summary]
    netlab sample --out PATH         # emit a synthetic export for demos and tests

`analyze` writes to stdout by default so it composes with shell pipelines:

    netlab analyze Connections.csv --json | jq '.companies.concentration'
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import settings
from .core import NetlabError, analyze_path, render_markdown
from .logging_setup import configure

log = logging.getLogger("netlab.cli")


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Install the server extra:\n"
            "    pip install -e '.[server]'",
            file=sys.stderr,
        )
        return 2

    host = args.host or settings.host
    port = args.port or settings.port
    print(f"\n  netlab {__version__}  →  http://{host}:{port}\n")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("  WARNING: binding beyond loopback exposes an endpoint that ingests\n"
              "           personal contact data. Confirm this is intentional.\n", file=sys.stderr)
    uvicorn.run("netlab.api:app", host=host, port=port, reload=args.reload, log_config=None)
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"No such file: {path}", file=sys.stderr)
        return 2

    try:
        document = analyze_path(
            str(path),
            cluster_by=args.cluster_by,
            redact=args.redact,
            include_graph=args.include_graph,
        )
    except NetlabError as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1

    if args.markdown:
        output = render_markdown(document, title=args.title)
    elif args.summary:
        output = _summarize(document)
    else:
        output = json.dumps(document, indent=2 if args.pretty else None, default=str)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote {args.out} ({len(output):,} bytes)", file=sys.stderr)
    else:
        print(output)
    return 0


def _summarize(document: dict) -> str:
    ov = document["overview"]
    lines = [
        "",
        f"  {ov['connections']:,} connections · {ov['distinct_companies']:,} employers · "
        f"{ov['first_connection']} → {ov['last_connection']}",
        "",
    ]
    for insight in document.get("insights", [])[:8]:
        lines.append(f"  • {insight['title']}  [{insight['confidence']}]")
        lines.append(f"    {insight['detail']}")
        lines.append("")
    lines.append(f"  analyzed in {document['runtime_ms']:.0f} ms — no data left this machine")
    lines.append("")
    return "\n".join(lines)


def _cmd_sample(args: argparse.Namespace) -> int:
    from .sampledata import write_sample

    path = write_sample(args.out, n=args.count, seed=args.seed)
    print(f"Wrote {args.count} synthetic connections to {path}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netlab",
        description="Local-first network analysis for LinkedIn data exports.",
    )
    parser.add_argument("--version", action="version", version=f"netlab {__version__}")
    parser.add_argument("--log-level", default=settings.log_level,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-json", action="store_true", help="Emit structured JSON logs.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the local web UI and API.")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true", help="Auto-reload on code change.")
    serve.set_defaults(func=_cmd_serve)

    analyze = sub.add_parser("analyze", help="Analyze a Connections.csv and print results.")
    analyze.add_argument("file")
    analyze.add_argument("--json", dest="as_json", action="store_true", default=True)
    analyze.add_argument("--markdown", action="store_true", help="Render a Markdown report.")
    analyze.add_argument("--summary", action="store_true", help="Human-readable digest.")
    analyze.add_argument("--pretty", action="store_true", help="Indent JSON output.")
    analyze.add_argument("--out", help="Write to a file instead of stdout.")
    analyze.add_argument("--title", default="Network Analysis")
    analyze.add_argument("--redact", action="store_true",
                         help="Replace names with initials — use for shareable output.")
    analyze.add_argument("--cluster-by", default="company",
                         choices=["company", "year", "function", "seniority", "none"])
    analyze.add_argument("--no-graph", dest="include_graph", action="store_false", default=True)
    analyze.set_defaults(func=_cmd_analyze)

    sample = sub.add_parser("sample", help="Generate a synthetic Connections.csv.")
    sample.add_argument("--out", default="data/sample/Connections.csv")
    sample.add_argument("--count", type=int, default=600)
    sample.add_argument("--seed", type=int, default=42)
    sample.set_defaults(func=_cmd_sample)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure(args.log_level, args.log_json)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except NetlabError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
