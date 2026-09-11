"""Runtime configuration.

Environment-driven with safe defaults. The defaults are deliberately restrictive: bind to
loopback, no persistence, no telemetry. Anything that weakens the privacy posture must be
switched on explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


@dataclass(slots=True)
class Settings:
    """Process configuration, resolved once at import of `netlab.api`."""

    host: str = field(default_factory=lambda: os.getenv("NETLAB_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("NETLAB_PORT", 8787))
    log_level: str = field(default_factory=lambda: os.getenv("NETLAB_LOG_LEVEL", "INFO").upper())
    log_json: bool = field(default_factory=lambda: _env_bool("NETLAB_LOG_JSON", False))

    # Privacy controls
    allow_persistence: bool = field(default_factory=lambda: _env_bool("NETLAB_ALLOW_PERSISTENCE", False))
    redact_by_default: bool = field(default_factory=lambda: _env_bool("NETLAB_REDACT", False))

    # Resource guards
    max_upload_mb: int = field(default_factory=lambda: _env_int("NETLAB_MAX_UPLOAD_MB", 64))
    max_graph_nodes: int = field(default_factory=lambda: _env_int("NETLAB_MAX_GRAPH_NODES", 6000))

    # CORS: empty means same-origin only, which is correct for the bundled UI.
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv("NETLAB_CORS_ORIGINS", "").split(",") if o.strip()
        )
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def binds_publicly(self) -> bool:
        return self.host not in {"127.0.0.1", "localhost", "::1"}


settings = Settings()
