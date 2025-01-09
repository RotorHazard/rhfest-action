import json
import logging
from pathlib import Path

import voluptuous as vol
from voluptuous.humanize import humanize_error

PYPI_DEPENDENCY_REGEX = r"^[a-zA-Z0-9_.-]+==\d+\.\d+\.\d+$"

MANIFEST_SCHEMA = vol.Schema(
    {
        "domain": vol.All(str, vol.Match(r"^[a-z0-9_-]+$")),
        "name": str,
        "description": str,
        "codeowners": [vol.Match(r"^@\w+")],
        "documentation": vol.Url(),
        "required_rhapi_version": vol.Match(r"^\d+\.\d+$"),
        "version": vol.Match(r"^\d+\.\d+\.\d+$"),
        vol.Optional("dependencies"): [vol.Match(PYPI_DEPENDENCY_REGEX)],
        vol.Optional("tags"): [str],
    },
    required=True,
    extra=vol.REMOVE_EXTRA,
)

class ManifestCheck:
    def __init__(self, manifest_file: Path):
        self.manifest_file = manifest_file

    def run(self):
        """Valideert de manifest.json volgens het schema."""
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        try:
            MANIFEST_SCHEMA(manifest_data)
            logging.info("✅ Validatie geslaagd: manifest.json is geldig.")
            return {"status": "pass", "message": "Manifest is valid"}
        except vol.Invalid as e:
            logging.error(f"❌ Validatie mislukt: {humanize_error(manifest_data, e)}")
            return {"status": "fail", "message": f"Validation error: {humanize_error(manifest_data, e)}"}
