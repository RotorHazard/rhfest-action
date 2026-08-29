"""Tests for orchestration, status, models, and output rendering."""

from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from rhfest.engine import RuleRegistrationError, ValidationEngine
from rhfest.models import (
    Capability,
    Diagnostic,
    ManifestDocument,
    RuleFamily,
    RulePhase,
    Severity,
    ValidationContext,
    ValidationResult,
)
from rhfest.report import Reporter
from rhfest.rules import DEFAULT_RULES, Rule


class LateRule(Rule):
    """Test rule supplied before an earlier rule."""

    code = "STR012"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 20

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Return one deterministic finding."""
        return [self.diagnostic("late")]


class EarlyRule(Rule):
    """Test rule that should execute first by order."""

    code = "STR011"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 10

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Return one deterministic finding."""
        return [self.diagnostic("early")]


class WarningRule(Rule):
    """Test warning that must not fail validation."""

    code = "STR010"
    family = RuleFamily.STRUCTURE
    phase = RulePhase.STRUCTURE
    order = 10
    severity = Severity.WARNING

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Return a warning finding."""
        return [self.diagnostic("warning")]


class SourceRule(Rule):
    """Future source rule used to verify declarative phase behavior."""

    code = "RH099"
    family = RuleFamily.ROTORHAZARD
    phase = RulePhase.SOURCE
    order = 10
    severity = Severity.WARNING

    def check(self, context: ValidationContext) -> list[Diagnostic]:
        """Return a source warning."""
        return [self.diagnostic("source warning")]


class InvalidCodeRule(EarlyRule):
    """Test rule with a malformed stable code."""

    code = "STR01"


class InvalidFamilyRule(EarlyRule):
    """Test rule whose family does not belong to its phase."""

    code = "MAN010"
    family = RuleFamily.MANIFEST


class InvalidCapabilityRule(EarlyRule):
    """Test rule with an untyped context prerequisite."""

    requires = frozenset({"manifest_path"})


def test_engine_orders_rules_and_diagnostics(tmp_path: Path) -> None:
    """Registration order cannot make execution nondeterministic."""
    result = ValidationEngine([LateRule(), EarlyRule()]).run(
        ValidationContext(tmp_path)
    )

    assert result.executed_rules == ("STR011", "STR012")
    assert [item.message for item in result.diagnostics] == ["early", "late"]


def test_warnings_do_not_fail_the_run(tmp_path: Path) -> None:
    """Severity, not the presence of diagnostics, controls exit status."""
    result = ValidationEngine([WarningRule()]).run(ValidationContext(tmp_path))

    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        ([EarlyRule(), EarlyRule()], "Duplicate rule code"),
        ([InvalidCodeRule()], "plus 3 digits"),
        ([InvalidFamilyRule()], "expected STR"),
        ([InvalidCapabilityRule()], "invalid context capabilities"),
    ],
)
def test_registry_rejects_invalid_rule_metadata(
    rules: list[Rule],
    message: str,
) -> None:
    """Invalid registrations fail before repository analysis starts."""
    with pytest.raises(RuleRegistrationError, match=message):
        ValidationEngine(rules)


def test_source_phase_requires_structure_but_not_manifest_success(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Future RH rules remain independent from manifest policy failures."""
    valid_manifest["version"] = "invalid"
    context = ValidationContext(repository_factory(valid_manifest))

    result = ValidationEngine((*DEFAULT_RULES, SourceRule())).run(context)

    assert "MAN001" in result.executed_rules
    assert "RH001" in result.executed_rules
    assert [item.code for item in result.diagnostics] == ["MAN001", "RH099"]


def test_source_phase_is_blocked_after_structure_failure(tmp_path: Path) -> None:
    """Declarative phase prerequisites block source analysis without discovery."""
    result = ValidationEngine((*DEFAULT_RULES, SourceRule())).run(
        ValidationContext(tmp_path)
    )

    assert result.executed_rules == ("STR001",)
    assert [item.code for item in result.diagnostics] == ["STR001"]


def test_context_capabilities_are_typed(tmp_path: Path) -> None:
    """ValidationContext exposes discovered values through typed capabilities."""
    context = ValidationContext(tmp_path)

    assert not context.has(Capability.MANIFEST_PATH)
    context.manifest_path = tmp_path / "manifest.json"
    assert context.has(Capability.MANIFEST_PATH)
    context.manifest_document = ManifestDocument("null", None)
    assert context.has(Capability.MANIFEST_DOCUMENT)
    assert context.has(Capability.MANIFEST_DATA)


def test_diagnostic_rejects_mismatched_family() -> None:
    """Stable codes cannot accidentally be assigned to another family."""
    with pytest.raises(ValueError, match="not in family"):
        Diagnostic("MAN001", Severity.ERROR, "bad", RuleFamily.STRUCTURE)


def test_local_reporter_with_and_without_location() -> None:
    """Local diagnostics consistently include code, severity, and locations."""
    reporter = Reporter(StringIO(), github_actions=False, color=False)
    located = Diagnostic(
        "MAN001",
        Severity.ERROR,
        "invalid",
        RuleFamily.MANIFEST,
        "custom_plugins/test/manifest.json",
        4,
        2,
    )
    unlocated = Diagnostic(
        "STR001",
        Severity.WARNING,
        "notice",
        RuleFamily.STRUCTURE,
    )

    assert reporter.format_diagnostic(located) == (
        "error: MAN001 invalid\n --> custom_plugins/test/manifest.json:4:2"
    )
    assert reporter.format_diagnostic(unlocated) == "warning: STR001 notice"


def test_github_reporter_emits_annotation_metadata() -> None:
    """GitHub output exposes source metadata to Actions annotations."""
    reporter = Reporter(StringIO(), github_actions=True)
    diagnostic = Diagnostic(
        "MAN001",
        Severity.ERROR,
        "invalid",
        RuleFamily.MANIFEST,
        "manifest.json",
        4,
        2,
    )

    assert reporter.format_diagnostic(diagnostic) == (
        "::error title=rhfest (MAN001),file=manifest.json,line=4,col=2::"
        "manifest.json:4:2: MAN001 invalid"
    )


def test_engine_invokes_reporter(tmp_path: Path) -> None:
    """The central engine passes collected diagnostics to its reporter."""
    stream = StringIO()

    result = ValidationEngine([WarningRule()]).run(
        ValidationContext(tmp_path),
        Reporter(stream, github_actions=False, color=False),
    )

    assert result == ValidationResult(result.diagnostics, ("STR010",))
    assert stream.getvalue() == "warning: STR010 warning\nFound 1 warning.\n"


def test_structure_failure_renders_debug_tree(tmp_path: Path) -> None:
    """Useful repository-tree output remains available for structure failures."""
    (tmp_path / "README.md").touch()
    stream = StringIO()

    ValidationEngine().run(
        ValidationContext(tmp_path),
        Reporter(stream, github_actions=False),
    )

    output = stream.getvalue()
    assert "Directory structure for debugging:" in output
    assert "└── 📄 README.md" in output


def test_full_reporter_renders_source_range_and_help(tmp_path: Path) -> None:
    """Full output follows Ruff/ty source annotation conventions."""
    source = tmp_path / "manifest.json"
    source.write_text('{\n  "domain": "other"\n}\n', encoding="utf-8")
    diagnostic = Diagnostic(
        "MAN002",
        Severity.ERROR,
        "domain mismatch",
        RuleFamily.MANIFEST,
        "manifest.json",
        2,
        3,
        2,
        11,
        "Use the folder name.",
    )
    reporter = Reporter(StringIO(), github_actions=False, color=False)

    assert reporter.format_diagnostic(diagnostic, tmp_path) == (
        "error: MAN002 domain mismatch\n"
        " --> manifest.json:2:3\n"
        "  |\n"
        '2 |   "domain": "other"\n'
        "  |   ^^^^^^^^\n"
        "  |\n"
        "help: Use the folder name."
    )


@pytest.mark.parametrize("path_kind", ["parent", "absolute"])
def test_full_reporter_does_not_read_outside_repository(
    tmp_path: Path,
    path_kind: str,
) -> None:
    """Source snippets are restricted to paths inside the repository."""
    secret = tmp_path.parent / f"{tmp_path.name}-secret.txt"
    secret.write_text("must not be rendered\n", encoding="utf-8")
    diagnostic_path = (
        f"../{secret.name}" if path_kind == "parent" else str(secret.resolve())
    )
    diagnostic = Diagnostic(
        "MAN001",
        Severity.ERROR,
        "invalid",
        RuleFamily.MANIFEST,
        diagnostic_path,
        1,
        1,
    )
    reporter = Reporter(StringIO(), github_actions=False, color=False)

    assert reporter.format_diagnostic(diagnostic, tmp_path) == (
        f"error: MAN001 invalid\n --> {diagnostic_path}:1:1"
    )


def test_github_reporter_renders_ranges_help_and_escaping() -> None:
    """GitHub annotations match Ruff's metadata and workflow escaping."""
    diagnostic = Diagnostic(
        "MAN002",
        Severity.WARNING,
        "domain, mismatch",
        RuleFamily.MANIFEST,
        "custom_plugins/example/manifest.json",
        2,
        3,
        2,
        11,
        "Use 100% valid input.",
    )
    reporter = Reporter(StringIO(), github_actions=True)

    assert reporter.format_diagnostic(diagnostic) == (
        "::warning title=rhfest (MAN002),"
        "file=custom_plugins/example/manifest.json,line=2,col=3,"
        "endLine=2,endColumn=11::"
        "custom_plugins/example/manifest.json:2:3: MAN002 domain, mismatch"
        "%0A  help: Use 100%25 valid input."
    )
