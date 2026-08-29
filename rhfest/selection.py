"""Validated rule selection for reported RHFest diagnostics."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rhfest.models import RuleFamily, ValidationResult

RULE_CODE_PATTERN = re.compile(r"[A-Z]+\d{3}")
FAMILY_SELECTORS = frozenset(family.value for family in RuleFamily)
FAMILY_SELECTOR_EXAMPLES = ", ".join(sorted(FAMILY_SELECTORS))


class RuleSelectionError(ValueError):
    """Raised when configured rule selectors are malformed or unknown."""


@dataclass(frozen=True, slots=True)
class RuleSelection:
    """Resolved rule codes that remain visible after complete analysis."""

    selected_codes: frozenset[str]
    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()

    @classmethod
    def from_selectors(
        cls,
        available_codes: Iterable[str],
        *,
        select: str | Iterable[str] | None = None,
        ignore: str | Iterable[str] | None = None,
    ) -> "RuleSelection":
        """Validate selectors and resolve them against registered rule codes."""
        codes = frozenset(available_codes)
        select_values = cls._parse(select, codes)
        ignore_values = cls._parse(ignore, codes)
        selected_codes = (
            cls._matching_codes(select_values, codes) if select_values else codes
        )
        selected_codes -= cls._matching_codes(ignore_values, codes)
        return cls(
            frozenset(selected_codes),
            tuple(sorted(select_values)),
            tuple(sorted(ignore_values)),
        )

    @property
    def active(self) -> bool:
        """Return whether explicit selection or ignore configuration is active."""
        return bool(self.select or self.ignore)

    @property
    def summary(self) -> str:
        """Return a deterministic, compact description for local output."""
        parts: list[str] = []
        if self.select:
            parts.append(f"select={','.join(self.select)}")
        if self.ignore:
            parts.append(f"ignore={','.join(self.ignore)}")
        return "; ".join(parts)

    def apply(self, result: ValidationResult) -> ValidationResult:
        """Filter diagnostics while retaining the complete execution record."""
        return ValidationResult(
            tuple(
                diagnostic
                for diagnostic in result.diagnostics
                if diagnostic.code in self.selected_codes
            ),
            result.executed_rules,
        )

    @staticmethod
    def _matching_codes(
        selectors: frozenset[str],
        available_codes: frozenset[str],
    ) -> set[str]:
        """Expand exact codes and family selectors to registered codes."""
        return {
            code
            for code in available_codes
            if any(
                code == selector or code.startswith(selector) for selector in selectors
            )
        }

    @classmethod
    def _parse(
        cls,
        raw_values: str | Iterable[str] | None,
        available_codes: frozenset[str],
    ) -> frozenset[str]:
        """Normalize comma-separated selectors and reject invalid values."""
        if raw_values is None:
            return frozenset()
        values = (raw_values,) if isinstance(raw_values, str) else raw_values
        selectors: set[str] = set()
        for value in values:
            for raw_selector in value.split(","):
                selector = raw_selector.strip().upper()
                if not selector:
                    raise RuleSelectionError(
                        "Empty rule selector; expected a rule code or family."
                    )
                cls._validate_selector(selector, available_codes)
                selectors.add(selector)
        return frozenset(selectors)

    @staticmethod
    def _validate_selector(
        selector: str,
        available_codes: frozenset[str],
    ) -> None:
        """Require a registered exact code or known full family prefix."""
        if selector in FAMILY_SELECTORS or selector in available_codes:
            return
        if selector.isalpha() or RULE_CODE_PATTERN.fullmatch(selector):
            message = f"Unknown rule selector: {selector!r}."
            raise RuleSelectionError(message)
        message = (
            f"Malformed rule selector: {selector!r}; expected "
            f"{FAMILY_SELECTOR_EXAMPLES}, "
            "or an exact code such as RH002."
        )
        raise RuleSelectionError(message)
