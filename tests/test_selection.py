"""Tests for rule selection, configuration, and filtered outcomes."""

from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from rhfest.core import main, run_rhfest
from rhfest.engine import ValidationEngine
from rhfest.models import (
    Diagnostic,
    RuleFamily,
    Severity,
    ValidationContext,
    ValidationResult,
)
from rhfest.report import Reporter
from rhfest.selection import RuleSelection, RuleSelectionError

REGISTERED_CODES = ("STR001", "STR004", "MAN000", "MAN002", "RH001", "RH002")


def test_default_selection_keeps_every_registered_rule() -> None:
    """Omitted configuration preserves the existing report-all behavior."""
    selection = RuleSelection.from_selectors(REGISTERED_CODES)

    assert selection.selected_codes == frozenset(REGISTERED_CODES)
    assert not selection.active
    assert selection.summary == ""


def test_exact_codes_and_family_prefixes_are_case_insensitive() -> None:
    """Comma lists and repeated values resolve exact codes and full families."""
    selection = RuleSelection.from_selectors(
        REGISTERED_CODES,
        select=["rh002, man", "STR004"],
    )

    assert selection.selected_codes == {
        "STR004",
        "MAN000",
        "MAN002",
        "RH002",
    }
    assert selection.select == ("MAN", "RH002", "STR004")
    assert selection.summary == "select=MAN,RH002,STR004"


def test_ignore_takes_precedence_over_select() -> None:
    """Ignore removes matching codes after exact or family selection expands."""
    selection = RuleSelection.from_selectors(
        REGISTERED_CODES,
        select="MAN,RH002",
        ignore="MAN002,RH",
    )

    assert selection.selected_codes == {"MAN000"}
    assert selection.summary == "select=MAN,RH002; ignore=MAN002,RH"


@pytest.mark.parametrize("selector", ["MAN999", "OTHER"])
def test_unknown_selectors_fail_clearly(selector: str) -> None:
    """Well-formed but unregistered codes and families are configuration errors."""
    with pytest.raises(RuleSelectionError, match="Unknown rule selector"):
        RuleSelection.from_selectors(REGISTERED_CODES, select=selector)


@pytest.mark.parametrize("selector", ["RH0", "RH002X", "123", "RH,,MAN"])
def test_malformed_selectors_fail_clearly(selector: str) -> None:
    """Partial codes, mixed suffixes, numeric values, and empty items are rejected."""
    with pytest.raises(RuleSelectionError, match="rule selector"):
        RuleSelection.from_selectors(REGISTERED_CODES, ignore=selector)


def test_malformed_selector_guidance_uses_registered_families() -> None:
    """Configuration guidance cannot drift from the RuleFamily enum."""
    with pytest.raises(RuleSelectionError) as error:
        RuleSelection.from_selectors(REGISTERED_CODES, select="RH0")

    expected_families = ", ".join(sorted(family.value for family in RuleFamily))
    assert f"expected {expected_families}, or an exact code" in str(error.value)


def test_selection_filters_diagnostics_but_not_prerequisite_execution(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Selecting one rule retains all discovery and context-building execution."""
    valid_manifest.update(version="invalid", domain="different")
    repository = repository_factory(valid_manifest)
    context = ValidationContext(repository)
    engine = ValidationEngine()
    selection = RuleSelection.from_selectors(
        (rule.code for rule in engine.rules),
        select="MAN002",
    )

    result = engine.run(context, selection=selection)

    assert [item.code for item in result.diagnostics] == ["MAN002"]
    assert "MAN001" in result.executed_rules
    assert "MAN002" in result.executed_rules
    assert context.manifest_document is not None


def test_filtered_diagnostics_control_exit_status_and_local_output(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """An ignored error is neither rendered nor counted in process status."""
    valid_manifest["domain"] = "different"
    repository = repository_factory(valid_manifest)
    stream = StringIO()

    status = run_rhfest(
        repository,
        Reporter(stream, github_actions=False, show_debug_tree=False, color=False),
        ignore="MAN002",
    )

    assert status == 0
    assert stream.getvalue() == (
        "RHFest version: dev\nRHFest configuration: ignore=MAN002\nAll checks passed!\n"
    )


def test_github_output_does_not_add_configuration_noise(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Action annotations only contain diagnostics and the normal summary."""
    valid_manifest["domain"] = "different"
    repository = repository_factory(valid_manifest)
    stream = StringIO()

    status = run_rhfest(
        repository,
        Reporter(stream, github_actions=True, show_debug_tree=False),
        select="MAN002",
    )

    assert status == 1
    assert "RHFest configuration" not in stream.getvalue()
    assert "::error title=rhfest (MAN002)" in stream.getvalue()


def test_cli_rejects_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Malformed CLI configuration exits with argparse's configuration status."""
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))

    with pytest.raises(SystemExit) as error:
        main(["--select", "RH0"])

    assert error.value.code == 2
    assert "Malformed rule selector: 'RH0'" in capsys.readouterr().err


def test_cli_combines_repeated_select_and_ignore_options(
    monkeypatch: pytest.MonkeyPatch,
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Repeated local flags use the same comma-list and precedence contract."""
    valid_manifest["domain"] = "different"
    repository = repository_factory(valid_manifest)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(repository))

    with pytest.raises(SystemExit) as error:
        main(["--select", "STR,MAN", "--select", "RH002", "--ignore", "MAN002"])

    assert error.value.code == 0


def test_action_input_environment_uses_the_same_selectors(
    monkeypatch: pytest.MonkeyPatch,
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Docker Action INPUT values feed the same validated configuration path."""
    valid_manifest["domain"] = "different"
    repository = repository_factory(valid_manifest)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(repository))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("INPUT_IGNORE", "MAN002")

    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 0


def test_diagnostic_order_remains_deterministic_after_filtering() -> None:
    """Selector ordering never reorders diagnostics or execution metadata."""
    diagnostics = (
        Diagnostic("STR001", Severity.ERROR, "first", RuleFamily.STRUCTURE),
        Diagnostic("MAN002", Severity.ERROR, "second", RuleFamily.MANIFEST),
        Diagnostic("RH002", Severity.ERROR, "third", RuleFamily.ROTORHAZARD),
    )
    selection = RuleSelection.from_selectors(
        REGISTERED_CODES,
        select=["RH002", "STR001"],
    )

    result = selection.apply(ValidationResult(diagnostics, REGISTERED_CODES))

    assert [item.code for item in result.diagnostics] == ["STR001", "RH002"]
    assert result.executed_rules == REGISTERED_CODES
