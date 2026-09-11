"""Local HTTP API.

Design constraints that shaped this module:

* **Stateless by construction.** Uploaded bytes live in the request scope and are dropped
  when the response is written. There is no database, no cache, no temp file. Nothing to
  leak, nothing to purge.
* **Loopback by default.** `NETLAB_HOST` defaults to 127.0.0.1. Binding elsewhere emits a
  startup warning, because exposing an endpoint that ingests a contact list to a LAN is a
  decision that should be made consciously.
* **No outbound calls.** The process never opens an egress connection. This is the property
  that makes the privacy claim in the README verifiable rather than aspirational.

The browser can also run fully offline against the bundled JavaScript parser; the API
exists for the richer statistics that are not worth reimplementing in the client.
"""

from __future__ import annotations

import csv
import io
import logging
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import settings
from .core import SCHEMA_VERSION, NetlabError, ParseError, analyze_bytes, render_markdown
from .logging_setup import configure

log = logging.getLogger("netlab.api")
WEB_DIR = Path(__file__).parent / "web"

CLUSTER_MODES = {"company", "year", "function", "seniority", "none"}


# --------------------------------------------------------------------------------------
# Response contracts (documented in the generated OpenAPI schema at /docs)
# --------------------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str
    schema_version: str
    redact_by_default: bool
    max_upload_mb: int
    persistence_enabled: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str
    correlation_id: str


def create_app() -> FastAPI:
    configure(settings.log_level, settings.log_json)

    app = FastAPI(
        title="netlab",
        version=__version__,
        summary="Local-first network analysis for LinkedIn data exports.",
        description=(
            "Every endpoint is stateless. Uploaded files are parsed in memory and discarded "
            "with the request. The service makes no outbound network calls."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def correlate(request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:12]
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - started) * 1000
        response.headers["x-correlation-id"] = correlation_id
        # Path and status only -- never payload contents.
        log.info(
            "http method=%s path=%s status=%d ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            extra={"correlation_id": correlation_id},
        )
        return response

    @app.on_event("startup")
    async def announce() -> None:
        log.info("netlab %s listening on http://%s:%d", __version__, settings.host, settings.port)
        if settings.binds_publicly:
            log.warning(
                "SECURITY: bound to %s rather than loopback. This endpoint ingests personal "
                "contact data -- confirm this exposure is intentional.",
                settings.host,
            )

    @app.exception_handler(NetlabError)
    async def handle_domain_error(request: Request, exc: NetlabError) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", "-")
        log.warning("domain_error %s", type(exc).__name__, extra={"correlation_id": cid})
        return JSONResponse(
            status_code=422,
            content={"error": type(exc).__name__, "detail": str(exc), "correlation_id": cid},
        )

    # ----------------------------------------------------------------------------------
    # Endpoints
    # ----------------------------------------------------------------------------------

    @app.get("/api/health", response_model=HealthResponse, tags=["meta"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            schema_version=SCHEMA_VERSION,
            redact_by_default=settings.redact_by_default,
            max_upload_mb=settings.max_upload_mb,
            persistence_enabled=settings.allow_persistence,
        )

    async def _read_upload(file: UploadFile) -> bytes:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {settings.max_upload_mb} MB limit.",
            )
        return raw

    @app.post("/api/analyze", tags=["analysis"], responses={422: {"model": ErrorResponse}})
    async def analyze_endpoint(
        request: Request,
        file: Annotated[UploadFile, File(description="Connections.csv from the LinkedIn export")],
        cluster_by: Annotated[str, Form()] = "company",
        redact: Annotated[bool, Form()] = False,
        include_graph: Annotated[bool, Form()] = True,
    ) -> dict[str, Any]:
        """Parse and analyze an export. Returns the full analysis document."""
        if cluster_by not in CLUSTER_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"cluster_by must be one of {sorted(CLUSTER_MODES)}.",
            )
        raw = await _read_upload(file)
        cid = getattr(request.state, "correlation_id", "-")
        log.info("analyze_start bytes=%d cluster_by=%s", len(raw), cluster_by,
                 extra={"correlation_id": cid})
        document = analyze_bytes(
            raw,
            cluster_by=cluster_by,
            redact=redact or settings.redact_by_default,
            include_graph=include_graph,
        )
        document["correlation_id"] = cid
        return document

    @app.get("/api/sample", response_class=PlainTextResponse, tags=["meta"])
    async def sample_endpoint(count: int = 600, seed: int = 42) -> PlainTextResponse:
        """Synthetic export for demos and first-run exploration.

        Generated in memory on every call -- nothing is read from or written to disk.
        """
        from .sampledata import generate

        count = max(50, min(count, 5000))
        rows = generate(n=count, seed=seed)
        header = ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"]
        buffer = io.StringIO()
        buffer.write('Notes:\n"Synthetic data generated by netlab. No real person is represented."\n\n')
        writer = csv.DictWriter(buffer, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"content-disposition": 'attachment; filename="Connections-sample.csv"'},
        )

    @app.post("/api/report", response_class=PlainTextResponse, tags=["analysis"])
    async def report_endpoint(
        file: Annotated[UploadFile, File()],
        redact: Annotated[bool, Form()] = True,
    ) -> str:
        """Analyze and return a Markdown report artifact."""
        raw = await _read_upload(file)
        document = analyze_bytes(raw, redact=redact, include_graph=False)
        return render_markdown(document)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
    else:  # pragma: no cover - only hit in a broken install
        log.warning("Static web directory missing at %s; UI will not be served.", WEB_DIR)

    return app


app = create_app()
