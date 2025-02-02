"""Core module for the rhfest package."""

import logging
import os
import sys
from pathlib import Path

from checks.manifest import ManifestCheck
from checks.structure import StructureCheck
from report import Report

# Logging setup
logging.addLevelName(logging.INFO, "")
logging.addLevelName(logging.ERROR, "::error::")
logging.addLevelName(logging.WARNING, "::warning::")
logging.basicConfig(
    level=logging.INFO,
    format=" %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
PLUGIN_DIR = "custom_plugins"


def run_rhfest(base_path: str) -> None:
    """Run validation for the manifest.json file.

    Args:
    ----
        base_path: The base path of the repository.

    """
    base_path = Path(base_path).resolve()
    report = Report()

    logging.info("🚦 Starting structure validation")
    structure_check = StructureCheck(base_path, report)
    structure_result = structure_check.run()
    report.add(structure_result)
    # Check if the structure check failed
    if structure_result["status"] == "fail":
        report.generate()  # Triggers sys.exit(1)

    logging.info("🚦 Starting manifest.json validation")
    result = ManifestCheck(structure_check.manifest_path).run()
    report.add(result)
    report.generate()


if __name__ == "__main__":
    run_rhfest(os.getenv("GITHUB_WORKSPACE", Path.cwd()))
