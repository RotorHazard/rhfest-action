"""Rule contract and the built-in RHFest rules."""

import ast
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
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
    ManifestDocument,
    PythonSource,
    RuleFamily,
    RulePhase,
    Severity,
    ValidationContext,
)
from rhfest.source import RhapiProvenance, RhapiProvenanceAnalyzer

MANIFEST_SCHEMA = vol.Schema(
    {
        "domain": vol.All(
            str,
            vol.Match(r"^(?!.*__)(?!_)[a-z0-9_]+(?<!_)$"),
        ),
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
        context.plugin_entry = plugin_entries[0]
        return []


class PluginEntryPointRule(Rule):
    """STR004: require a plugin directory with a loadable entry point."""

    code = "STR004"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 30
    requires = frozenset({Capability.PLUGIN_ENTRY})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Validate the discovered plugin entry before exposing its directory."""
        if context.plugin_entry is None:
            return []

        plugin_entry = context.plugin_entry
        relative_entry = context.repository_path(plugin_entry)
        try:
            finding = self._validate_entry(context, plugin_entry)
        except OSError as error:
            return [
                self.diagnostic(
                    f"Unable to inspect the plugin entry: {error}.",
                    path=relative_entry,
                    help_text=(
                        "Ensure the plugin entry is accessible within the repository."
                    ),
                )
            ]
        if finding is not None:
            return [finding]

        context.plugin_dir = plugin_entry
        return []

    def _validate_entry(
        self,
        context: ValidationContext,
        plugin_entry: Path,
    ) -> Diagnostic | None:
        """Return a finding when the directory or entry point is invalid."""
        repository_root = context.base_path.resolve()
        relative_entry = context.repository_path(plugin_entry)
        resolved_entry = plugin_entry.resolve()
        if not resolved_entry.is_relative_to(repository_root):
            return self.diagnostic(
                "Plugin entry resolves outside the repository.",
                path=relative_entry,
                help_text="Keep the plugin directory within the repository.",
            )
        if not resolved_entry.is_dir():
            return self.diagnostic(
                "Expected the plugin entry to be a directory.",
                path=relative_entry,
                help_text=(
                    "Replace the entry with a directory containing __init__.py."
                ),
            )

        entry_point = plugin_entry / "__init__.py"
        relative_entry_point = context.repository_path(entry_point)
        resolved_entry_point = entry_point.resolve()
        if not resolved_entry_point.is_relative_to(repository_root):
            return self.diagnostic(
                "Plugin entry point resolves outside the repository.",
                path=relative_entry_point,
                help_text="Keep __init__.py within the repository.",
            )
        if not resolved_entry_point.is_file():
            return self.diagnostic(
                "Expected a regular __init__.py file below the plugin entry.",
                path=relative_entry_point,
                help_text=("Add a regular __init__.py file to the plugin directory."),
            )
        return None


class ManifestExistsRule(Rule):
    """STR003: require manifest.json below the discovered plugin entry."""

    code = "STR003"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 40
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


class ManifestParsingRule(Rule):
    """MAN000: read and parse manifest.json once for all manifest rules."""

    code = "MAN000"
    family = RuleFamily.MANIFEST
    phase = RulePhase.MANIFEST
    order = 0
    requires = frozenset({Capability.MANIFEST_PATH})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Populate reusable manifest context or return a parsing diagnostic."""
        if context.manifest_path is None:
            return []

        relative_path = context.repository_path(context.manifest_path)
        repository_root = context.base_path.resolve()
        try:
            manifest_path = context.manifest_path.resolve()
            if not manifest_path.is_relative_to(repository_root):
                return [
                    self.diagnostic(
                        "Manifest file resolves outside the repository.",
                        path=relative_path,
                        help_text="Keep manifest.json within the repository.",
                    )
                ]
            context.manifest_source = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            return [
                self.diagnostic(
                    f"Unable to read manifest JSON: {error}.",
                    path=relative_path,
                    help_text="Ensure manifest.json is readable UTF-8 JSON.",
                )
            ]

        try:
            data = json.loads(context.manifest_source)
        except json.JSONDecodeError as error:
            return [
                self.diagnostic(
                    f"Unable to parse manifest JSON: {error.msg}.",
                    path=relative_path,
                    line=error.lineno,
                    column=error.colno,
                    end_line=error.lineno,
                    end_column=error.colno + 1,
                    help_text="Fix the JSON syntax in manifest.json.",
                )
            ]

        context.manifest_document = ManifestDocument(context.manifest_source, data)
        return []


class ManifestSchemaRule(Rule):
    """MAN001: validate the parsed manifest against its complete schema."""

    code = "MAN001"
    family = RuleFamily.MANIFEST
    phase = RulePhase.MANIFEST
    order = 10
    requires = frozenset({Capability.MANIFEST_DOCUMENT})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Return one diagnostic for every Voluptuous schema finding."""
        if context.manifest_document is None:
            return []

        try:
            MANIFEST_SCHEMA(context.manifest_document.data)
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
    requires = frozenset({Capability.MANIFEST_PATH, Capability.MANIFEST_DOCUMENT})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Compare a string domain with the discovered plugin folder name."""
        if context.manifest_path is None or context.manifest_document is None:
            return []
        if not isinstance(context.manifest_document.data, dict):
            return []

        manifest_domain = context.manifest_document.data.get("domain")
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


class PythonSourceRule(Rule):
    """RH000: discover and parse plugin Python sources once."""

    code = "RH000"
    family = RuleFamily.ROTORHAZARD
    phase = RulePhase.SOURCE
    order = 0
    requires = frozenset({Capability.PLUGIN_DIR})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Populate reusable AST context and report unreadable or invalid files."""
        if context.plugin_dir is None:
            return []

        diagnostics: list[Diagnostic] = []
        sources: list[PythonSource] = []
        repository_root = context.base_path.resolve()
        plugin_root = context.plugin_dir.resolve()
        if not plugin_root.is_relative_to(repository_root):
            context.python_sources = ()
            return [
                self.diagnostic(
                    "Plugin source directory resolves outside the repository.",
                    path=context.repository_path(context.plugin_dir),
                    help_text="Keep plugin source files within the repository.",
                )
            ]

        candidates = sorted(
            context.plugin_dir.rglob("*.py"),
            key=context.repository_path,
        )
        for path in candidates:
            relative_path = context.repository_path(path)
            try:
                resolved_path = path.resolve()
                if (
                    not resolved_path.is_relative_to(plugin_root)
                    or not resolved_path.is_file()
                ):
                    continue
                source = resolved_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative_path)
            except SyntaxError as error:
                diagnostics.append(self._syntax_diagnostic(relative_path, error))
                continue
            except (OSError, UnicodeError) as error:
                diagnostics.append(
                    self.diagnostic(
                        f"Unable to read Python source: {error}.",
                        path=relative_path,
                        help_text="Ensure the file is readable UTF-8 source.",
                    )
                )
                continue
            sources.append(PythonSource(path, relative_path, source, tree))

        context.python_sources = tuple(sources)
        return diagnostics

    def _syntax_diagnostic(
        self,
        relative_path: str,
        error: SyntaxError,
    ) -> Diagnostic:
        """Convert a parser failure to the shared diagnostic contract."""
        line = error.lineno if error.lineno is not None and error.lineno > 0 else None
        column = error.offset if error.offset is not None and error.offset > 0 else None
        end_line = error.end_lineno if error.end_lineno == line else None
        end_column = (
            error.end_offset
            if end_line is not None
            and error.end_offset is not None
            and error.end_offset > 0
            else None
        )
        return self.diagnostic(
            f"Unable to parse Python source: {error.msg}.",
            path=relative_path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
            help_text="Fix the Python syntax before running source rules.",
        )


class PrivateRhapiAccessRule(Rule):
    """RH001: prohibit access to private RotorHazard race context state."""

    code = "RH001"
    family = RuleFamily.ROTORHAZARD
    phase = RulePhase.SOURCE
    order = 10
    requires = frozenset({Capability.PYTHON_SOURCES})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Find `_racecontext` access on conservatively derived RHAPI values."""
        diagnostics: list[Diagnostic] = []
        for source in context.python_sources or ():
            private_accesses: list[tuple[ast.Attribute, RhapiProvenance]] = []
            analyzer = RhapiProvenanceAnalyzer(
                lambda node, provenance, accesses=private_accesses: accesses.append(
                    (node, provenance)
                )
            )
            analyzer.analyze(source.tree)
            diagnostics.extend(
                self._diagnostic(source, node, provenance)
                for node, provenance in sorted(
                    private_accesses,
                    key=lambda item: (
                        item[0].end_lineno or 0,
                        item[0].end_col_offset or 0,
                    ),
                )
            )
        return diagnostics

    def _diagnostic(
        self,
        source: PythonSource,
        node: ast.Attribute,
        provenance: RhapiProvenance,
    ) -> Diagnostic:
        """Build a precise diagnostic over the private attribute name."""
        location = locate_attribute(source.source, node)
        return self.diagnostic(
            "Private RHAPI member '_racecontext' accessed. Plugins must use "
            "the public RHAPI interface.",
            path=source.relative_path,
            help_text=self._help_text(provenance),
            **location,
        )

    @staticmethod
    def _help_text(provenance: RhapiProvenance) -> str:
        """Suggest a public API only when namespace provenance is certain."""
        if provenance.namespace is not None:
            return (
                f"This value originates from `rhapi.{provenance.namespace}`; "
                "replace `_racecontext` access with a documented public RHAPI "
                "operation."
            )
        return "Replace `_racecontext` access with a documented public RHAPI operation."


class InitializeEntryPointRule(Rule):
    """RH002: validate the documented plugin initialize entry point."""

    code = "RH002"
    family = RuleFamily.ROTORHAZARD
    phase = RulePhase.SOURCE
    order = 20
    requires = frozenset({Capability.PLUGIN_DIR, Capability.PYTHON_SOURCES})

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Validate one unambiguous top-level ``initialize(rhapi)`` function."""
        source = self._entry_point_source(context)
        if source is None:
            return []

        definitions = [
            node
            for node in source.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "initialize"
        ]
        if not definitions:
            return [
                self.diagnostic(
                    "Expected a top-level `def initialize(rhapi)` entry point.",
                    path=source.relative_path,
                    help_text=self._help_text(),
                )
            ]
        if len(definitions) != 1:
            return [
                self.diagnostic(
                    "Expected exactly one top-level initialize definition; "
                    f"found {len(definitions)}.",
                    path=source.relative_path,
                    help_text=self._help_text(),
                    **locate_definition_name(source.source, definitions[0]),
                )
            ]

        definition = definitions[0]
        if self._has_supported_signature(definition):
            return []
        return [
            self.diagnostic(
                "Initialize entry point must use the supported "
                "`def initialize(rhapi)` signature.",
                path=source.relative_path,
                help_text=self._help_text(),
                **locate_definition_name(source.source, definition),
            )
        ]

    @staticmethod
    def _entry_point_source(context: ValidationContext) -> PythonSource | None:
        """Return the cached top-level plugin source when it parsed successfully."""
        if context.plugin_dir is None:
            return None
        relative_path = context.repository_path(context.plugin_dir / "__init__.py")
        return next(
            (
                source
                for source in context.python_sources or ()
                if source.relative_path == relative_path
            ),
            None,
        )

    @staticmethod
    def _has_supported_signature(
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> bool:
        """Return whether a definition exactly follows the supported contract."""
        arguments = definition.args
        positional = [*arguments.posonlyargs, *arguments.args]
        return (
            isinstance(definition, ast.FunctionDef)
            and not definition.decorator_list
            and len(positional) == 1
            and positional[0].arg == "rhapi"
            and not arguments.defaults
            and not arguments.kwonlyargs
            and arguments.vararg is None
            and arguments.kwarg is None
        )

    @staticmethod
    def _help_text() -> str:
        """Return version-independent guidance for the plugin contract."""
        return (
            "Define one synchronous, undecorated top-level "
            "`def initialize(rhapi)` following the RotorHazard plugin contract."
        )


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


def locate_attribute(source: str, node: ast.Attribute) -> dict[str, int]:
    """Return a one-based source range for an AST attribute name."""
    line = node.end_lineno or node.lineno
    end_offset = node.end_col_offset
    if end_offset is None:
        return {"line": line, "column": node.col_offset + 1}

    source_line = source.splitlines()[line - 1]
    encoded_line = source_line.encode("utf-8")
    start_offset = end_offset - len(node.attr.encode("utf-8"))
    column = len(encoded_line[:start_offset].decode("utf-8")) + 1
    end_column = len(encoded_line[:end_offset].decode("utf-8")) + 1
    return {
        "line": line,
        "column": column,
        "end_line": line,
        "end_column": end_column,
    }


def locate_definition_name(
    source: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, int]:
    """Return the one-based range of a function definition name."""
    source_line = source.splitlines()[node.lineno - 1]
    encoded_line = source_line.encode("utf-8")
    encoded_name = node.name.encode("utf-8")
    start_offset = encoded_line.find(encoded_name, node.col_offset)
    if start_offset < 0:
        return {"line": node.lineno, "column": node.col_offset + 1}
    column = len(encoded_line[:start_offset].decode("utf-8")) + 1
    end_column = (
        len(encoded_line[: start_offset + len(encoded_name)].decode("utf-8")) + 1
    )
    return {
        "line": node.lineno,
        "column": column,
        "end_line": node.lineno,
        "end_column": end_column,
    }


DEFAULT_RULES: tuple[Rule, ...] = (
    CustomPluginsRule(),
    SinglePluginRule(),
    PluginEntryPointRule(),
    ManifestExistsRule(),
    ManifestParsingRule(),
    ManifestSchemaRule(),
    ManifestDomainRule(),
    PythonSourceRule(),
    PrivateRhapiAccessRule(),
    InitializeEntryPointRule(),
)
