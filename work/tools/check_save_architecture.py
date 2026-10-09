#!/usr/bin/env python3
"""Guard the Python harness/TypeScript codec boundary using Python syntax trees.

This is a regression guard, not a proof against deliberately disguised codecs.
It checks every emu_*.py and the bridge (including future harness modules). Test
fixtures and independent read-only memcheck/quality/runtime oracles are outside
that production boundary; emulator RAM/script/ROM operations remain permitted.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CODEC_CONSTANTS = {0x41C64E6D, 0x6073, 0x1021, 0x8408}
BINARY_WRITERS = {"pack", "pack_into", "to_bytes", "bytearray"}
CODEC_FUNCTIONS = {"crypt", "encrypt", "decrypt", "crc16", "crc16_ccitt", "prng_stream", "lcrng"}
EDITOR_REEXPORTS = {
    name: f"export * from '../../../save-core/dist/{name}.js';"
    for name in ("save", "pokemon", "inventory", "stats", "save-container", "errors", "trainer", "pokedex")
}
EDITOR_REEXPORTS["transaction"] = (
    "export { applyEditorTransaction, SaveTransactionError } from '../../../save-core/dist/transaction.js';\n"
    "export type { EditorOperation } from '../../../save-core/dist/transaction.js';"
)


def callable_name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""


def violations(source, name):
    """Return stable line-specific findings; strings/comments never count as code."""
    tree = ast.parse(source, filename=name)
    findings = set()

    def flag(node, message):
        findings.add((node.lineno, message))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value in CODEC_CONSTANTS:
            flag(node, "save/Pokemon crypto constant belongs in the TypeScript core")
        if isinstance(node, ast.Call) and callable_name(node.func) in {"crc_hqx", "crc16", "crc16_ccitt"}:
            flag(node, "Python save checksum implementation is forbidden")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "crc_hqx":
                    flag(node, "Python save checksum implementation is forbidden (including aliases)")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.lstrip("_").lower() in CODEC_FUNCTIONS:
            flag(node, "local binary codec functions belong in the TypeScript core")
        # Sensitive binary facades must never regain Python serialization. The
        # rest of Harness legitimately packs event scripts and writes emulator RAM.
        protected = ((isinstance(node, ast.ClassDef) and node.name == "SaveFile")
                     or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and node.name in {"encode_pokemon", "decode_pokemon", "decode_party_pokemon", "patch_pokemon"}))
        if protected:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and callable_name(inner.func) in BINARY_WRITERS:
                    flag(inner, "save/Pokemon facade must delegate binary writes to the TypeScript core")
                if isinstance(inner, ast.Subscript) and isinstance(inner.ctx, (ast.Store, ast.Del)):
                    flag(inner, "save/Pokemon facade must not mutate byte offsets in Python")
    return [f"{name}:{line}: {message}" for line, message in sorted(findings)]


def scan(tools=TOOLS):
    paths = sorted(set(tools.glob("emu_*.py")) | {tools / "save_core.py"})
    return [finding for path in paths for finding in violations(path.read_text(), path.name)]


def editor_violations(source, name):
    """Compatibility modules are intentionally only these explicit core exports."""
    normalized = lambda value: re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", value, flags=re.S))
    if normalized(source) != normalized(EDITOR_REEXPORTS[name]):
        return [f"save-editor/src/core/{name}.ts: compatibility module must only re-export the shared TypeScript core"]
    return []


def scan_editor(directory=TOOLS.parent / "save-editor" / "src" / "core"):
    findings = []
    for name in EDITOR_REEXPORTS:
        path = directory / f"{name}.ts"
        if not path.is_file():
            findings.append(f"save-editor/src/core/{name}.ts: shared-core compatibility module is missing")
        else:
            findings.extend(editor_violations(path.read_text(), name))
        # A stale root-level module can keep old consumers on a second codec even
        # while the new UI correctly imports src/core. Do not leave both graphs.
        if (directory.parent / f"{name}.ts").exists():
            findings.append(f"save-editor/src/{name}.ts: legacy module must be removed; use src/core/{name}.ts")
    return findings


def main():
    findings = scan() + scan_editor()
    if findings:
        print("\n".join(findings))
        return 1
    print("Python harness delegates save/Pokemon codecs to TypeScript: architecture guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
