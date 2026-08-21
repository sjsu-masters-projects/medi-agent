"""Fail when production Python code contains an empty module or placeholder handler."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "app"


def _body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _is_abstract(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Name)
        and decorator.id == "abstractmethod"
        or isinstance(decorator, ast.Attribute)
        and decorator.attr == "abstractmethod"
        for decorator in node.decorator_list
    )


def _is_not_implemented(error: ast.expr | None) -> bool:
    if isinstance(error, ast.Name):
        return error.id == "NotImplementedError"
    return (
        isinstance(error, ast.Call)
        and isinstance(error.func, ast.Name)
        and error.func.id == "NotImplementedError"
    )


def check_file(path: Path) -> list[str]:
    relative = path.relative_to(ROOT)
    if path.name == "__init__.py":
        return []

    source = path.read_text(encoding="utf-8")
    if not source.strip():
        return [f"{relative}: empty production module"]

    try:
        tree = ast.parse(source, filename=str(relative))
    except SyntaxError as error:
        return [f"{relative}:{error.lineno}: cannot parse production module: {error.msg}"]

    errors: list[str] = []
    if not _body_without_docstring(tree.body):
        errors.append(f"{relative}: production module contains no implementation")

    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and _is_not_implemented(node.exc):
            errors.append(
                f"{relative}:{node.lineno}: NotImplementedError is not allowed in production"
            )
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            body = _body_without_docstring(node.body)
            if len(body) == 1 and isinstance(body[0], ast.Pass | ast.Expr):
                is_ellipsis = (
                    isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and body[0].value.value is Ellipsis
                )
                if (isinstance(body[0], ast.Pass) or is_ellipsis) and not _is_abstract(node):
                    errors.append(f"{relative}:{node.lineno}: {node.name} has no implementation")
    return errors


def main() -> int:
    errors = [error for path in sorted(ROOT.rglob("*.py")) for error in check_file(path)]
    if errors:
        print("Production placeholder check failed:", file=sys.stderr)
        print(*errors, sep="\n", file=sys.stderr)
        return 1
    print("Production placeholder check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
