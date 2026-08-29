"""Tests for reusable Python parsing and RotorHazard-specific rules."""

import ast
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from rhfest.engine import ValidationEngine
from rhfest.models import Diagnostic, RuleFamily, Severity, ValidationContext
from rhfest.rules import PythonSourceRule

PRIVATE_MESSAGE = (
    "Private RHAPI member '_racecontext' accessed. Plugins must use the public "
    "RHAPI interface."
)
GENERIC_HELP = "Replace `_racecontext` access with a documented public RHAPI operation."
INITIALIZE_HELP = (
    "Define one synchronous, undecorated top-level `def initialize(rhapi)` "
    "following the RotorHazard plugin contract."
)


def origin_help(namespace: str) -> str:
    """Return the expected version-independent namespace guidance."""
    return (
        f"This value originates from `rhapi.{namespace}`; replace `_racecontext` "
        "access with a documented public RHAPI operation."
    )


def write_plugin_source(repository: Path, relative_path: str, source: str) -> Path:
    """Write a Python file below the discovered example plugin directory."""
    path = repository / "custom_plugins" / "example" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def source_diagnostics(repository: Path) -> tuple[Diagnostic, ...]:
    """Run the default engine and return only source-family diagnostics."""
    result = ValidationEngine().run(ValidationContext(repository))
    return tuple(
        item for item in result.diagnostics if item.family is RuleFamily.ROTORHAZARD
    )


@pytest.mark.parametrize(
    ("expression", "expected_help"),
    [
        (
            "rhapi._racecontext",
            GENERIC_HELP,
        ),
        ("rhapi.db._racecontext", origin_help("db")),
        ("rhapi.race._racecontext", origin_help("race")),
        ("rhapi.events._racecontext", origin_help("events")),
        (
            "rhapi.future_namespace._racecontext",
            origin_help("future_namespace"),
        ),
    ],
)
def test_rh001_detects_direct_and_namespace_access(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    expression: str,
    expected_help: str,
) -> None:
    """Root and public-namespace chains retain RHAPI provenance."""
    repository = repository_factory(valid_manifest)
    line = f"    value = {expression}"
    write_plugin_source(repository, "__init__.py", f"def initialize(rhapi):\n{line}\n")

    diagnostics = source_diagnostics(repository)

    assert len(diagnostics) == 1
    assert diagnostics[0] == Diagnostic(
        "RH001",
        Severity.ERROR,
        PRIVATE_MESSAGE,
        RuleFamily.ROTORHAZARD,
        "custom_plugins/example/__init__.py",
        2,
        line.index("_racecontext") + 1,
        2,
        line.index("_racecontext") + len("_racecontext") + 1,
        expected_help,
    )


@pytest.mark.parametrize(
    ("assignment", "expected_help"),
    [
        (
            "api = rhapi\n    value = api._racecontext",
            GENERIC_HELP,
        ),
        (
            "database = rhapi.db\n    value = database._racecontext",
            origin_help("db"),
        ),
    ],
)
def test_rh001_detects_simple_aliases(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    assignment: str,
    expected_help: str,
) -> None:
    """Simple local aliases preserve root or namespace provenance."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        f"def initialize(rhapi):\n    {assignment}\n",
    )

    diagnostics = source_diagnostics(repository)

    assert [item.code for item in diagnostics] == ["RH001"]
    assert diagnostics[0].help == expected_help


def test_rh001_collects_nested_violations_in_deterministic_order(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Files and accesses within each file follow deterministic source order."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "nested/checks.py",
        "def callback(rhapi):\n"
        "    first = rhapi.db._racecontext\n"
        "    second = rhapi.race._racecontext\n",
    )
    write_plugin_source(
        repository,
        "z_last.py",
        "def initialize(rhapi):\n    value = rhapi._racecontext\n",
    )

    diagnostics = source_diagnostics(repository)

    assert [(item.path, item.line) for item in diagnostics] == [
        ("custom_plugins/example/nested/checks.py", 2),
        ("custom_plugins/example/nested/checks.py", 3),
        ("custom_plugins/example/z_last.py", 2),
    ]


def test_rh001_error_fails_validation(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Private RHAPI access contributes a failing engine result."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "def initialize(rhapi):\n    return rhapi._racecontext\n",
    )

    result = ValidationEngine().run(ValidationContext(repository))

    assert result.exit_code == 1
    assert [item.code for item in result.diagnostics] == ["RH001"]


def test_rh001_accepts_public_access_and_unrelated_private_members(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Public calls, text, and values without provenance do not trigger RH001."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "# rhapi._racecontext\n"
        "TEXT = 'rhapi._racecontext'\n"
        "def initialize(rhapi):\n"
        "    pilots = rhapi.db.pilots\n"
        "    rhapi.race.stage({})\n"
        "    rhapi.events.on('event', handler)\n"
        "    unrelated = object()\n"
        "    value = unrelated._racecontext\n"
        "    rhapi_client = object()\n"
        "    other = rhapi_client._racecontext\n"
        "def helper(value):\n"
        "    return value._racecontext\n",
    )

    assert source_diagnostics(repository) == ()


def test_rh001_respects_reassignment_and_parameter_shadowing(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Overwritten aliases and unrelated local parameters lose provenance."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "def initialize(rhapi):\n"
        "    api = rhapi\n"
        "    api = object()\n"
        "    value = api._racecontext\n"
        "    def helper(api):\n"
        "        return api._racecontext\n"
        "    values = [rhapi._racecontext for rhapi in unrelated_values]\n",
    )

    assert source_diagnostics(repository) == ()


def test_rh001_retains_unmodified_provenance_after_complex_control_flow(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Try and match blocks do not erase aliases they never reassign."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "def initialize(rhapi):\n"
        "    try:\n"
        "        operation()\n"
        "    except RuntimeError:\n"
        "        recover()\n"
        "    match value:\n"
        "        case _:\n"
        "            pass\n"
        "    return rhapi._racecontext\n",
    )

    diagnostics = source_diagnostics(repository)

    assert [(item.code, item.line) for item in diagnostics] == [("RH001", 9)]


def test_rh001_uses_generic_help_for_ambiguous_branch_namespace(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Different proven namespaces retain RHAPI provenance without guessing."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "def initialize(rhapi):\n"
        "    if condition:\n"
        "        api = rhapi.db\n"
        "    else:\n"
        "        api = rhapi.race\n"
        "    return api._racecontext\n",
    )

    diagnostics = source_diagnostics(repository)

    assert len(diagnostics) == 1
    assert diagnostics[0].help == GENERIC_HELP


def test_rh001_does_not_follow_calls_or_containers(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """The initial provenance model avoids uncertain transformations."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "def initialize(rhapi):\n"
        "    called = identity(rhapi)\n"
        "    called._racecontext\n"
        "    contained = [rhapi][0]\n"
        "    contained._racecontext\n",
    )

    assert source_diagnostics(repository) == ()


def test_source_files_outside_plugin_directory_are_ignored(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Source discovery remains scoped to the validated plugin directory."""
    repository = repository_factory(valid_manifest)
    outside = repository / "tools.py"
    outside.write_text(
        "def initialize(rhapi):\n    return rhapi._racecontext\n",
        encoding="utf-8",
    )

    assert source_diagnostics(repository) == ()


def test_plugin_symlink_outside_repository_is_rejected(
    tmp_path: Path,
    valid_manifest: dict[str, Any],
) -> None:
    """Source discovery never follows the plugin root outside the checkout."""
    repository = tmp_path / "repository"
    plugin_parent = repository / "custom_plugins"
    plugin_parent.mkdir(parents=True)
    external_plugin = tmp_path / "external" / "example"
    external_plugin.mkdir(parents=True)
    (external_plugin / "manifest.json").write_text(
        json.dumps(valid_manifest),
        encoding="utf-8",
    )
    (external_plugin / "__init__.py").touch()
    (external_plugin / "private.py").write_text(
        "def initialize(rhapi):\n    return rhapi._racecontext\n",
        encoding="utf-8",
    )
    (plugin_parent / "example").symlink_to(external_plugin, target_is_directory=True)
    context = ValidationContext(
        repository,
        plugin_dir=plugin_parent / "example",
    )

    result = ValidationEngine((PythonSourceRule(),)).run(context)
    diagnostics = tuple(
        item for item in result.diagnostics if item.family is RuleFamily.ROTORHAZARD
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "RH000"
    assert diagnostics[0].path == "custom_plugins/example"
    assert diagnostics[0].message == (
        "Plugin source directory resolves outside the repository."
    )
    assert context.python_sources == ()


def test_rh000_reads_the_resolved_source_path(
    monkeypatch: pytest.MonkeyPatch,
    valid_manifest: dict[str, Any],
    tmp_path: Path,
) -> None:
    """A source symlink cannot redirect the read after its boundary check."""
    repository = tmp_path / "repository"
    plugin_dir = repository / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    (plugin_dir / "manifest.json").write_text(
        json.dumps(valid_manifest),
        encoding="utf-8",
    )
    source_target = plugin_dir / "source.txt"
    source_target.write_text("VALUE = 1\n", encoding="utf-8")
    source_path = plugin_dir / "linked.py"
    source_path.symlink_to(source_target)
    external_source = tmp_path / "external.py"
    external_source.write_text(
        "def initialize(rhapi):\n    return rhapi._racecontext\n",
        encoding="utf-8",
    )
    original_read_text = Path.read_text

    def redirecting_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == source_path:
            path.unlink()
            path.symlink_to(external_source)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", redirecting_read_text)

    result = ValidationEngine().run(ValidationContext(repository))

    assert result.diagnostics == ()
    assert source_path.resolve() == source_target


def test_rh000_reports_syntax_errors_without_blocking_other_files(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Parser failures use diagnostics while valid ASTs still reach RH001."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(repository, "broken.py", "def broken(:\n")
    write_plugin_source(
        repository,
        "valid.py",
        "def initialize(rhapi):\n    return rhapi._racecontext\n",
    )

    diagnostics = source_diagnostics(repository)

    assert [item.code for item in diagnostics] == ["RH000", "RH001"]
    assert diagnostics[0].path == "custom_plugins/example/broken.py"
    assert diagnostics[0].message.startswith("Unable to parse Python source:")


def test_python_files_are_parsed_once_for_all_source_rules(
    monkeypatch: pytest.MonkeyPatch,
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """The source context is reusable by every RH rule without reparsing."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(repository, "a.py", "VALUE = 1\n")
    write_plugin_source(repository, "nested/b.py", "VALUE = 2\n")
    parse_calls: list[str] = []
    original_parse = ast.parse

    def counting_parse(source: str, filename: str) -> ast.Module:
        parse_calls.append(filename)
        return original_parse(source, filename=filename)

    monkeypatch.setattr("rhfest.rules.ast.parse", counting_parse)
    context = ValidationContext(repository)

    ValidationEngine().run(context)

    assert parse_calls == [
        "custom_plugins/example/__init__.py",
        "custom_plugins/example/a.py",
        "custom_plugins/example/nested/b.py",
    ]
    assert context.python_sources is not None
    assert [item.relative_path for item in context.python_sources] == parse_calls


def test_rh002_reports_missing_top_level_initialize(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Names in other files do not satisfy the __init__.py entry point."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(repository, "__init__.py", "VALUE = 1\n")
    write_plugin_source(repository, "other.py", "def initialize(rhapi):\n    pass\n")

    diagnostics = source_diagnostics(repository)

    assert diagnostics == (
        Diagnostic(
            "RH002",
            Severity.ERROR,
            "Expected a top-level `def initialize(rhapi)` entry point.",
            RuleFamily.ROTORHAZARD,
            "custom_plugins/example/__init__.py",
            help=INITIALIZE_HELP,
        ),
    )


@pytest.mark.parametrize(
    "definition",
    [
        "def initialize(rhapi):\n    pass\n",
        "def initialize(rhapi: object) -> None:\n    pass\n",
        "def initialize(rhapi, /):\n    pass\n",
    ],
)
def test_rh002_accepts_supported_initialize_definitions(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    definition: str,
) -> None:
    """A single positional RHAPI parameter and annotations are supported."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(repository, "__init__.py", definition)

    assert source_diagnostics(repository) == ()


@pytest.mark.parametrize(
    "definition",
    [
        "def initialize():\n    pass\n",
        "def initialize(api):\n    pass\n",
        "def initialize(rhapi, extra):\n    pass\n",
        "def initialize(rhapi=None):\n    pass\n",
        "def initialize(*args):\n    pass\n",
        "def initialize(**kwargs):\n    pass\n",
        "def initialize(*, rhapi):\n    pass\n",
        "async def initialize(rhapi):\n    pass\n",
        "@decorator\ndef initialize(rhapi):\n    pass\n",
    ],
)
def test_rh002_rejects_ambiguous_initialize_signatures(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    definition: str,
) -> None:
    """Defaults, alternate names, async, decorators, and variadics are rejected."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(repository, "__init__.py", definition)

    diagnostics = source_diagnostics(repository)

    assert [item.code for item in diagnostics] == ["RH002"]
    assert diagnostics[0].message == (
        "Initialize entry point must use the supported "
        "`def initialize(rhapi)` signature."
    )
    expected_line = 2 if definition.startswith("@") else 1
    expected_column = 11 if definition.startswith("async ") else 5
    assert (
        diagnostics[0].line,
        diagnostics[0].column,
        diagnostics[0].end_line,
        diagnostics[0].end_column,
    ) == (expected_line, expected_column, expected_line, expected_column + 10)
    assert diagnostics[0].help == INITIALIZE_HELP


@pytest.mark.parametrize(
    "source",
    [
        "def outer():\n    def initialize(rhapi):\n        pass\n",
        "class Plugin:\n    def initialize(self, rhapi):\n        pass\n",
    ],
)
def test_rh002_ignores_nested_and_class_initialize_definitions(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    source: str,
) -> None:
    """Only a direct module child can provide the plugin entry point."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(repository, "__init__.py", source)

    diagnostics = source_diagnostics(repository)

    assert [item.code for item in diagnostics] == ["RH002"]
    assert diagnostics[0].line is None


def test_rh002_ignores_non_definition_initialize_names(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Imports, assignments, comments, strings, and lambdas are not definitions."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "# def initialize(rhapi): pass\n"
        "TEXT = 'def initialize(rhapi)'\n"
        "from helpers import initialize\n"
        "initialize = lambda rhapi: None\n",
    )

    diagnostics = source_diagnostics(repository)

    assert [item.code for item in diagnostics] == ["RH002"]


def test_rh002_rejects_multiple_overload_style_definitions(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Multiple definitions are ambiguous even when one is an implementation."""
    repository = repository_factory(valid_manifest)
    write_plugin_source(
        repository,
        "__init__.py",
        "from typing import overload\n"
        "@overload\n"
        "def initialize(rhapi: object) -> None: ...\n"
        "def initialize(rhapi):\n"
        "    pass\n",
    )

    diagnostics = source_diagnostics(repository)

    assert [item.code for item in diagnostics] == ["RH002"]
    assert diagnostics[0].message == (
        "Expected exactly one top-level initialize definition; found 2."
    )
    assert (diagnostics[0].line, diagnostics[0].column) == (3, 5)
