#!/usr/bin/env python3
"""Folder listings in the build-path modules are sorted (reproducible builds, work/notes/toolchain.md).

os.listdir, os.scandir, os.walk, Path.iterdir, Path.glob and Path.rglob return entries in the file system's
order, which differs between machines and file systems. In the modules a build runs, every such listing must
be wrapped in sorted() or only feed something order-free (set, frozenset, any, all, len, sum, a set
comprehension), or be listed in ALLOWED with the reason its order cannot reach an output. Run:
  python3 -m unittest -v work/tools/test_listing_order.py
"""
import ast
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
BUILD_MODULES = ("build", "ws", "msgtool", "gfx", "asmpatch", "fixes", "hardcoded", "text_speed_patch")
LISTING_ATTRS = {"iterdir", "glob", "rglob", "listdir", "scandir", "walk"}
ORDER_FREE = {"sorted", "set", "frozenset", "any", "all", "len", "sum"}
# (module, enclosing function, listing attr): why the order does not matter
ALLOWED = {}


def unsorted_listings(source: str) -> list:
    """(function, line, attr) of every listing call that is not under sorted() or an order-free consumer."""
    tree = ast.parse(source)
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in LISTING_ATTRS):
            continue
        if node.func.attr == "walk" and not (isinstance(node.func.value, ast.Name) and node.func.value.id == "os"):
            continue                                        # ast.walk and the like
        ok, func, up = False, "<module>", parent.get(node)
        while up is not None and not isinstance(up, ast.stmt):
            if isinstance(up, ast.SetComp) or (isinstance(up, ast.Call) and isinstance(up.func, ast.Name)
                                               and up.func.id in ORDER_FREE):
                ok = True
                break
            up = parent.get(up)
        scope = parent.get(node)
        while scope is not None and not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = parent.get(scope)
        if scope is not None:
            func = scope.name
        if not ok:
            found.append((func, node.lineno, node.func.attr))
    return sorted(found, key=lambda f: f[1])


class ListingOrder(unittest.TestCase):
    def test_build_modules_sort_their_listings(self):
        bad = []
        for mod in BUILD_MODULES:
            for func, line, attr in unsorted_listings((TOOLS / f"{mod}.py").read_text(encoding="utf-8")):
                if (mod, func, attr) not in ALLOWED:
                    bad.append(f"work/tools/{mod}.py:{line} in {func}(): .{attr}() without sorted()")
        self.assertEqual(bad, [], "wrap the listing in sorted(), or add it to ALLOWED with the reason")

    def test_the_lint_itself(self):
        src = ("import os\nfrom pathlib import Path\n"
               "def f(p):\n"
               "    a = sorted(p.glob('*'))\n"
               "    b = {x.name for x in p.iterdir()}\n"
               "    c = set(os.listdir(p))\n"
               "    d = any(p.rglob('*.json'))\n"
               "    for x in p.iterdir():\n"
               "        pass\n"
               "    e = next(p.glob('*.bin'))\n"
               "    for root, dirs, files in os.walk(p):\n"
               "        pass\n")
        self.assertEqual(unsorted_listings(src), [("f", 8, "iterdir"), ("f", 10, "glob"), ("f", 11, "walk")])


if __name__ == "__main__":
    unittest.main()
