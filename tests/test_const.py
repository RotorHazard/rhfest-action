"""Tests for RHFest constants resolved from the runtime environment."""

import pytest

from rhfest.const import _resolve_rhfest_version


@pytest.mark.parametrize(
    ("build_version", "action_ref", "expected"),
    [
        ("v3.2.1", "v3", "v3.2.1"),
        (None, "v3.2.0", "v3.2.0"),
        (None, None, "dev"),
    ],
)
def test_resolve_rhfest_version(
    monkeypatch: pytest.MonkeyPatch,
    build_version: str | None,
    action_ref: str | None,
    expected: str,
) -> None:
    """Prefer a release build, then the Action ref, then local development."""
    if build_version is None:
        monkeypatch.delenv("RHFEST_VERSION", raising=False)
    else:
        monkeypatch.setenv("RHFEST_VERSION", build_version)

    if action_ref is None:
        monkeypatch.delenv("GITHUB_ACTION_REF", raising=False)
    else:
        monkeypatch.setenv("GITHUB_ACTION_REF", action_ref)

    assert _resolve_rhfest_version() == expected
