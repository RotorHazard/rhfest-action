"""Const values for rhfest."""

import os
from typing import Final


def _resolve_rhfest_version() -> str:
    """Resolve the build version or the GitHub Action reference."""
    return os.getenv("RHFEST_VERSION") or os.getenv("GITHUB_ACTION_REF") or "dev"


PLUGIN_DIR: Final[str] = "custom_plugins"
MANIFEST_FILE: Final[str] = "manifest.json"
RHFEST_VERSION: Final[str] = _resolve_rhfest_version()

# Manifest checks
PYPI_PACKAGE_REGEX = (
    r"^[a-zA-Z0-9.-]+"  # Package name
    r"(?:\s*(~=|==|!=|<=|>=|<|>|===)\s*\d+(?:\.\d+)*(\.\*)?)?$"  # Optional versie-spec
)
GIT_URL_REGEX = r"^git\+https://[^\s]+$"
VERSION_REGEX = r"^\d+\.\d+\.\d+(-[a-zA-Z]+(\.\d+)?)?$"
