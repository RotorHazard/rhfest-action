"""Tests for migrated manifest schema and domain behavior."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from rhfest.engine import ValidationEngine
from rhfest.models import ValidationContext


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


def test_invalid_json_retains_existing_exception_policy(tmp_path: Path) -> None:
    """The architecture migration does not silently redefine JSON errors."""
    plugin_dir = tmp_path / "custom_plugins" / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        validate(tmp_path)
