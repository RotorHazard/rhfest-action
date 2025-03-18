"""Const values for rhfest."""

import logging
import os
import sys
from typing import Final

PLUGIN_DIR: Final[str] = "custom_plugins"
MANIFEST_FILE: Final[str] = "manifest.json"
RHFEST_VERSION = os.getenv("RHFEST_VERSION", "dev")

# Manifest checks
PYPI_DEPENDENCY_REGEX = r"^[a-zA-Z0-9_.-]+==\d+\.\d+\.\d+$"
ALLOWED_CATEGORIES_URL = "https://rhcp.hazardcreative.com/v1/plugin/categories.json"

# Logging setup
logging.addLevelName(logging.INFO, "")
logging.addLevelName(logging.ERROR, "::error::")
logging.addLevelName(logging.WARNING, "::warning::")
logging.basicConfig(
    level=logging.INFO,
    format=" %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)
