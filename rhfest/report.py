"""Report module for the RH plugin validation action."""

import logging


class Report:
    def __init__(self) -> None:
        self.results = []

    def add(self, result) -> None:
        self.results.append(result)

    def generate(self) -> None:
        passed = [r for r in self.results if r["status"] == "pass"]
        failed = [r for r in self.results if r["status"] == "fail"]

        logging.info("========== Validation Report ==========")
        logging.info(f"✅ Passed: {len(passed)}")
        logging.info(f"❌ Failed: {len(failed)}")
