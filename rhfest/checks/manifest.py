"""Manifest check module."""

import json
import logging
from pathlib import Path

import voluptuous as vol
from const import ALLOWED_CATEGORIES_URL, PYPI_DEPENDENCY_REGEX
from utility import fetch_categories

MANIFEST_SCHEMA = vol.Schema(
    {
        "domain": vol.All(str, vol.Match(r"^[a-z0-9_-]+$")),
        "name": str,
        "description": str,
        "documentation": vol.Url(),
        "required_rhapi_version": vol.Match(r"^\d+\.\d+$"),
        "version": vol.Match(r"^\d+\.\d+\.\d+$"),
        "category": vol.All(
            [vol.In(fetch_categories(ALLOWED_CATEGORIES_URL))],
            vol.Length(min=1, max=2),
        ),
        vol.Optional("dependencies"): [vol.Match(PYPI_DEPENDENCY_REGEX)],
        vol.Optional("zip_release"): bool,
        vol.Optional("zip_filename"): vol.All(str, vol.Match(r"^[a-z0-9_-]+\.zip$")),
    },
    required=True,
    extra=vol.PREVENT_EXTRA,
)


class ManifestCheck:
    """Manifest check class, to validate the manifest.json file."""

    def __init__(self, manifest_file: Path) -> None:
        """Set the manifest file path."""
        self.manifest_file = manifest_file
        self.errors = []

    def _add_error(self, path: list, message: str) -> None:
        """Add an error to the errors list.

        Args:
        ----
            path (list): The path to the error.
            message (str): The error message.

        """
        formatted_path = " > ".join(str(p) for p in path or ["root"])
        self.errors.append(f"Validation error in [{formatted_path}]: {message}")

    def _validate_schema(self, manifest_data: dict) -> None:
        """Perform schema validation.

        Args:
        ----
            manifest_data (dict): The manifest data to validate.

        """
        try:
            MANIFEST_SCHEMA(manifest_data)
        except vol.MultipleInvalid as e:
            for err in e.errors:
                self._add_error(err.path, err.msg)
        except vol.Invalid as e:
            self._add_error(e.path, e.msg)

    def _validate_custom_rules(self, manifest_data: dict) -> None:
        """Perform custom validation rules.

        Args:
        ----
            manifest_data (dict): The manifest data to validate.

        """
        if manifest_data.get("zip_release") and not manifest_data.get("zip_filename"):
            self._add_error(
                ["zip_filename"],
                "'zip_filename' is required when 'zip_release' is set to true",
            )

    def run(self) -> dict[str, str]:
        """Validate the manifest.json according to the schema.

        Returns
        -------
            dict: The validation status and message.

        """
        with Path.open(self.manifest_file, encoding="utf-8") as f:
            manifest_data = json.load(f)

        self.errors = []

        # Start validation
        self._validate_schema(manifest_data)
        self._validate_custom_rules(manifest_data)

        if self.errors:
            for error in self.errors:
                logging.error(error)
            return {"status": "fail", "message": "Validation failed"}

        logging.info("✅ Manifest validation passed.")
        return {"status": "pass", "message": "Manifest is valid"}
