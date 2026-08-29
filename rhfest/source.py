"""Reusable, conservative Python source analysis for RotorHazard rules."""

import ast
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RhapiProvenance:
    """First non-private attribute traversed from RHAPI, if known."""

    namespace: str | None = None


ROOT_RHAPI = RhapiProvenance()
type ProvenanceMap = dict[str, RhapiProvenance]
type PrivateAccessCallback = Callable[[ast.Attribute, RhapiProvenance], None]


def get_rhapi_provenance(
    node: ast.AST,
    derived: ProvenanceMap,
) -> RhapiProvenance | None:
    """Return provenance for a simple RHAPI-derived name/attribute chain."""
    if isinstance(node, ast.Name):
        return derived.get(node.id)
    if isinstance(node, ast.Attribute):
        provenance = get_rhapi_provenance(node.value, derived)
        if (
            provenance is not None
            and provenance.namespace is None
            and not node.attr.startswith("_")
        ):
            return RhapiProvenance(node.attr)
        return provenance
    return None


def bind_target(
    target: ast.AST,
    derived: ProvenanceMap,
    *,
    provenance: RhapiProvenance | None,
) -> None:
    """Bind a simple name alias or invalidate names in a complex target."""
    if isinstance(target, ast.Name):
        if provenance is not None:
            derived[target.id] = provenance
        else:
            derived.pop(target.id, None)
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            bind_target(item, derived, provenance=None)


def invalidate_pattern(pattern: ast.pattern, derived: ProvenanceMap) -> None:
    """Invalidate names captured by a structural pattern."""
    for node in ast.walk(pattern):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
            derived.pop(node.name, None)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            derived.pop(node.rest, None)


def common_provenance(*states: ProvenanceMap) -> ProvenanceMap:
    """Return bindings proven as RHAPI-derived on every supplied path."""
    common_names = set.intersection(*(set(state) for state in states))
    merged: ProvenanceMap = {}
    for name in common_names:
        provenances = {state[name] for state in states}
        merged[name] = provenances.pop() if len(provenances) == 1 else ROOT_RHAPI
    return merged


class RhapiProvenanceAnalyzer:
    """Find private access on locally established RHAPI-derived expressions."""

    def __init__(self, on_private_access: PrivateAccessCallback) -> None:
        """Configure a callback for each offending attribute access."""
        self._on_private_access = on_private_access

    def analyze(self, tree: ast.Module) -> None:
        """Analyze a module in source order with scope-local provenance."""
        self._visit_block(tree.body, {})

    def _visit_block(self, statements: list[ast.stmt], derived: ProvenanceMap) -> None:
        """Analyze statements sequentially, updating proven local aliases."""
        for statement in statements:
            self._visit_statement(statement, derived)

    def _visit_statement(self, statement: ast.stmt, derived: ProvenanceMap) -> None:
        """Analyze one statement and apply its straightforward bindings."""
        if self._visit_definition(statement, derived):
            return
        if self._visit_assignment(statement, derived):
            return
        if self._visit_control_flow(statement, derived):
            return
        self._visit_binding_or_expression(statement, derived)

    def _visit_definition(
        self,
        statement: ast.stmt,
        derived: ProvenanceMap,
    ) -> bool:
        """Analyze a function or class definition when applicable."""
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_function(statement, derived)
            return True
        if isinstance(statement, ast.ClassDef):
            self._visit_class(statement, derived)
            return True
        return False

    def _visit_assignment(
        self,
        statement: ast.stmt,
        derived: ProvenanceMap,
    ) -> bool:
        """Analyze assignment expressions and update simple aliases."""
        if isinstance(statement, ast.Assign):
            self._scan(statement.value, derived)
            provenance = get_rhapi_provenance(statement.value, derived)
            for target in statement.targets:
                bind_target(target, derived, provenance=provenance)
            return True
        if isinstance(statement, ast.AnnAssign):
            if statement.value is not None:
                self._scan(statement.value, derived)
            bind_target(
                statement.target,
                derived,
                provenance=(
                    get_rhapi_provenance(statement.value, derived)
                    if statement.value is not None
                    else None
                ),
            )
            return True
        if isinstance(statement, ast.AugAssign):
            self._scan(statement.target, derived)
            self._scan(statement.value, derived)
            bind_target(statement.target, derived, provenance=None)
            return True
        return False

    def _visit_control_flow(
        self,
        statement: ast.stmt,
        derived: ProvenanceMap,
    ) -> bool:
        """Analyze compound statements with conservative state merging."""
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._visit_loop(statement, derived)
            return True
        if isinstance(statement, ast.While):
            self._visit_while(statement, derived)
            return True
        if isinstance(statement, ast.If):
            self._visit_if(statement, derived)
            return True
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            self._visit_with(statement, derived)
            return True
        if isinstance(statement, (ast.Try, ast.TryStar, ast.Match)):
            if isinstance(statement, ast.Match):
                self._visit_match(statement, derived)
            else:
                self._visit_try(statement, derived)
            return True
        return False

    def _visit_binding_or_expression(
        self,
        statement: ast.stmt,
        derived: ProvenanceMap,
    ) -> None:
        """Handle imports, deletion, declarations, and simple expressions."""
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            self._invalidate_imports(statement, derived)
        elif isinstance(statement, ast.Delete):
            for target in statement.targets:
                bind_target(target, derived, provenance=None)
        elif isinstance(statement, (ast.Global, ast.Nonlocal)):
            for name in statement.names:
                derived.pop(name, None)
        else:
            self._scan(statement, derived)

    def _visit_function(
        self,
        statement: ast.FunctionDef | ast.AsyncFunctionDef,
        outer_derived: ProvenanceMap,
    ) -> None:
        """Analyze defaults outside and a callback body in a fresh local scope."""
        for expression in (
            *statement.decorator_list,
            *statement.args.defaults,
            *(item for item in statement.args.kw_defaults if item is not None),
        ):
            self._scan(expression, outer_derived)

        parameters = (
            *statement.args.posonlyargs,
            *statement.args.args,
            *statement.args.kwonlyargs,
        )
        function_derived = {
            item.arg: ROOT_RHAPI for item in parameters if item.arg == "rhapi"
        }
        if statement.args.vararg is not None and statement.args.vararg.arg == "rhapi":
            function_derived["rhapi"] = ROOT_RHAPI
        if statement.args.kwarg is not None and statement.args.kwarg.arg == "rhapi":
            function_derived["rhapi"] = ROOT_RHAPI
        self._visit_block(statement.body, function_derived)
        outer_derived.pop(statement.name, None)

    def _visit_class(self, statement: ast.ClassDef, derived: ProvenanceMap) -> None:
        """Analyze class expressions and methods without inheriting aliases."""
        for expression in (*statement.decorator_list, *statement.bases):
            self._scan(expression, derived)
        for keyword in statement.keywords:
            self._scan(keyword.value, derived)
        self._visit_block(statement.body, {})
        derived.pop(statement.name, None)

    def _visit_if(self, statement: ast.If, derived: ProvenanceMap) -> None:
        """Keep aliases after a conditional only when every path proves them."""
        self._scan(statement.test, derived)
        body_derived = dict(derived)
        self._visit_block(statement.body, body_derived)
        else_derived = dict(derived)
        self._visit_block(statement.orelse, else_derived)
        derived.clear()
        derived.update(common_provenance(body_derived, else_derived))

    def _visit_loop(
        self,
        statement: ast.For | ast.AsyncFor,
        derived: ProvenanceMap,
    ) -> None:
        """Analyze a loop while accounting for its possible zero iterations."""
        self._scan(statement.iter, derived)
        body_derived = dict(derived)
        bind_target(statement.target, body_derived, provenance=None)
        self._visit_block(statement.body, body_derived)
        else_derived = dict(derived)
        self._visit_block(statement.orelse, else_derived)
        merged = common_provenance(derived, body_derived, else_derived)
        derived.clear()
        derived.update(merged)

    def _visit_while(self, statement: ast.While, derived: ProvenanceMap) -> None:
        """Analyze a while loop without assuming that its body executes."""
        self._scan(statement.test, derived)
        body_derived = dict(derived)
        self._visit_block(statement.body, body_derived)
        else_derived = dict(derived)
        self._visit_block(statement.orelse, else_derived)
        merged = common_provenance(derived, body_derived, else_derived)
        derived.clear()
        derived.update(merged)

    def _visit_with(
        self,
        statement: ast.With | ast.AsyncWith,
        derived: ProvenanceMap,
    ) -> None:
        """Treat context-manager outputs as unrelated values."""
        for item in statement.items:
            self._scan(item.context_expr, derived)
            if item.optional_vars is not None:
                bind_target(item.optional_vars, derived, provenance=None)
        self._visit_block(statement.body, derived)

    def _visit_try(
        self,
        statement: ast.Try | ast.TryStar,
        derived: ProvenanceMap,
    ) -> None:
        """Retain only aliases proven by every completing try/except path."""
        before = dict(derived)
        body_derived = dict(before)
        self._visit_block(statement.body, body_derived)
        self._visit_block(statement.orelse, body_derived)
        paths = [body_derived]
        for handler in statement.handlers:
            handler_derived = dict(before)
            if handler.type is not None:
                self._scan(handler.type, handler_derived)
            if handler.name is not None:
                handler_derived.pop(handler.name, None)
            self._visit_block(handler.body, handler_derived)
            paths.append(handler_derived)
        merged = common_provenance(*paths)
        self._visit_block(statement.finalbody, merged)
        derived.clear()
        derived.update(merged)

    def _visit_match(self, statement: ast.Match, derived: ProvenanceMap) -> None:
        """Retain aliases that survive every match case and no-match path."""
        self._scan(statement.subject, derived)
        paths = [dict(derived)]
        for case in statement.cases:
            case_derived = dict(derived)
            invalidate_pattern(case.pattern, case_derived)
            if case.guard is not None:
                self._scan(case.guard, case_derived)
            self._visit_block(case.body, case_derived)
            paths.append(case_derived)
        merged = common_provenance(*paths)
        derived.clear()
        derived.update(merged)

    def _scan(self, node: ast.AST, derived: ProvenanceMap) -> None:
        """Inspect expressions for private accesses without following calls."""
        _ExpressionScanner(derived, self._on_private_access).visit(node)

    @staticmethod
    def _invalidate_imports(
        statement: ast.Import | ast.ImportFrom,
        derived: ProvenanceMap,
    ) -> None:
        """Treat imported bindings as unrelated values."""
        for item in statement.names:
            bound_name = item.asname or item.name.split(".", maxsplit=1)[0]
            derived.pop(bound_name, None)


class _ExpressionScanner(ast.NodeVisitor):
    """Find offending attributes inside one expression or simple statement."""

    def __init__(
        self,
        derived: ProvenanceMap,
        on_private_access: PrivateAccessCallback,
    ) -> None:
        self._derived = derived
        self._on_private_access = on_private_access

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Report only the named private member on an RHAPI-derived chain."""
        provenance = get_rhapi_provenance(node.value, self._derived)
        if node.attr == "_racecontext" and provenance is not None:
            self._on_private_access(node, provenance)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        """Support a straightforward assignment expression alias."""
        self.visit(node.value)
        bind_target(
            node.target,
            self._derived,
            provenance=get_rhapi_provenance(node.value, self._derived),
        )

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Do not transfer surrounding aliases into a separate lambda scope."""

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Respect target shadowing in a list-comprehension scope."""
        self._visit_comprehension(node.generators, node.elt)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Respect target shadowing in a set-comprehension scope."""
        self._visit_comprehension(node.generators, node.elt)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        """Respect target shadowing in a generator-expression scope."""
        self._visit_comprehension(node.generators, node.elt)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Respect target shadowing in a dict-comprehension scope."""
        self._visit_comprehension(node.generators, node.key, node.value)

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        *results: ast.expr,
    ) -> None:
        """Analyze generator inputs before applying their local bindings."""
        local_derived = dict(self._derived)
        local_scanner = _ExpressionScanner(local_derived, self._on_private_access)
        for generator in generators:
            local_scanner.visit(generator.iter)
            bind_target(generator.target, local_derived, provenance=None)
            for condition in generator.ifs:
                local_scanner.visit(condition)
        for result in results:
            local_scanner.visit(result)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Leave nested function bodies to the scope-aware statement walker."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Leave nested async bodies to the scope-aware statement walker."""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Leave nested class bodies to the scope-aware statement walker."""
