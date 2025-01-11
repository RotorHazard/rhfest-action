"""Core module for the rhfest package."""

import logging
import sys
from pathlib import Path

from checks.manifest import ManifestCheck
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


def find_manifest_path(base_path: Path, report: Report) -> Path:
    """Find the manifest.json file in the custom_plugins directory.

    Args:
    ----
        base_path: The base path of the repository.
        report: The report object to log messages.

    Returns:
    -------
        The path to the manifest.json file.

    """
    logging.info(f"🔍 Searching for manifest.json in {base_path}")
    plugin_dirs = list(base_path.glob("*"))

    if len(plugin_dirs) == 0:
        logging.error(f"No plugin domain directory found in '{base_path}'.")
        logging.info("🐛 Directory structure for debugging:")
        report.list_files_in_tree(base_path)
        sys.exit(1)

    if len(plugin_dirs) > 1:
        logging.error(
            f"Multiple plugin directories found: "
            f"{[p.name for p in plugin_dirs]} in '{base_path}'."
        )
        logging.info("🐛 Directory structure for debugging:")
        report.list_files_in_tree(base_path)
        sys.exit(1)

    manifest_path = plugin_dirs[0] / "manifest.json"
    if not manifest_path.exists():
        logging.error(f"manifest.json not found in {manifest_path}.")
        logging.info("🐛 Directory structure for debugging:")
        report.list_files_in_tree(base_path)
        sys.exit(1)

    logging.info(f"✅ Found manifest.json at {manifest_path}")
    return manifest_path


def run_rhfest() -> None:
    """Run validation for the manifest.json file."""
    base_path = Path.cwd()
    report = Report()

    logging.info(f"🔍 Searching for '{PLUGIN_DIR}' directory in {base_path}")
    plugin_path: str = base_path / PLUGIN_DIR
    if not plugin_path.exists():
        logging.error(f"No '{PLUGIN_DIR}' directory found in '{base_path}'.")
        logging.info("🐛 Directory structure for debugging:")
        report.list_files_in_tree(base_path)
        sys.exit(1)

    manifest_path = find_manifest_path(plugin_path, report)
    report = Report()

    logging.info("🚦 Starting manifest.json validation...")
    result = ManifestCheck(manifest_path).run()
    report.add(result)
    report.generate()


if __name__ == "__main__":
    run_rhfest()
