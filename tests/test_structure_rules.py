"""Tests for migrated repository structure behavior."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rhfest.engine import ValidationEngine
from rhfest.models import ValidationContext


def validate(path: Path):  # noqa: ANN201
    """Run the default engine for a test repository."""
    return ValidationEngine().run(ValidationContext(path))


def test_missing_custom_plugins(tmp_path: Path) -> None:
    """STR001 reports a missing root entry and blocks later phases."""
    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR001"]
    assert result.executed_rules == ("STR001",)
    assert result.exit_code == 1


def test_empty_custom_plugins(tmp_path: Path) -> None:
    """STR002 reports an empty custom_plugins entry."""
    (tmp_path / "custom_plugins").mkdir()

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR002"]
    assert result.executed_rules == ("STR001", "STR002")


def test_multiple_plugin_entries_are_sorted(tmp_path: Path) -> None:
    """STR002 retains exactly-one semantics and deterministic names."""
    for name in ("zeta", "alpha"):
        (tmp_path / "custom_plugins" / name).mkdir(parents=True)

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR002"]
    assert "alpha, zeta" in result.diagnostics[0].message


def test_missing_manifest(tmp_path: Path) -> None:
    """STR003 reports a missing manifest below the single plugin entry."""
    (tmp_path / "custom_plugins" / "example").mkdir(parents=True)

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR003"]
    assert result.diagnostics[0].path == "custom_plugins/example/manifest.json"


def test_successful_structure_discovers_context(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """The successful path supplies explicit context to manifest rules."""
    repository = repository_factory(valid_manifest)
    context = ValidationContext(repository)

    result = ValidationEngine().run(context)

    assert result.diagnostics == ()
    assert context.plugin_dir == repository / "custom_plugins" / "example"
    assert context.manifest_path == context.plugin_dir / "manifest.json"
    assert result.executed_rules == (
        "STR001",
        "STR002",
        "STR003",
        "MAN001",
        "MAN002",
        "RH000",
        "RH001",
    )
