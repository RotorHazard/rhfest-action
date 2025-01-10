"""Report module for the RH plugin validation action."""

import logging
import sys


class Report:
    """Validation report class."""

    def __init__(self) -> None:
        """Initialize the report."""
        self.results = []

    def add(self, result: dict[str, str]) -> None:
        """Add a result to the report.

        Args:
        ----
            result (dict): The result to add to the report.

        """
        self.results.append(result)

    def generate(self) -> None:
        """Generate the validation report."""
        passed = [r for r in self.results if r["status"] == "pass"]
        failed = [r for r in self.results if r["status"] == "fail"]

        logging.info("========== Validation Report ==========")
        logging.info(f"✅ Passed: {len(passed)}")
        logging.info(f"❌ Failed: {len(failed)}")

        # Exit with a non-zero status code if there are failed checks.
        if len(failed) > 0:
            sys.exit(1)
        else:
            sys.exit(0)
