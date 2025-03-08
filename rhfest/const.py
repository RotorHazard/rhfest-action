"""Const values for rhfest."""

from typing import Final

PLUGIN_DIR: Final[str] = "custom_plugins"
MANIFEST_FILE: Final[str] = "manifest.json"

# Manifest checks
PYPI_DEPENDENCY_REGEX = r"^[a-zA-Z0-9_.-]+==\d+\.\d+\.\d+$"
ALLOWED_CATEGORIES_URL = "https://rhcp.hazardcreative.com/v1/plugin/categories.json"
