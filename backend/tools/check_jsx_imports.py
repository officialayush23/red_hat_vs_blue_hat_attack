"""Static check for JSX components used but never imported.

Why this exists: `npm run build` cannot run from the device bridge --
node_modules holds Windows binaries and the bridge shell is Linux -- so
frontend edits ship unbuilt. A component or icon referenced without its
import is the JSX equivalent of the NameError that ate a full evaluation
run's per-case rows: it parses fine and explodes at render.

Deliberately narrow. It only flags capitalised JSX element names
(<FooBar />), which in React must resolve to a binding in scope -- a
lowercase <div> is intrinsic and needs nothing. It ignores member
expressions (<Foo.Bar />, where only Foo must be bound) beyond their root,
and namespaced/SVG-ish names containing a dash.
"""
import os
import re
import sys
from pathlib import Path

# import X, { a, b as c }, * as ns  /  const X = ..., function X(), class X
IMPORT_RE = re.compile(r"""import\s+(?P<clause>[^'"]*?)\s*from\s*['"][^'"]+['"]""", re.S)
BARE_DECL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", re.M)
JSX_OPEN_RE = re.compile(r"<\s*([A-Z][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")


def bound_names(src: str) -> set:
    names = set()
    for m in IMPORT_RE.finditer(src):
        clause = m.group("clause")
        # default and namespace bindings sit outside the braces
        outside = re.sub(r"\{[^}]*\}", " ", clause)
        for part in outside.split(","):
            part = part.strip()
            if not part:
                continue
            ns = re.match(r"\*\s+as\s+([A-Za-z_$][\w$]*)", part)
            names.add(ns.group(1) if ns else part)
        for braces in re.findall(r"\{([^}]*)\}", clause):
            for part in braces.split(","):
                part = part.strip()
                if not part:
                    continue
                alias = re.match(r".*\bas\s+([A-Za-z_$][\w$]*)$", part)
                names.add(alias.group(1) if alias else part)
    names.update(BARE_DECL_RE.findall(src))
    # Destructuring, in the three places it binds a capitalised name:
    #   const { A, B } = ...
    #   function Foo({ icon: Icon }) {...}
    #   ({ icon: Icon }) => ...
    # The last two are why this check first reported SidebarMenuButton's
    # and SchematicNode's `icon: Icon` prop as an unimported component --
    # a rename in a function parameter list is still a binding, and both
    # were correct code.
    patterns = [
        r"(?:const|let|var)\s*\{([^}]*)\}\s*=",   # const { ... } =
        r"function\s+[\w$]*\s*\(\s*\{([^}]*)\}",  # function f({ ... })
        r"\(\s*\{([^}]*)\}\s*\)\s*=>",          # ({ ... }) =>
    ]
    for pattern in patterns:
        for braces in re.findall(pattern, src, re.S):
            for part in braces.split(","):
                # `icon: Icon` binds Icon, not icon; `a = 1` binds a.
                part = part.split(":")[-1].split("=")[0].strip()
                if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                    names.add(part)
    return {n for n in names if n}


def check(path: Path):
    src = path.read_text(encoding="utf-8", errors="replace")
    bound = bound_names(src)
    problems = []
    seen = set()
    for m in JSX_OPEN_RE.finditer(src):
        full = m.group(1)
        if "-" in full:
            continue
        root = full.split(".")[0]
        if root in bound or root in seen:
            continue
        seen.add(root)
        line = src.count("\n", 0, m.start()) + 1
        problems.append((path, line, full))
    return problems


def main():
    roots = [Path(a) for a in sys.argv[1:]] or [Path("frontend/src")]
    SKIP = {"node_modules", "dist", "build", ".git", ".vite"}
    files = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            files.extend(Path(dirpath) / f for f in filenames
                         if f.endswith((".jsx", ".tsx")))
    found = []
    for f in sorted(files):
        found.extend(check(f))
    if not found:
        print(f"clean: {len(files)} files, every JSX component resolves to an import")
        return 0
    for path, line, name in found:
        print(f"{path}:{line}: <{name}> is not imported or declared in this file")
    print(f"\n{len(found)} in {len(files)} files")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
