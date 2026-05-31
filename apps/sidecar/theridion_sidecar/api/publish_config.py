"""Publish config — persisted settings for RunResult v2 push targets.

Storage: ~/.theridion/publish_config.json
Shape:
  {
    "weave_url": "https://...",
    "weave_token": "...",
    "hub_url": "https://...",
    "hub_token": "...",
    "enabled": true
  }

Tokens are stored on disk (chmod 600 on the parent dir is the OS-level
protection). They are NEVER returned in log output.

Endpoints
---------
GET  /api/run-result/config  -> PublishConfig (tokens redacted to "*" if set)
PUT  /api/run-result/config  -> PublishConfig (round-trips the full value)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar.storage import home_dir

router = APIRouter(prefix="/api/run-result", tags=["run-result-v2"])

_CONFIG_FILENAME = "publish_config.json"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class PublishConfig(BaseModel):
    """Publish targets for RunResult v2 push."""

    weave_url: str = ""
    weave_token: str = ""
    hub_url: str = ""
    hub_token: str = ""
    enabled: bool = True


class PublishConfigMasked(BaseModel):
    """Read response — tokens are masked when set so they are never echoed."""

    weave_url: str = ""
    weave_token_set: bool = False
    hub_url: str = ""
    hub_token_set: bool = False
    enabled: bool = True


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _config_path() -> Path:
    return home_dir() / _CONFIG_FILENAME


def load_config() -> PublishConfig:
    """Load publish config from disk. Returns defaults if file is absent or corrupt."""
    p = _config_path()
    if not p.exists():
        return PublishConfig()
    try:
        return PublishConfig(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return PublishConfig()


def save_config(cfg: PublishConfig) -> None:
    """Persist publish config atomically. Tokens are written as-is — never logged."""
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump(mode="json")
    fd, tmp_str = tempfile.mkstemp(
        prefix="publish_config.", suffix=".json.tmp", dir=str(p.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _mask(cfg: PublishConfig) -> PublishConfigMasked:
    """Return a read-safe view — presence of token indicated by bool, not value."""
    return PublishConfigMasked(
        weave_url=cfg.weave_url,
        weave_token_set=bool(cfg.weave_token),
        hub_url=cfg.hub_url,
        hub_token_set=bool(cfg.hub_token),
        enabled=cfg.enabled,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/config", response_model=PublishConfigMasked)
async def get_publish_config() -> PublishConfigMasked:
    """Return the current publish config. Tokens are represented as booleans."""
    return _mask(load_config())


@router.put("/config", response_model=PublishConfigMasked)
async def put_publish_config(cfg: PublishConfig) -> PublishConfigMasked:
    """Persist publish config. Pass empty string to clear a token."""
    save_config(cfg)
    return _mask(cfg)
