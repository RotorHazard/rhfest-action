"""Deterministic validation engine for RHFest rules."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rhfest.models import (
    Capability,
    Diagnostic,
    RuleFamily,
    RulePhase,
    Severity,
    ValidationContext,
    ValidationResult,
)
from rhfest.report import Reporter
from rhfest.rules import DEFAULT_RULES, Rule
from rhfest.selection import RuleSelection


@dataclass(frozen=True, slots=True)
class PhaseDefinition:
    """Ordering, namespace, and successful-phase prerequisites."""

    order: int
    family: RuleFamily
    requires_success: frozenset[RulePhase] = frozenset()


PHASES = {
    RulePhase.STRUCTURE: PhaseDefinition(10, RuleFamily.STRUCTURE),
    RulePhase.MANIFEST: PhaseDefinition(
        20,
        RuleFamily.MANIFEST,
        frozenset({RulePhase.STRUCTURE}),
    ),
    RulePhase.SOURCE: PhaseDefinition(
        30,
        RuleFamily.ROTORHAZARD,
        frozenset({RulePhase.STRUCTURE}),
    ),
}


class RuleRegistrationError(ValueError):
    """Raised when registered rule metadata violates the engine contract."""


class ValidationEngine:
    """Execute applicable rules in stable phase/order/code order."""

    def __init__(self, rules: Iterable[Rule] = DEFAULT_RULES) -> None:
        """Register a deterministic snapshot of the supplied rules."""
        registered_rules = tuple(rules)
        self._validate_registry(registered_rules)
        self.rules = tuple(
            sorted(
                registered_rules,
                key=lambda rule: (PHASES[rule.phase].order, rule.order, rule.code),
            )
        )

    def run(
        self,
        context: ValidationContext,
        reporter: Reporter | None = None,
        selection: RuleSelection | None = None,
    ) -> ValidationResult:
        """Execute rules, collect findings, optionally report, and return status."""
        diagnostics: list[Diagnostic] = []
        executed_rules: list[str] = []
        failed_phases: set[RulePhase] = set()

        for rule in self.rules:
            if self._phase_blocked(rule.phase, failed_phases):
                continue
            if not rule.is_applicable(context):
                continue
            executed_rules.append(rule.code)
            findings = rule.check(context)
            self._validate_findings(rule, findings)
            diagnostics.extend(findings)
            if any(item.severity is Severity.ERROR for item in findings):
                failed_phases.add(rule.phase)

        result = ValidationResult(tuple(diagnostics), tuple(executed_rules))
        if selection is not None:
            result = selection.apply(result)
        if reporter is not None:
            reporter.report(result, context)
        return result

    @staticmethod
    def _phase_blocked(
        phase: RulePhase,
        failed_phases: set[RulePhase],
    ) -> bool:
        """Return whether a required phase produced an error."""
        return bool(PHASES[phase].requires_success & failed_phases)

    @staticmethod
    def _validate_registry(rules: tuple[Rule, ...]) -> None:
        """Fail early on invalid, ambiguous, or mistyped rule metadata."""
        seen_codes: set[str] = set()
        for rule in rules:
            if not isinstance(rule.phase, RulePhase) or rule.phase not in PHASES:
                msg = f"Rule {type(rule).__name__} has an unknown phase."
                raise RuleRegistrationError(msg)
            if not isinstance(rule.family, RuleFamily):
                msg = f"Rule {type(rule).__name__} has an invalid family."
                raise RuleRegistrationError(msg)
            expected_family = PHASES[rule.phase].family
            if rule.family is not expected_family:
                msg = (
                    f"Rule {rule.code} uses family {rule.family.value} in the "
                    f"{rule.phase.value} phase; expected {expected_family.value}."
                )
                raise RuleRegistrationError(msg)
            code_pattern = rf"{re.escape(rule.family.value)}\d{{3}}"
            if re.fullmatch(code_pattern, rule.code) is None:
                msg = (
                    f"Rule code {rule.code!r} must be {rule.family.value} plus "
                    "3 digits."
                )
                raise RuleRegistrationError(msg)
            if rule.code in seen_codes:
                msg = f"Duplicate rule code registered: {rule.code}."
                raise RuleRegistrationError(msg)
            seen_codes.add(rule.code)
            if not isinstance(rule.order, int) or isinstance(rule.order, bool):
                msg = f"Rule {rule.code} must define an integer order."
                raise RuleRegistrationError(msg)
            invalid_requirements = [
                requirement
                for requirement in rule.requires
                if not isinstance(requirement, Capability)
            ]
            if invalid_requirements:
                msg = f"Rule {rule.code} has invalid context capabilities."
                raise RuleRegistrationError(msg)

    @staticmethod
    def _validate_findings(rule: Rule, findings: list[Diagnostic]) -> None:
        """Ensure a rule cannot emit diagnostics under another stable code."""
        if any(
            finding.code != rule.code or finding.family is not rule.family
            for finding in findings
        ):
            msg = f"Rule {rule.code} emitted a diagnostic with mismatched metadata."
            raise RuleRegistrationError(msg)
