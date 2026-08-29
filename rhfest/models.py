"""Shared models for RHFest validation rules and diagnostics."""

import ast
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    """Severity of a validation diagnostic."""

    ERROR = "error"
    WARNING = "warning"


class RuleFamily(StrEnum):
    """Stable namespaces for RHFest rules."""

    STRUCTURE = "STR"
    MANIFEST = "MAN"
    ROTORHAZARD = "RH"


class RulePhase(StrEnum):
    """Validation phases, ordered by the engine rather than enum value."""

    STRUCTURE = "structure"
    MANIFEST = "manifest"
    SOURCE = "source"


class Capability(StrEnum):
    """Typed context values that rules can require."""

    PLUGIN_PATH = "plugin_path"
    PLUGIN_DIR = "plugin_dir"
    MANIFEST_PATH = "manifest_path"
    MANIFEST_DOCUMENT = "manifest_document"
    MANIFEST_DATA = "manifest_data"
    MANIFEST_SOURCE = "manifest_source"
    PYTHON_SOURCES = "python_sources"


@dataclass(frozen=True, slots=True)
class ManifestDocument:
    """A manifest read and parsed once for all manifest rules."""

    source: str
    data: Any


@dataclass(frozen=True, slots=True)
class PythonSource:
    """A plugin Python file parsed once for all source rules."""

    path: Path
    relative_path: str
    source: str
    tree: ast.Module


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single, reportable validation finding."""

    code: str
    severity: Severity
    message: str
    family: RuleFamily
    path: str | None = None
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    help: str | None = None

    def __post_init__(self) -> None:
        """Reject invalid diagnostic metadata at its source."""
        if not self.code.startswith(self.family.value):
            msg = f"Rule code {self.code!r} is not in family {self.family.value!r}."
            raise ValueError(msg)
        if self.line is not None and self.line < 1:
            msg = "Diagnostic lines are one-based."
            raise ValueError(msg)
        if self.column is not None and self.column < 1:
            msg = "Diagnostic columns are one-based."
            raise ValueError(msg)
        if self.end_line is not None and self.end_line < 1:
            msg = "Diagnostic end lines are one-based."
            raise ValueError(msg)
        if self.end_column is not None and self.end_column < 1:
            msg = "Diagnostic end columns are one-based."
            raise ValueError(msg)


@dataclass(slots=True)
class ValidationContext:
    """Repository data discovered and shared explicitly between rule phases."""

    base_path: Path
    plugin_path: Path | None = None
    plugin_dir: Path | None = None
    manifest_path: Path | None = None
    manifest_source: str | None = None
    manifest_document: ManifestDocument | None = None
    python_sources: tuple[PythonSource, ...] | None = None

    @property
    def manifest_data(self) -> Any | None:
        """Expose parsed manifest data for compatibility with context consumers."""
        if self.manifest_document is None:
            return None
        return self.manifest_document.data

    def repository_path(self, path: Path) -> str:
        """Return a repository-relative POSIX path for a diagnostic."""
        return path.relative_to(self.base_path).as_posix()

    def has(self, capability: Capability) -> bool:
        """Return whether a typed capability is available to a rule."""
        if capability is Capability.MANIFEST_DATA:
            return self.manifest_document is not None
        return getattr(self, capability.value) is not None

    def source_for(self, path: str | None) -> str | None:
        """Return source already loaded for a repository-relative path."""
        if path is None:
            return None
        if (
            self.manifest_path is not None
            and self.manifest_source is not None
            and self.repository_path(self.manifest_path) == path
        ):
            return self.manifest_source
        for source in self.python_sources or ():
            if source.relative_path == path:
                return source.source
        return None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Collected output and status for one engine run."""

    diagnostics: tuple[Diagnostic, ...]
    executed_rules: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        """Return a failing status only when at least one error exists."""
        return int(any(item.severity is Severity.ERROR for item in self.diagnostics))
