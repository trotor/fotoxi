"""Single source of truth for the application version.

Reads the version from ``pyproject.toml`` at runtime so the backend, the
OpenAPI docs and the frontend (via ``GET /api/version``) can never drift from
it. (``importlib.metadata`` is deliberately not used: it reflects the
version at ``pip install`` time, which goes stale on an editable install.)
"""
from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@lru_cache(maxsize=1)
def get_version() -> str:
    try:
        with open(_PYPROJECT, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"
