import ast
from pathlib import Path

_SKIP_DIRS = {".venv", "__pycache__", ".git", "tests", "node_modules", ".raphael"}


def build_repo_map(repo_path: Path) -> str:
    """Build a compact repo map from Python AST. No LLM required."""
    lines = []
    for py_file in sorted(repo_path.rglob("*.py")):
        rel = py_file.relative_to(repo_path)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        defs = _extract_defs(tree)
        if defs:
            lines.append(f"{rel}:")
            lines.extend(f"  {d}" for d in defs)

    return "\n".join(lines)


def _extract_defs(tree: ast.AST) -> list[str]:
    """Extract top-level functions and all class methods."""
    defs = []
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            defs.append(f"class {node.name}:")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in item.args.args]
                    defs.append(f"  def {item.name}({', '.join(args)})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Only include if it's truly top-level (not inside a class)
            # We check by seeing if it appears in any class body
            in_class = any(
                node in getattr(c, 'body', [])
                for c in ast.walk(tree)
                if isinstance(c, ast.ClassDef)
            )
            if not in_class:
                args = [a.arg for a in node.args.args]
                defs.append(f"def {node.name}({', '.join(args)})")

    return defs
