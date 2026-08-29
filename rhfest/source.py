"""Reusable, conservative Python source analysis for RotorHazard rules."""

import ast
from collections.abc import Callable


def is_rhapi_derived(node: ast.AST, derived: set[str]) -> bool:
    """Return whether a simple name/attribute chain has RHAPI provenance."""
    if isinstance(node, ast.Name):
        return node.id in derived
    if isinstance(node, ast.Attribute):
        return is_rhapi_derived(node.value, derived)
    return False


def bind_target(
    target: ast.AST,
    derived: set[str],
    *,
    value_is_derived: bool,
) -> None:
    """Bind a simple name alias or invalidate names in a complex target."""
    if isinstance(target, ast.Name):
        if value_is_derived:
            derived.add(target.id)
        else:
            derived.discard(target.id)
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            bind_target(item, derived, value_is_derived=False)


def invalidate_pattern(pattern: ast.pattern, derived: set[str]) -> None:
    """Invalidate names captured by a structural pattern."""
    for node in ast.walk(pattern):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
            derived.discard(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            derived.discard(node.rest)


class RhapiProvenanceAnalyzer:
    """Find private access on locally established RHAPI-derived expressions."""

    def __init__(self, on_private_access: Callable[[ast.Attribute], None]) -> None:
        """Configure a callback for each offending attribute access."""
        self._on_private_access = on_private_access

    def analyze(self, tree: ast.Module) -> None:
        """Analyze a module in source order with scope-local provenance."""
        self._visit_block(tree.body, set())

    def _visit_block(self, statements: list[ast.stmt], derived: set[str]) -> None:
        """Analyze statements sequentially, updating proven local aliases."""
        for statement in statements:
            self._visit_statement(statement, derived)

    def _visit_statement(self, statement: ast.stmt, derived: set[str]) -> None:
        """Analyze one statement and apply its straightforward bindings."""
        if self._visit_definition(statement, derived):
            return
        if self._visit_assignment(statement, derived):
            return
        if self._visit_control_flow(statement, derived):
            return
        self._visit_binding_or_expression(statement, derived)

    def _visit_definition(self, statement: ast.stmt, derived: set[str]) -> bool:
        """Analyze a function or class definition when applicable."""
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_function(statement, derived)
            return True
        if isinstance(statement, ast.ClassDef):
            self._visit_class(statement, derived)
            return True
        return False

    def _visit_assignment(self, statement: ast.stmt, derived: set[str]) -> bool:
        """Analyze assignment expressions and update simple aliases."""
        if isinstance(statement, ast.Assign):
            self._scan(statement.value, derived)
            is_derived = is_rhapi_derived(statement.value, derived)
            for target in statement.targets:
                bind_target(target, derived, value_is_derived=is_derived)
            return True
        if isinstance(statement, ast.AnnAssign):
            if statement.value is not None:
                self._scan(statement.value, derived)
            bind_target(
                statement.target,
                derived,
                value_is_derived=(
                    statement.value is not None
                    and is_rhapi_derived(statement.value, derived)
                ),
            )
            return True
        if isinstance(statement, ast.AugAssign):
            self._scan(statement.target, derived)
            self._scan(statement.value, derived)
            bind_target(statement.target, derived, value_is_derived=False)
            return True
        return False

    def _visit_control_flow(self, statement: ast.stmt, derived: set[str]) -> bool:
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
        derived: set[str],
    ) -> None:
        """Handle imports, deletion, declarations, and simple expressions."""
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            self._invalidate_imports(statement, derived)
        elif isinstance(statement, ast.Delete):
            for target in statement.targets:
                bind_target(target, derived, value_is_derived=False)
        elif isinstance(statement, (ast.Global, ast.Nonlocal)):
            derived.difference_update(statement.names)
        else:
            self._scan(statement, derived)

    def _visit_function(
        self,
        statement: ast.FunctionDef | ast.AsyncFunctionDef,
        outer_derived: set[str],
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
        function_derived = {item.arg for item in parameters if item.arg == "rhapi"}
        if statement.args.vararg is not None and statement.args.vararg.arg == "rhapi":
            function_derived.add("rhapi")
        if statement.args.kwarg is not None and statement.args.kwarg.arg == "rhapi":
            function_derived.add("rhapi")
        self._visit_block(statement.body, function_derived)
        outer_derived.discard(statement.name)

    def _visit_class(self, statement: ast.ClassDef, derived: set[str]) -> None:
        """Analyze class expressions and methods without inheriting aliases."""
        for expression in (*statement.decorator_list, *statement.bases):
            self._scan(expression, derived)
        for keyword in statement.keywords:
            self._scan(keyword.value, derived)
        self._visit_block(statement.body, set())
        derived.discard(statement.name)

    def _visit_if(self, statement: ast.If, derived: set[str]) -> None:
        """Keep aliases after a conditional only when every path proves them."""
        self._scan(statement.test, derived)
        body_derived = set(derived)
        self._visit_block(statement.body, body_derived)
        else_derived = set(derived)
        self._visit_block(statement.orelse, else_derived)
        derived.clear()
        derived.update(body_derived & else_derived)

    def _visit_loop(
        self,
        statement: ast.For | ast.AsyncFor,
        derived: set[str],
    ) -> None:
        """Analyze a loop while accounting for its possible zero iterations."""
        self._scan(statement.iter, derived)
        body_derived = set(derived)
        bind_target(statement.target, body_derived, value_is_derived=False)
        self._visit_block(statement.body, body_derived)
        else_derived = set(derived)
        self._visit_block(statement.orelse, else_derived)
        derived.intersection_update(body_derived, else_derived)

    def _visit_while(self, statement: ast.While, derived: set[str]) -> None:
        """Analyze a while loop without assuming that its body executes."""
        self._scan(statement.test, derived)
        body_derived = set(derived)
        self._visit_block(statement.body, body_derived)
        else_derived = set(derived)
        self._visit_block(statement.orelse, else_derived)
        derived.intersection_update(body_derived, else_derived)

    def _visit_with(
        self,
        statement: ast.With | ast.AsyncWith,
        derived: set[str],
    ) -> None:
        """Treat context-manager outputs as unrelated values."""
        for item in statement.items:
            self._scan(item.context_expr, derived)
            if item.optional_vars is not None:
                bind_target(item.optional_vars, derived, value_is_derived=False)
        self._visit_block(statement.body, derived)

    def _visit_try(
        self,
        statement: ast.Try | ast.TryStar,
        derived: set[str],
    ) -> None:
        """Retain only aliases proven by every completing try/except path."""
        before = set(derived)
        body_derived = set(before)
        self._visit_block(statement.body, body_derived)
        self._visit_block(statement.orelse, body_derived)
        paths = [body_derived]
        for handler in statement.handlers:
            handler_derived = set(before)
            if handler.type is not None:
                self._scan(handler.type, handler_derived)
            if handler.name is not None:
                handler_derived.discard(handler.name)
            self._visit_block(handler.body, handler_derived)
            paths.append(handler_derived)
        merged = set.intersection(*paths)
        self._visit_block(statement.finalbody, merged)
        derived.clear()
        derived.update(merged)

    def _visit_match(self, statement: ast.Match, derived: set[str]) -> None:
        """Retain aliases that survive every match case and no-match path."""
        self._scan(statement.subject, derived)
        paths = [set(derived)]
        for case in statement.cases:
            case_derived = set(derived)
            invalidate_pattern(case.pattern, case_derived)
            if case.guard is not None:
                self._scan(case.guard, case_derived)
            self._visit_block(case.body, case_derived)
            paths.append(case_derived)
        derived.intersection_update(*paths)

    def _scan(self, node: ast.AST, derived: set[str]) -> None:
        """Inspect expressions for private accesses without following calls."""
        _ExpressionScanner(derived, self._on_private_access).visit(node)

    @staticmethod
    def _invalidate_imports(
        statement: ast.Import | ast.ImportFrom,
        derived: set[str],
    ) -> None:
        """Treat imported bindings as unrelated values."""
        for item in statement.names:
            bound_name = item.asname or item.name.split(".", maxsplit=1)[0]
            derived.discard(bound_name)


class _ExpressionScanner(ast.NodeVisitor):
    """Find offending attributes inside one expression or simple statement."""

    def __init__(
        self,
        derived: set[str],
        on_private_access: Callable[[ast.Attribute], None],
    ) -> None:
        self._derived = derived
        self._on_private_access = on_private_access

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Report only the named private member on an RHAPI-derived chain."""
        if node.attr == "_racecontext" and is_rhapi_derived(
            node.value,
            self._derived,
        ):
            self._on_private_access(node)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        """Support a straightforward assignment expression alias."""
        self.visit(node.value)
        bind_target(
            node.target,
            self._derived,
            value_is_derived=is_rhapi_derived(node.value, self._derived),
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
        local_derived = set(self._derived)
        local_scanner = _ExpressionScanner(local_derived, self._on_private_access)
        for generator in generators:
            local_scanner.visit(generator.iter)
            bind_target(generator.target, local_derived, value_is_derived=False)
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
