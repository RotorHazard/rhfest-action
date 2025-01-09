"""Core module for the rhfest package."""

import logging
import sys
from pathlib import Path

from checks.manifest import ManifestCheck
from report import Report

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def find_manifest_path(base_path: Path) -> Path:
    plugin_dirs = list(base_path.glob("custom_plugins/*"))
    if len(plugin_dirs) == 0:
        logging.error("Geen plugins gevonden in 'custom_plugins/'.")
        sys.exit(1)
    if len(plugin_dirs) > 1:
        logging.error(f"Meerdere mappen gevonden in 'custom_plugins/': {[p.name for p in plugin_dirs]}")
        sys.exit(1)
    manifest_path = plugin_dirs[0] / "manifest.json"
    if not manifest_path.exists():
        logging.error(f"manifest.json niet gevonden in {manifest_path}.")
        sys.exit(1)
    logging.info(f"Manifest gevonden: {manifest_path}")
    return manifest_path

def run_rhfest(base_path: str):
    base_path = Path(base_path).resolve()
    manifest_path = find_manifest_path(base_path)
    report = Report()
    logging.info("Start met het valideren van het manifest.json-bestand...")
    result = ManifestCheck(manifest_path).run()
    report.add(result)
    report.generate()

if __name__ == "__main__":
    run_rhfest(".")
