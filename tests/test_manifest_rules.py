"""Tests for migrated manifest schema and domain behavior."""

import json
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from rhfest.engine import ValidationEngine
from rhfest.models import RuleFamily, Severity, ValidationContext
from rhfest.report import Reporter


def validate(path: Path):  # noqa: ANN201
    """Run all built-in rules for a repository."""
    return ValidationEngine().run(ValidationContext(path))


@pytest.mark.parametrize(
    ("change", "expected_fragment"),
    [
        (lambda manifest: manifest.pop("name"), "required key not provided"),
        (lambda manifest: manifest.update(version="one"), "does not match"),
        (lambda manifest: manifest.update(unexpected=True), "extra keys not allowed"),
    ],
)
def test_manifest_schema_failures(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    change: Callable[[dict[str, Any]], object],
    expected_fragment: str,
) -> None:
    """MAN001 retains missing, malformed, and extra-field constraints."""
    change(valid_manifest)

    result = validate(repository_factory(valid_manifest))

    assert result.exit_code == 1
    assert "MAN001" in [item.code for item in result.diagnostics]
    assert any(expected_fragment in item.message for item in result.diagnostics)


def test_schema_rule_returns_multiple_diagnostics(
    repository_factory: Callable[[dict[str, Any], str], Path],
) -> None:
    """One schema-backed rule can return multiple ordered findings."""
    result = validate(repository_factory({"domain": "example"}))

    assert len(result.diagnostics) == 4
    assert {item.code for item in result.diagnostics} == {"MAN001"}
    assert [item.message for item in result.diagnostics] == [
        "Validation error in [description]: required key not provided",
        "Validation error in [name]: required key not provided",
        "Validation error in [required_rhapi_version]: required key not provided",
        "Validation error in [version]: required key not provided",
    ]


def test_domain_mismatch(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """MAN002 compares the manifest domain with its parent folder."""
    result = validate(repository_factory(valid_manifest, "different"))

    assert [item.code for item in result.diagnostics] == ["MAN002"]
    assert result.diagnostics[0].path == "custom_plugins/different/manifest.json"


def test_valid_manifest_with_all_optional_fields(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Current optional manifest fields remain accepted."""
    valid_manifest.update(
        documentation_uri="https://example.com/docs",
        dependencies=["package-name>=1.2", "git+https://example.com/repo.git"],
        zip_filename="example.zip",
        author="Author",
        author_uri="https://example.com",
        info_uri=None,
        license="MIT",
        license_uri=None,
    )

    result = validate(repository_factory(valid_manifest))

    assert result.diagnostics == ()
    assert result.exit_code == 0


def test_dormant_zip_release_rule_stays_disabled(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """zip_release remains an extra field, rather than enabling dormant policy."""
    valid_manifest["zip_release"] = True

    result = validate(repository_factory(valid_manifest))

    assert [item.code for item in result.diagnostics] == ["MAN001"]
    assert "extra keys not allowed" in result.diagnostics[0].message


def test_man000_reports_invalid_json_with_source_location(tmp_path: Path) -> None:
    """Malformed JSON becomes one precise diagnostic instead of a traceback."""
    plugin_dir = tmp_path / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    manifest_path = plugin_dir / "manifest.json"
    manifest_path.write_text(
        '{\n  "domain": "example",\n  "name":,\n}\n',
        encoding="utf-8",
    )
    context = ValidationContext(tmp_path)

    result = ValidationEngine().run(context)

    assert result.exit_code == 1
    assert [item.code for item in result.diagnostics] == ["MAN000"]
    diagnostic = result.diagnostics[0]
    assert diagnostic.family is RuleFamily.MANIFEST
    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.message == "Unable to parse manifest JSON: Expecting value."
    assert diagnostic.path == "custom_plugins/example/manifest.json"
    assert (diagnostic.line, diagnostic.column) == (3, 10)
    assert (diagnostic.end_line, diagnostic.end_column) == (3, 11)
    assert diagnostic.help == "Fix the JSON syntax in manifest.json."
    assert context.manifest_source == manifest_path.read_text(encoding="utf-8")
    assert context.manifest_document is None
    assert "MAN001" not in result.executed_rules
    assert "MAN002" not in result.executed_rules


def test_man000_reports_invalid_utf8(tmp_path: Path) -> None:
    """Unicode decoding failures use the shared diagnostic path."""
    plugin_dir = tmp_path / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    (plugin_dir / "manifest.json").write_bytes(b"\xff")

    result = validate(tmp_path)

    assert [item.code for item in result.diagnostics] == ["MAN000"]
    assert result.diagnostics[0].message.startswith("Unable to read manifest JSON:")
    assert result.diagnostics[0].path == "custom_plugins/example/manifest.json"


def test_man000_rejects_manifest_symlink_outside_repository(
    tmp_path: Path,
    valid_manifest: dict[str, Any],
) -> None:
    """Manifest preparation never reads through a path outside the checkout."""
    repository = tmp_path / "repository"
    plugin_dir = repository / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    external_manifest = tmp_path / "external-manifest.json"
    external_manifest.write_text(json.dumps(valid_manifest), encoding="utf-8")
    (plugin_dir / "manifest.json").symlink_to(external_manifest)

    result = validate(repository)

    assert [item.code for item in result.diagnostics] == ["MAN000"]
    assert result.diagnostics[0].message == (
        "Manifest file resolves outside the repository."
    )
    assert result.diagnostics[0].path == "custom_plugins/example/manifest.json"


def test_man000_reads_the_resolved_manifest_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_manifest: dict[str, Any],
) -> None:
    """A symlink cannot redirect the read after its target passed validation."""
    repository = tmp_path / "repository"
    plugin_dir = repository / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    manifest_target = plugin_dir / "manifest-target.json"
    manifest_target.write_text(json.dumps(valid_manifest), encoding="utf-8")
    manifest_path = plugin_dir / "manifest.json"
    manifest_path.symlink_to(manifest_target)
    external_manifest = tmp_path / "external-manifest.json"
    external_manifest.write_text("not json", encoding="utf-8")
    original_read_text = Path.read_text

    def redirecting_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == manifest_path:
            path.unlink()
            path.symlink_to(external_manifest)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", redirecting_read_text)

    result = validate(repository)

    assert result.diagnostics == ()
    assert manifest_path.resolve() == manifest_target


def test_man000_reports_file_read_errors(
    monkeypatch: pytest.MonkeyPatch,
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Operating-system read failures do not escape as exceptions."""
    repository = repository_factory(valid_manifest)
    manifest_path = repository / "custom_plugins" / "example" / "manifest.json"
    original_read_text = Path.read_text

    def failing_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == manifest_path:
            raise OSError("permission denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)

    result = validate(repository)

    assert [item.code for item in result.diagnostics] == ["MAN000"]
    assert result.diagnostics[0].message == (
        "Unable to read manifest JSON: permission denied."
    )
    assert "MAN001" not in result.executed_rules
    assert "MAN002" not in result.executed_rules


def test_parsed_json_null_reaches_schema_validation(tmp_path: Path) -> None:
    """A parsed null is distinct from the absence of parsed manifest context."""
    plugin_dir = tmp_path / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    (plugin_dir / "manifest.json").write_text("null\n", encoding="utf-8")
    context = ValidationContext(tmp_path)

    result = ValidationEngine().run(context)

    assert [item.code for item in result.diagnostics] == ["MAN001"]
    assert context.manifest_document is not None
    assert context.manifest_document.data is None
    assert "MAN000" in result.executed_rules
    assert "MAN001" in result.executed_rules


def test_manifest_is_read_and_parsed_once_with_reporting(
    monkeypatch: pytest.MonkeyPatch,
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
) -> None:
    """Rules and source rendering reuse the prepared manifest document."""
    valid_manifest["version"] = "invalid"
    repository = repository_factory(valid_manifest)
    manifest_path = repository / "custom_plugins" / "example" / "manifest.json"
    read_calls = 0
    parse_calls = 0
    original_read_text = Path.read_text
    original_loads = json.loads

    def counting_read_text(path: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_calls
        if path == manifest_path:
            read_calls += 1
        return original_read_text(path, *args, **kwargs)

    def counting_loads(value: str, *args: object, **kwargs: object) -> Any:
        nonlocal parse_calls
        parse_calls += 1
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    monkeypatch.setattr("rhfest.rules.json.loads", counting_loads)
    stream = StringIO()
    context = ValidationContext(repository)

    result = ValidationEngine().run(
        context,
        Reporter(stream, github_actions=False, show_debug_tree=False),
    )

    assert [item.code for item in result.diagnostics] == ["MAN001"]
    assert read_calls == 1
    assert parse_calls == 1
    assert context.manifest_document is not None
    assert context.manifest_document.source == context.manifest_source
    assert '"version": "invalid"' in stream.getvalue()


def test_man000_uses_github_annotation_reporting(tmp_path: Path) -> None:
    """Manifest parser diagnostics carry full GitHub annotation metadata."""
    plugin_dir = tmp_path / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "def initialize(rhapi):\n    pass\n",
        encoding="utf-8",
    )
    (plugin_dir / "manifest.json").write_text('{"name": }\n', encoding="utf-8")
    stream = StringIO()

    result = ValidationEngine().run(
        ValidationContext(tmp_path),
        Reporter(stream, github_actions=True, show_debug_tree=False),
    )

    assert result.exit_code == 1
    assert stream.getvalue().startswith(
        "::error title=rhfest (MAN000),"
        "file=custom_plugins/example/manifest.json,line=1,col=10,"
        "endLine=1,endColumn=11::"
    )
