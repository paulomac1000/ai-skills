"""Lexically scoped Python process evidence for AGENTS.md audits."""

from __future__ import annotations

import ast
import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from agents_md_shell_evidence import _add_command_segments

BindingKind = Literal["subprocess-module", "os-module", "subprocess-function", "os-system", "other"]
SUBPROCESS_CALLS = frozenset({"run", "call", "check_call", "check_output", "Popen"})


@dataclass
class _PythonScope:
    """Lexical Python bindings used to prove process execution conservatively."""

    parent: _PythonScope | None = None
    bindings: dict[str, BindingKind] = field(default_factory=dict)
    function_parent: _PythonScope | None = None

    def clone(self) -> _PythonScope:
        return _PythonScope(self.parent, dict(self.bindings), self.function_parent)

    def resolve(self, name: str) -> BindingKind | None:
        if name in self.bindings:
            return self.bindings[name]
        return self.parent.resolve(name) if self.parent is not None else None

    def lexical_parent_for_callable(self) -> _PythonScope:
        """Return the scope inherited by a function or lambda defined here."""
        return self.function_parent or self


def _literal_python_command(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            values.append(element.value)
        return shlex.join(values)
    return None


def _bound_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            names.update(_bound_names(item))
    elif isinstance(target, ast.Starred):
        names.update(_bound_names(target.value))
    return names


def _function_local_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> set[str]:
    names = {argument.arg for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    if node.args.vararg is not None:
        names.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.add(node.args.kwarg.arg)
    body: list[ast.stmt] = list(node.body) if not isinstance(node, ast.Lambda) else []

    class Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            names.add(child.name)

        def visit_AsyncFunctionDef(self, child: ast.AsyncFunctionDef) -> None:
            names.add(child.name)

        def visit_ClassDef(self, child: ast.ClassDef) -> None:
            names.add(child.name)

        def visit_Lambda(self, child: ast.Lambda) -> None:
            return

        def visit_Name(self, child: ast.Name) -> None:
            if isinstance(child.ctx, (ast.Store, ast.Del)):
                names.add(child.id)

        def visit_Import(self, child: ast.Import) -> None:
            for alias in child.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])

        def visit_ImportFrom(self, child: ast.ImportFrom) -> None:
            for alias in child.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)

        def visit_Global(self, child: ast.Global) -> None:
            names.difference_update(child.names)

        def visit_Nonlocal(self, child: ast.Nonlocal) -> None:
            names.difference_update(child.names)

    collector = Collector()
    for statement in body:
        collector.visit(statement)
    return names


class _PythonInvocationVisitor:
    def __init__(self) -> None:
        self.invocations: set[str] = set()

    def process_statements(self, statements: Sequence[ast.stmt], scope: _PythonScope) -> None:
        for statement in statements:
            self.process_statement(statement, scope)

    def process_statement(self, node: ast.stmt, scope: _PythonScope) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                import_kind: BindingKind = "other"
                if alias.name == "subprocess":
                    import_kind = "subprocess-module"
                elif alias.name == "os":
                    import_kind = "os-module"
                scope.bindings[local] = import_kind
            return
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                from_kind: BindingKind = "other"
                if node.module == "subprocess" and alias.name in SUBPROCESS_CALLS:
                    from_kind = "subprocess-function"
                elif node.module == "os" and alias.name == "system":
                    from_kind = "os-system"
                scope.bindings[local] = from_kind
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                self.process_expression(decorator, scope)
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is not None:
                    self.process_expression(default, scope)
            scope.bindings[node.name] = "other"
            child = _PythonScope(scope.lexical_parent_for_callable())
            child.bindings.update({name: "other" for name in _function_local_names(node)})
            self.process_statements(node.body, child)
            return
        if isinstance(node, ast.ClassDef):
            for item in (*node.decorator_list, *node.bases, *node.keywords):
                expression = item.value if isinstance(item, ast.keyword) else item
                self.process_expression(expression, scope)
            scope.bindings[node.name] = "other"
            lexical_parent = scope.lexical_parent_for_callable()
            class_scope = _PythonScope(lexical_parent, function_parent=lexical_parent)
            self.process_statements(node.body, class_scope)
            return
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            value = getattr(node, "value", None)
            if isinstance(value, ast.AST):
                self.process_expression(value, scope)
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            else:
                target = getattr(node, "target", None)
                if isinstance(target, ast.AST):
                    targets.append(target)
            for target in targets:
                for name in _bound_names(target):
                    scope.bindings[name] = "other"
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.process_expression(node.iter, scope)
            branch = scope.clone()
            for name in _bound_names(node.target):
                branch.bindings[name] = "other"
            self.process_statements(node.body, branch)
            self.process_statements(node.orelse, scope.clone())
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            branch = scope.clone()
            for item in node.items:
                self.process_expression(item.context_expr, scope)
                if item.optional_vars is not None:
                    for name in _bound_names(item.optional_vars):
                        branch.bindings[name] = "other"
            self.process_statements(node.body, branch)
            return
        if isinstance(node, ast.If):
            self.process_expression(node.test, scope)
            self.process_statements(node.body, scope.clone())
            self.process_statements(node.orelse, scope.clone())
            return
        if isinstance(node, (ast.Try, ast.TryStar)):
            self.process_statements(node.body, scope.clone())
            for handler in node.handlers:
                branch = scope.clone()
                if handler.name:
                    branch.bindings[handler.name] = "other"
                if handler.type is not None:
                    self.process_expression(handler.type, scope)
                self.process_statements(handler.body, branch)
            self.process_statements(node.orelse, scope.clone())
            self.process_statements(node.finalbody, scope.clone())
            return
        if isinstance(node, ast.While):
            self.process_expression(node.test, scope)
            self.process_statements(node.body, scope.clone())
            self.process_statements(node.orelse, scope.clone())
            return
        if isinstance(node, ast.Match):
            self.process_expression(node.subject, scope)
            for case in node.cases:
                branch = scope.clone()
                if case.guard is not None:
                    self.process_expression(case.guard, branch)
                self.process_statements(case.body, branch)
            return
        if isinstance(node, ast.Expr):
            self.process_expression(node.value, scope)
            return
        if isinstance(node, ast.Return) and node.value is not None:
            self.process_expression(node.value, scope)
            return
        if isinstance(node, ast.Raise):
            if node.exc is not None:
                self.process_expression(node.exc, scope)
            if node.cause is not None:
                self.process_expression(node.cause, scope)
            return
        if isinstance(node, ast.Assert):
            self.process_expression(node.test, scope)
            if node.msg is not None:
                self.process_expression(node.msg, scope)
            return
        if isinstance(node, ast.Delete):
            for target in node.targets:
                for name in _bound_names(target):
                    scope.bindings[name] = "other"

    def process_expression(self, node: ast.AST, scope: _PythonScope) -> None:
        if isinstance(node, ast.Call):
            self._process_call(node, scope)
        elif isinstance(node, ast.Lambda):
            child = _PythonScope(scope.lexical_parent_for_callable())
            child.bindings.update({name: "other" for name in _function_local_names(node)})
            self.process_expression(node.body, child)
            return
        for expression_child in ast.iter_child_nodes(node):
            if isinstance(expression_child, ast.expr) and not isinstance(node, ast.Lambda):
                self.process_expression(expression_child, scope)

    def _process_call(self, node: ast.Call, scope: _PythonScope) -> None:
        accepted = False
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = scope.resolve(node.func.value.id)
            accepted = (owner == "subprocess-module" and node.func.attr in SUBPROCESS_CALLS) or (
                owner == "os-module" and node.func.attr == "system"
            )
        elif isinstance(node.func, ast.Name):
            accepted = scope.resolve(node.func.id) in {"subprocess-function", "os-system"}
        if not accepted:
            return
        argument = (
            node.args[0]
            if node.args
            else next((keyword.value for keyword in node.keywords if keyword.arg in {"args", "command"}), None)
        )
        if argument is None:
            return
        command = _literal_python_command(argument)
        if command is not None:
            _add_command_segments(self.invocations, command)


def _extract_python_invocations(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    visitor = _PythonInvocationVisitor()
    visitor.process_statements(tree.body, _PythonScope())
    return visitor.invocations
