"""Command-line entry point for RHFest repository validation."""

import argparse
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from rhfest.const import RHFEST_VERSION
from rhfest.engine import ValidationEngine
from rhfest.models import ValidationContext
from rhfest.report import Reporter
from rhfest.selection import RuleSelection, RuleSelectionError


def detect_base_path() -> Path:
    """Automatically detect the repository path to validate."""
    if workspace := os.getenv("GITHUB_WORKSPACE"):
        return Path(workspace).resolve()
    if Path("/.dockerenv").exists():
        return Path("/repo").resolve()
    return Path.cwd().resolve()


def run_rhfest(
    base_path: str | Path,
    reporter: Reporter | None = None,
    *,
    select: str | Iterable[str] | None = None,
    ignore: str | Iterable[str] | None = None,
) -> int:
    """Validate a repository and return the engine-determined exit status."""
    active_reporter = reporter or Reporter()
    engine = ValidationEngine()
    selection = RuleSelection.from_selectors(
        (rule.code for rule in engine.rules),
        select=select,
        ignore=ignore,
    )
    print(f"RHFest version: {RHFEST_VERSION}", file=active_reporter.stream)
    if selection.active:
        active_reporter.report_configuration(selection.summary)
    context = ValidationContext(Path(base_path).resolve())
    result = engine.run(context, active_reporter, selection=selection)
    return result.exit_code


def _environment_selectors(name: str) -> str | None:
    """Read local configuration before the equivalent Action input."""
    local_value = os.getenv(f"RHFEST_{name}")
    value = local_value if local_value is not None else os.getenv(f"INPUT_{name}")
    return value or None


def _parser() -> argparse.ArgumentParser:
    """Build the stable local and container command-line contract."""
    parser = argparse.ArgumentParser(prog="rhfest")
    parser.add_argument(
        "--select",
        action="append",
        metavar="SELECTORS",
        help="Select exact rule codes or families (comma-separated; repeatable).",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        metavar="SELECTORS",
        help="Ignore exact rule codes or families after selection.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run RHFest for its detected repository and exit with validation status."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    select = (
        arguments.select
        if arguments.select is not None
        else _environment_selectors("SELECT")
    )
    ignore = (
        arguments.ignore
        if arguments.ignore is not None
        else _environment_selectors("IGNORE")
    )
    try:
        status = run_rhfest(detect_base_path(), select=select, ignore=ignore)
    except RuleSelectionError as error:
        parser.error(str(error))
    raise SystemExit(status)


if __name__ == "__main__":
    main()
