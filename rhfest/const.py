"""Const values for rhfest."""

import os
from typing import Final

PLUGIN_DIR: Final[str] = "custom_plugins"
MANIFEST_FILE: Final[str] = "manifest.json"
RHFEST_VERSION: Final[str] = os.getenv("RHFEST_VERSION") or "dev"

# Manifest checks
PYPI_PACKAGE_REGEX = (
    r"^[a-zA-Z0-9.-]+"  # Package name
    r"(?:\s*(~=|==|!=|<=|>=|<|>|===)\s*\d+(?:\.\d+)*(\.\*)?)?$"  # Optional versie-spec
)
GIT_URL_REGEX = r"^git\+https://[^\s]+$"
VERSION_REGEX = r"^\d+\.\d+\.\d+(-[a-zA-Z]+(\.\d+)?)?$"
