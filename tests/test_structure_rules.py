"""Tests for migrated repository structure behavior."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rhfest.engine import ValidationEngine
from rhfest.models import RuleFamily, Severity, ValidationContext


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
    plugin_dir = tmp_path / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").touch()

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR003"]
    assert result.diagnostics[0].path == "custom_plugins/example/manifest.json"


def test_plugin_entry_must_be_a_directory(tmp_path: Path) -> None:
    """STR004 rejects a file used as the single plugin entry."""
    plugin_parent = tmp_path / "custom_plugins"
    plugin_parent.mkdir()
    (plugin_parent / "example").touch()

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR004"]
    assert result.diagnostics[0].path == "custom_plugins/example"
    assert result.diagnostics[0].message == (
        "Expected the plugin entry to be a directory."
    )
    assert result.executed_rules == ("STR001", "STR002", "STR004")


def test_plugin_entry_point_is_required(tmp_path: Path) -> None:
    """STR004 locates a missing entry point below the discovered plugin."""
    (tmp_path / "custom_plugins" / "example").mkdir(parents=True)

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR004"]
    assert result.diagnostics[0].path == "custom_plugins/example/__init__.py"
    assert result.diagnostics[0].message == (
        "Expected a regular __init__.py file below the plugin entry."
    )
    assert result.diagnostics[0].family is RuleFamily.STRUCTURE
    assert result.diagnostics[0].severity is Severity.ERROR


def test_plugin_entry_point_must_be_a_file(tmp_path: Path) -> None:
    """STR004 rejects a directory named __init__.py."""
    entry_point = tmp_path / "custom_plugins" / "example" / "__init__.py"
    entry_point.mkdir(parents=True)

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["STR004"]
    assert result.diagnostics[0].path == "custom_plugins/example/__init__.py"


def test_plugin_entry_cannot_resolve_outside_repository(tmp_path: Path) -> None:
    """STR004 rejects a plugin-directory symlink that crosses the boundary."""
    repository = tmp_path / "repository"
    plugin_parent = repository / "custom_plugins"
    plugin_parent.mkdir(parents=True)
    external_plugin = tmp_path / "external-plugin"
    external_plugin.mkdir()
    (external_plugin / "__init__.py").touch()
    (plugin_parent / "example").symlink_to(
        external_plugin,
        target_is_directory=True,
    )

    result = validate(repository)

    assert [item.code for item in result.diagnostics] == ["STR004"]
    assert result.diagnostics[0].path == "custom_plugins/example"
    assert result.diagnostics[0].message == (
        "Plugin entry resolves outside the repository."
    )


def test_plugin_entry_point_cannot_resolve_outside_repository(
    tmp_path: Path,
) -> None:
    """STR004 rejects an entry-point symlink that crosses the boundary."""
    repository = tmp_path / "repository"
    plugin_dir = repository / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    external_entry_point = tmp_path / "external-init.py"
    external_entry_point.touch()
    (plugin_dir / "__init__.py").symlink_to(external_entry_point)

    result = validate(repository)

    assert [item.code for item in result.diagnostics] == ["STR004"]
    assert result.diagnostics[0].path == "custom_plugins/example/__init__.py"
    assert result.diagnostics[0].message == (
        "Plugin entry point resolves outside the repository."
    )


def test_successful_structure_discovers_context(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """The successful path supplies explicit context to manifest rules."""
    repository = repository_factory(valid_manifest)
    context = ValidationContext(repository)

    result = ValidationEngine().run(context)

    assert result.diagnostics == ()
    assert context.plugin_entry == repository / "custom_plugins" / "example"
    assert context.plugin_dir == repository / "custom_plugins" / "example"
    assert context.manifest_path == context.plugin_dir / "manifest.json"
    assert result.executed_rules == (
        "STR001",
        "STR002",
        "STR004",
        "STR003",
        "MAN000",
        "MAN001",
        "MAN002",
        "RH000",
        "RH001",
    )
