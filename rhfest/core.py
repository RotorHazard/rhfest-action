"""Command-line entry point for RHFest repository validation."""

import os
from pathlib import Path

from rhfest.const import RHFEST_VERSION
from rhfest.engine import ValidationEngine
from rhfest.models import ValidationContext
from rhfest.report import Reporter


def detect_base_path() -> Path:
    """Automatically detect the repository path to validate."""
    if workspace := os.getenv("GITHUB_WORKSPACE"):
        return Path(workspace).resolve()
    if Path("/.dockerenv").exists():
        return Path("/repo").resolve()
    return Path.cwd().resolve()


def run_rhfest(base_path: str | Path, reporter: Reporter | None = None) -> int:
    """Validate a repository and return the engine-determined exit status."""
    active_reporter = reporter or Reporter()
    print(f"RHFest version: {RHFEST_VERSION}", file=active_reporter.stream)
    context = ValidationContext(Path(base_path).resolve())
    result = ValidationEngine().run(context, active_reporter)
    return result.exit_code


def main() -> None:
    """Run RHFest for its detected repository and exit with validation status."""
    raise SystemExit(run_rhfest(detect_base_path()))


if __name__ == "__main__":
    main()
