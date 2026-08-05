"""Reachability-aware wrapper for Python process-evidence extraction."""

from __future__ import annotations

import ast

import agents_md_python_evidence_impl as _impl


class _ReachableOnly(ast.NodeTransformer):
    """Prune branches that are statically unreachable from literal conditions."""

    @staticmethod
    def _truthiness(node: ast.AST) -> bool | None:
        try:
            value = ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None
        try:
            return bool(value)
        except (TypeError, ValueError):
            return None

    def _statements(self, statements: list[ast.stmt]) -> list[ast.stmt]:
        transformed: list[ast.stmt] = []
        for statement in statements:
            result = self.visit(statement)
            if result is None:
                continue
            if isinstance(result, list):
                transformed.extend(item for item in result if isinstance(item, ast.stmt))
            elif isinstance(result, ast.stmt):
                transformed.append(result)
        return transformed

    def _suite(self, statements: list[ast.stmt]) -> list[ast.stmt]:
        """Return a syntactically valid suite after recursive pruning."""
        transformed = self._statements(statements)
        return transformed or [ast.Pass()]

    def visit_If(self, node: ast.If) -> ast.AST | list[ast.stmt] | None:
        truthiness = self._truthiness(node.test)
        if truthiness is True:
            return self._suite(node.body)
        if truthiness is False:
            return self._suite(node.orelse)
        had_orelse = bool(node.orelse)
        transformed = self.generic_visit(node)
        assert isinstance(transformed, ast.If)
        transformed.body = transformed.body or [ast.Pass()]
        if had_orelse and not transformed.orelse:
            transformed.orelse = [ast.Pass()]
        return transformed

    def visit_While(self, node: ast.While) -> ast.AST | list[ast.stmt] | None:
        if self._truthiness(node.test) is False:
            return self._suite(node.orelse)
        had_orelse = bool(node.orelse)
        transformed = self.generic_visit(node)
        assert isinstance(transformed, ast.While)
        transformed.body = transformed.body or [ast.Pass()]
        if had_orelse and not transformed.orelse:
            transformed.orelse = [ast.Pass()]
        return transformed

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        truthiness = self._truthiness(node.test)
        if truthiness is True:
            return self.visit(node.body)
        if truthiness is False:
            return self.visit(node.orelse)
        return self.generic_visit(node)


def _extract_python_invocations(text: str) -> set[str]:
    """Extract commands only from branches reachable under literal conditions."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    pruned = _ReachableOnly().visit(tree)
    if not isinstance(pruned, ast.Module):
        return set()
    ast.fix_missing_locations(pruned)
    return _impl._extract_python_invocations(ast.unparse(pruned))
