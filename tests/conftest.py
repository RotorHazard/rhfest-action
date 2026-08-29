"""Shared fixtures for RHFest tests."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def valid_manifest() -> dict[str, Any]:
    """Return the smallest valid manifest accepted before the migration."""
    return {
        "domain": "example",
        "name": "Example",
        "description": "Example plugin",
        "required_rhapi_version": "1.2",
        "version": "1.0.0",
    }


@pytest.fixture
def repository_factory(
    tmp_path: Path,
) -> Callable[[dict[str, Any], str], Path]:
    """Create a representative plugin repository."""

    def create(manifest: dict[str, Any], domain: str = "example") -> Path:
        plugin_dir = tmp_path / "custom_plugins" / domain
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "__init__.py").touch()
        (plugin_dir / "manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return tmp_path

    return create
