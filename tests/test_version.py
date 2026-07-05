"""Tests for backend.version — single source of truth for the app version."""
import tomllib
from pathlib import Path

from backend.version import get_version


def test_get_version_matches_pyproject():
    """get_version() reads the version straight from pyproject.toml (single source)."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    assert get_version() == expected
