"""End-to-end regression and process-status tests."""

from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from rhfest.core import run_rhfest
from rhfest.report import Reporter


@pytest.mark.parametrize(
    ("manifest_change", "expected_status"),
    [
        (lambda manifest: None, 0),
        (lambda manifest: manifest.update(version="invalid"), 1),
        (lambda manifest: manifest.update(domain="other"), 1),
    ],
)
def test_representative_repository_outcomes(
    repository_factory: Callable[[dict[str, Any], str], Path],
    valid_manifest: dict[str, Any],
    manifest_change: Callable[[dict[str, Any]], object],
    expected_status: int,
) -> None:
    """Repositories accepted/rejected before migration retain their outcome."""
    manifest_change(valid_manifest)
    repository = repository_factory(valid_manifest)
    stream = StringIO()

    status = run_rhfest(
        repository,
        Reporter(stream, github_actions=False, show_debug_tree=False),
    )

    assert status == expected_status
    if expected_status:
        assert "Found 1 error." in stream.getvalue()
    else:
        assert "All checks passed!" in stream.getvalue()
