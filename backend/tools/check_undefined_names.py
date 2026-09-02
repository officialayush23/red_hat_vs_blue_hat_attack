"""Static undefined-name check for the backend.

Why this exists: a missing `import os` in supabase_results.py raised
NameError only when a GPU eval reached that line, silently costing a full
run's per-case rows. py_compile and ast.parse both pass on that file --
they check syntax, not name resolution. Nothing in this repo checks name
resolution, and pyflakes cannot be installed here (no package registry
access from either shell), so this does the one check that would have
caught it.

Deliberately conservative: it reports a name only when it is loaded in a
scope where nothing in that scope, any enclosing scope, the module, or
builtins ever binds it. Star-imports and any module using them are
skipped rather than guessed at.
"""
import ast
import builtins
import os
import sys
from pathlib import Path

BUILTINS = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__builtins__", "__loader__", "__path__", "WindowsError",
}


def bound_in(node):
    """Every name this scope binds, without descending into nested scopes
    (which have their own)."""
    out = set()

    def walk(n, top=False):
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(child.name)
                continue  # its body is a separate scope
            if isinstance(child, ast.Lambda):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for a in child.names:
                    if a.name == "*":
                        out.add("*")
                    else:
                        out.add((a.asname or a.name).split(".")[0])
            elif isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                out.add(child.id)
            elif isinstance(child, ast.arg):
                out.add(child.arg)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                out.add(child.name)
            elif isinstance(child, ast.Global) or isinstance(child, ast.Nonlocal):
                out.update(child.names)
            elif isinstance(child, (ast.withitem,)):
                pass
            walk(child)

    walk(node, top=True)
    return out


def check(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [(path, exc.lineno or 0, f"SYNTAX: {exc.msg}")]

    all_bound = set()
    star = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            all_bound.add(node.name)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    star = True
                else:
                    all_bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            all_bound.add(node.id)
        elif isinstance(node, ast.arg):
            all_bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            all_bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            all_bound.update(node.names)
        elif isinstance(node, ast.comprehension):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    all_bound.add(t.id)

    if star:
        return []  # a star-import can bind anything; refuse to guess

    known = all_bound | BUILTINS
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in known:
                problems.append((path, node.lineno, node.id))
    return problems


def main():
    roots = [Path(a) for a in sys.argv[1:]] or [Path("backend")]
    # PRUNE DURING THE WALK, not after. backend/red, paddleocr_env and
    # voice_gen_env are full vendored interpreters -- tens of thousands of
    # files. rglob("*.py") + a filter still TRAVERSES them, which took long
    # enough to look like a hang. os.walk lets the directory be dropped
    # before it is descended into.
    SKIP = {"red", "paddleocr_env", "voice_gen_env", "__pycache__",
            "site-packages", "Lib", "node_modules", ".git", "Include",
            "Scripts", "share", "etc"}
    files = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            files.extend(Path(dirpath) / f for f in filenames if f.endswith(".py"))
    found = []
    for f in sorted(files):
        found.extend(check(f))
    if not found:
        print(f"clean: {len(files)} files, no undefined names")
        return 0
    for path, line, name in found:
        print(f"{path}:{line}: {name}")
    print(f"\n{len(found)} in {len(files)} files")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
