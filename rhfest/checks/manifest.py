"""Manifest check module."""

import json
import logging
from pathlib import Path

import voluptuous as vol

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
    extra=vol.PREVENT_EXTRA,
)


class ManifestCheck:
    """Manifest check class."""

    def __init__(self, manifest_file: Path) -> None:
        """Set the manifest file path."""
        self.manifest_file = manifest_file

    def run(self) -> dict[str, str]:
        """Validate the manifest.json according to the schema.

        Returns
        -------
            dict: The validation status and message.

        """
        with Path.open(self.manifest_file, encoding="utf-8") as f:
            manifest_data = json.load(f)

        try:
            MANIFEST_SCHEMA(manifest_data)
            logging.info("✅ Manifest validation passed.")
        except vol.MultipleInvalid as e:
            for error in e.errors:
                logging.error(  # noqa: TRY400
                    f"Validation error in [{'.'.join(str(p) for p in error.path) or 'root'}]: {error.msg}"  # noqa: E501
                )
            return {"status": "fail", "message": "Validation failed"}
        except vol.Invalid as e:
            field_path = ".".join(str(p) for p in e.path) or "root"
            logging.error(f"Validation error in [{field_path}]: {e.msg}")  # noqa: TRY400
            return {"status": "fail", "message": "Validation failed"}
        else:
            return {"status": "pass", "message": "Manifest is valid"}
