"""Rule contract and the built-in RHFest rules."""

import json
import re
from abc import ABC, abstractmethod
from typing import ClassVar

import voluptuous as vol

from rhfest.const import (
    GIT_URL_REGEX,
    MANIFEST_FILE,
    PLUGIN_DIR,
    PYPI_PACKAGE_REGEX,
    VERSION_REGEX,
)
from rhfest.models import (
    Capability,
    Diagnostic,
    RuleFamily,
    RulePhase,
    Severity,
    ValidationContext,
)

MANIFEST_SCHEMA = vol.Schema(
    {
        "domain": vol.All(str, vol.Match(r"^[a-z0-9_-]+$")),
        "name": str,
        "description": str,
        "required_rhapi_version": vol.Match(r"^\d+\.\d+$"),
        "version": vol.Match(VERSION_REGEX),
        vol.Optional("documentation_uri"): vol.Any(None, vol.Url()),
        vol.Optional("dependencies"): [
            vol.Any(vol.Match(PYPI_PACKAGE_REGEX), vol.Match(GIT_URL_REGEX))
        ],
        vol.Optional("zip_filename"): vol.All(str, vol.Match(r"^[a-z0-9_-]+\.zip$")),
        vol.Optional("author"): vol.Any(None, str),
        vol.Optional("author_uri"): vol.Any(None, vol.Url()),
        vol.Optional("info_uri"): vol.Any(None, vol.Url()),
        vol.Optional("license"): vol.Any(None, str),
        vol.Optional("license_uri"): vol.Any(None, vol.Url()),
    },
    required=True,
    extra=vol.PREVENT_EXTRA,
)


class Rule(ABC):
    """Common contract for a validation rule."""

    code: ClassVar[str]
    family: ClassVar[RuleFamily]
    phase: ClassVar[RulePhase]
    order: ClassVar[int]
    severity: ClassVar[Severity] = Severity.ERROR
    requires: ClassVar[frozenset[Capability]] = frozenset()

    def is_applicable(self, context: ValidationContext) -> bool:
        """Return whether all explicitly declared context is available."""
        return all(context.has(capability) for capability in self.requires)

    def diagnostic(  # noqa: PLR0913
        self,
        message: str,
        *,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        end_line: int | None = None,
        end_column: int | None = None,
        help_text: str | None = None,
    ) -> Diagnostic:
        """Create a diagnostic carrying this rule's stable metadata."""
        return Diagnostic(
            code=self.code,
            severity=self.severity,
            message=message,
            family=self.family,
            path=path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
            help=help_text,
        )

    @abstractmethod
    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Run this rule and return findings without reporting side effects."""


class CustomPluginsRule(Rule):
    """STR001: require the root custom_plugins entry."""

    code = "STR001"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 10

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Discover the custom_plugins entry when present."""
        plugin_path = context.base_path / PLUGIN_DIR
        if not plugin_path.exists():
            return [
                self.diagnostic(
                    "Expected a custom_plugins entry at the repository root.",
                    path=PLUGIN_DIR,
                )
            ]
        context.plugin_path = plugin_path
        return []


class SinglePluginRule(Rule):
    """STR002: require exactly one entry below custom_plugins."""

    code = "STR002"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 20
    requires = frozenset({Capability.PLUGIN_PATH})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Discover the only plugin entry, retaining the existing glob semantics."""
        if context.plugin_path is None:
            return []

        plugin_entries = sorted(context.plugin_path.glob("*"))
        if not plugin_entries:
            return [
                self.diagnostic(
                    "Expected exactly one plugin entry; found none.",
                    path=PLUGIN_DIR,
                )
            ]
        if len(plugin_entries) > 1:
            names = ", ".join(entry.name for entry in plugin_entries)
            return [
                self.diagnostic(
                    f"Expected exactly one plugin entry; found: {names}.",
                    path=PLUGIN_DIR,
                )
            ]
        context.plugin_dir = plugin_entries[0]
        return []


class ManifestExistsRule(Rule):
    """STR003: require manifest.json below the discovered plugin entry."""

    code = "STR003"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 30
    requires = frozenset({Capability.PLUGIN_DIR})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Discover manifest.json when it exists."""
        if context.plugin_dir is None:
            return []

        manifest_path = context.plugin_dir / MANIFEST_FILE
        relative_path = context.repository_path(manifest_path)
        if not manifest_path.exists():
            return [
                self.diagnostic(
                    "Expected manifest.json below the plugin entry.",
                    path=relative_path,
                )
            ]
        context.manifest_path = manifest_path
        return []


class ManifestSchemaRule(Rule):
    """MAN001: load manifest.json and validate its complete schema."""

    code = "MAN001"
    family = RuleFamily.MANIFEST
    phase = RulePhase.MANIFEST
    order = 10
    requires = frozenset({Capability.MANIFEST_PATH})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Return one diagnostic for every Voluptuous schema finding."""
        if context.manifest_path is None:
            return []

        context.manifest_source = context.manifest_path.read_text(encoding="utf-8")
        context.manifest_data = json.loads(context.manifest_source)

        try:
            MANIFEST_SCHEMA(context.manifest_data)
        except vol.MultipleInvalid as err:
            errors = sorted(err.errors, key=lambda item: tuple(map(str, item.path)))
            return [self._schema_diagnostic(context, item) for item in errors]
        except vol.Invalid as err:
            return [self._schema_diagnostic(context, err)]
        return []

    def _schema_diagnostic(
        self,
        context: ValidationContext,
        error: vol.Invalid,
    ) -> Diagnostic:
        """Convert a Voluptuous error to the shared diagnostic model."""
        location = " > ".join(str(item) for item in error.path or ["root"])
        manifest_path = context.manifest_path
        location_data = self._field_location(context, error.path)
        return self.diagnostic(
            f"Validation error in [{location}]: {error.msg}",
            path=(
                context.repository_path(manifest_path)
                if manifest_path is not None
                else None
            ),
            **location_data,
        )

    @staticmethod
    def _field_location(
        context: ValidationContext,
        error_path: list[object],
    ) -> dict[str, int]:
        """Locate a present top-level JSON key for richer source output."""
        if not error_path or not isinstance(error_path[0], str):
            return {}
        return locate_manifest_key(context, error_path[0])


class ManifestDomainRule(Rule):
    """MAN002: require the manifest domain to match its parent folder."""

    code = "MAN002"
    family = RuleFamily.MANIFEST
    phase = RulePhase.MANIFEST
    order = 20
    requires = frozenset({Capability.MANIFEST_PATH, Capability.MANIFEST_DATA})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Compare a string domain with the discovered plugin folder name."""
        if context.manifest_path is None or not isinstance(context.manifest_data, dict):
            return []

        manifest_domain = context.manifest_data.get("domain")
        if not isinstance(manifest_domain, str):
            return []
        folder_domain = context.manifest_path.parent.name
        if manifest_domain == folder_domain:
            return []
        location = locate_manifest_key(context, "domain")
        return [
            self.diagnostic(
                f"Manifest domain {manifest_domain!r} does not match folder "
                f"{folder_domain!r}.",
                path=context.repository_path(context.manifest_path),
                help_text=f"Change the manifest domain to {folder_domain!r}.",
                **location,
            )
        ]


def locate_manifest_key(
    context: ValidationContext,
    key: str,
) -> dict[str, int]:
    """Return a one-based source range for a JSON object key when available."""
    if context.manifest_source is None:
        return {}
    match = re.search(rf'"{re.escape(key)}"[ \t]*:', context.manifest_source)
    if match is None:
        return {}
    key_offset = context.manifest_source.find(f'"{key}"', match.start(), match.end())
    line = context.manifest_source.count("\n", 0, key_offset) + 1
    previous_newline = context.manifest_source.rfind("\n", 0, key_offset)
    column = key_offset - previous_newline
    return {
        "line": line,
        "column": column,
        "end_line": line,
        "end_column": column + len(key) + 2,
    }


DEFAULT_RULES: tuple[Rule, ...] = (
    CustomPluginsRule(),
    SinglePluginRule(),
    ManifestExistsRule(),
    ManifestSchemaRule(),
    ManifestDomainRule(),
)
