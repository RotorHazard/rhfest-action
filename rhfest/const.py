"""Const values for rhfest."""

from typing import Final

PLUGIN_DIR: Final[str] = "custom_plugins"
MANIFEST_FILE: Final[str] = "manifest.json"

# Manifest checks
PYPI_DEPENDENCY_REGEX = r"^[a-zA-Z0-9_.-]+==\d+\.\d+\.\d+$"
ALLOWED_CATEGORIES_URL = "https://raw.githubusercontent.com/dutchdronesquad/rh-community-store/main/categories.json"
