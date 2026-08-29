"""Consistent local and GitHub Actions reporting for RHFest diagnostics."""

import os
import sys
from pathlib import Path
from typing import TextIO

from rhfest.models import (
    Diagnostic,
    RuleFamily,
    Severity,
    ValidationContext,
    ValidationResult,
)

IGNORED_FOLDERS = {".ruff_cache", ".venv", "__pycache__", ".git", ".github"}


class Reporter:
    """Render diagnostics and a summary without deciding process control flow."""

    def __init__(
        self,
        stream: TextIO = sys.stdout,
        *,
        github_actions: bool | None = None,
        show_debug_tree: bool = True,
        color: bool | None = None,
    ) -> None:
        """Configure the output target and annotation environment."""
        self.stream = stream
        self.github_actions = (
            os.getenv("GITHUB_ACTIONS") == "true"
            if github_actions is None
            else github_actions
        )
        self.show_debug_tree = show_debug_tree
        self.color = (
            stream.isatty() and "NO_COLOR" not in os.environ if color is None else color
        )

    def report_configuration(self, summary: str) -> None:
        """Identify explicit local selection without adding annotation noise."""
        if summary and not self.github_actions:
            self._write(f"RHFest configuration: {summary}")

    def report(
        self,
        result: ValidationResult,
        context: ValidationContext,
    ) -> None:
        """Render all findings, optional structure tree, and final status."""
        for diagnostic in result.diagnostics:
            self._write(
                self.format_diagnostic(
                    diagnostic,
                    context.base_path,
                    source=context.source_for(diagnostic.path),
                )
            )

        has_structure_error = any(
            item.family is RuleFamily.STRUCTURE and item.severity is Severity.ERROR
            for item in result.diagnostics
        )
        if has_structure_error and self.show_debug_tree:
            self._write("Directory structure for debugging:")
            self._write_tree(context.base_path)

        self._write_summary(result)

    def format_diagnostic(
        self,
        diagnostic: Diagnostic,
        base_path: Path | None = None,
        *,
        source: str | None = None,
    ) -> str:
        """Format a diagnostic for local output or a GitHub annotation."""
        if self.github_actions:
            return self._format_github(diagnostic)
        return self._format_full(diagnostic, base_path, source)

    def _format_full(
        self,
        diagnostic: Diagnostic,
        base_path: Path | None,
        source: str | None,
    ) -> str:
        """Render a Ruff/ty-style terminal diagnostic."""
        severity_color = "31" if diagnostic.severity is Severity.ERROR else "33"
        severity = self._style(diagnostic.severity.value, severity_color, bold=True)
        code = self._style(diagnostic.code, severity_color, bold=True)
        lines = [f"{severity}: {code} {diagnostic.message}"]

        if diagnostic.path:
            location = diagnostic.path
            if diagnostic.line is not None:
                location += f":{diagnostic.line}"
                if diagnostic.column is not None:
                    location += f":{diagnostic.column}"
            lines.append(f" {self._style('-->', '34', bold=True)} {location}")

        source_line = self._read_source_line(diagnostic, base_path, source)
        if source_line is not None and diagnostic.line is not None:
            line_number = str(diagnostic.line)
            gutter = " " * len(line_number)
            lines.extend(
                (
                    f"{gutter} {self._style('|', '34', bold=True)}",
                    f"{line_number} {self._style('|', '34', bold=True)} {source_line}",
                    self._underline(diagnostic, gutter),
                    f"{gutter} {self._style('|', '34', bold=True)}",
                )
            )

        if diagnostic.help:
            help_label = self._style("help", "36", bold=True)
            lines.append(f"{help_label}: {diagnostic.help}")
        return "\n".join(lines)

    def _format_github(self, diagnostic: Diagnostic) -> str:
        """Render the same workflow-command structure used by Ruff and ty."""
        properties = [f"title=rhfest ({self._escape_property(diagnostic.code)})"]
        if diagnostic.path:
            properties.append(f"file={self._escape_property(diagnostic.path)}")
        if diagnostic.line is not None:
            properties.append(f"line={diagnostic.line}")
        if diagnostic.column is not None:
            properties.append(f"col={diagnostic.column}")
        if diagnostic.end_line is not None:
            properties.append(f"endLine={diagnostic.end_line}")
        if diagnostic.end_column is not None:
            properties.append(f"endColumn={diagnostic.end_column}")

        location = diagnostic.path or ""
        if diagnostic.line is not None:
            location += f":{diagnostic.line}"
            if diagnostic.column is not None:
                location += f":{diagnostic.column}"
        prefix = f"{location}: " if location else ""
        message = f"{prefix}{diagnostic.code} {diagnostic.message}"
        if diagnostic.help:
            message += f"\n  help: {diagnostic.help}"
        escaped_message = self._escape_message(message)
        metadata = ",".join(properties)
        return f"::{diagnostic.severity.value} {metadata}::{escaped_message}"

    def _underline(self, diagnostic: Diagnostic, gutter: str) -> str:
        """Render a one-line source underline for a diagnostic range."""
        column = diagnostic.column or 1
        end_column = diagnostic.end_column or column + 1
        width = max(end_column - column, 1)
        marker = " " * (column - 1) + "^" * width
        marker_color = "31" if diagnostic.severity is Severity.ERROR else "33"
        return (
            f"{gutter} {self._style('|', '34', bold=True)} "
            f"{self._style(marker, marker_color, bold=True)}"
        )

    @staticmethod
    def _read_source_line(
        diagnostic: Diagnostic,
        base_path: Path | None,
        source: str | None = None,
    ) -> str | None:
        """Read a requested source line, returning no snippet when unavailable."""
        if diagnostic.path is None or diagnostic.line is None:
            return None
        source_lines = (
            source.splitlines()
            if source is not None
            else Reporter._read_source_lines(diagnostic.path, base_path)
        )
        if source_lines is None or diagnostic.line > len(source_lines):
            return None
        return source_lines[diagnostic.line - 1]

    @staticmethod
    def _read_source_lines(
        diagnostic_path: str,
        base_path: Path | None,
    ) -> list[str] | None:
        """Read repository-contained source when it is not already cached."""
        if base_path is None:
            return None
        try:
            repository_path = base_path.resolve()
            source_path = (repository_path / diagnostic_path).resolve()
            if not source_path.is_relative_to(repository_path):
                return None
            return source_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return None

    def _write_summary(self, result: ValidationResult) -> None:
        """Render Ruff-like success or diagnostic totals."""
        errors = sum(item.severity is Severity.ERROR for item in result.diagnostics)
        warnings = sum(item.severity is Severity.WARNING for item in result.diagnostics)
        if errors == 0 and warnings == 0:
            self._write(self._style("All checks passed!", "32", bold=True))
            return

        parts: list[str] = []
        if errors:
            parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
        self._write(f"Found {' and '.join(parts)}.")

    def _style(self, text: str, code: str, *, bold: bool = False) -> str:
        """Apply ANSI SGR styling only for an interactive color target."""
        if not self.color:
            return text
        attributes = f"1;{code}" if bold else code
        return f"\x1b[{attributes}m{text}\x1b[0m"

    @staticmethod
    def _escape_message(value: str) -> str:
        """Escape GitHub workflow-command message data."""
        return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    @classmethod
    def _escape_property(cls, value: str) -> str:
        """Escape GitHub workflow-command property data."""
        return cls._escape_message(value).replace(":", "%3A").replace(",", "%2C")

    def _write(self, line: str) -> None:
        """Write one output line."""
        print(line, file=self.stream)

    def _write_tree(self, directory: Path, prefix: str = "") -> None:
        """Recursively render a deterministic, filtered directory tree."""
        entries = sorted(
            entry
            for entry in directory.iterdir()
            if not (entry.is_dir() and entry.name in IGNORED_FOLDERS)
        )
        for index, entry in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = "└──" if is_last else "├──"
            icon = "📁" if entry.is_dir() else "📄"
            self._write(f"{prefix}{connector} {icon} {entry.name}")
            if entry.is_dir():
                child_prefix = prefix + ("    " if is_last else "│   ")
                self._write_tree(entry, child_prefix)
