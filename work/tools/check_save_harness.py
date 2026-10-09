#!/usr/bin/env python3
"""Run every portable save-core/harness regression without ROMs or an emulator.

    python3 work/tools/check_save_harness.py
    python3 work/tools/check_save_harness.py --with-images  # pinned Pillow installed

New test_emu_*.py modules are discovered automatically. Native tests are excluded
by exact ID regardless of local ROM availability; stale classification is an
error. Unexpected skips fail so a new dependency cannot silently reduce CI.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
NATIVE_RUNNER_TESTS = TOOLS.parent / "research" / "save_core"
NATIVE_TESTS = {
    "test_emu_reflection.AgainstTheFix.test_resolver_is_the_chinese_roms": "Chinese ROM",
    "test_emu_reflection.AgainstTheFix.test_assembled_fix_changes_one_byte": "Chinese ROM and armips",
    "test_emu_texture_bounds.AgainstTheFix.test_routine_is_the_chinese_roms": "Chinese ROM",
    "test_emu_texture_bounds.AgainstTheFix.test_assembled_fix_is_the_fixed_routine": "Chinese ROM and armips",
}
IMAGE_TESTS = {"test_emu_screenshots.Screenshots.test_screen_diff": "Pillow (--with-images)"}


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def classify(tests, with_images=False):
    """Fail closed if an explicitly classified test disappears or discovery fails."""
    tests = list(tests)
    identifiers = {test.id() for test in tests}
    missing = (NATIVE_TESTS.keys() | IMAGE_TESTS.keys()) - identifiers
    if missing:
        raise ValueError("missing classified tests (rename or import failure): " + ", ".join(sorted(missing)))
    if len(identifiers) != len(tests):
        raise ValueError("duplicate discovered test IDs")
    excluded = dict(NATIVE_TESTS)
    if not with_images:
        excluded.update(IMAGE_TESTS)
    return unittest.TestSuite(test for test in tests if test.id() not in excluded), excluded


def discover():
    loader = unittest.TestLoader()
    modules = sorted({p.stem for p in TOOLS.glob("test_emu_*.py")} | {
        "test_save_core", "test_save_architecture", "test_check_save_harness", "test_check.SharedSaveCore",
    })
    suite = loader.loadTestsFromNames(modules)
    # These validate orchestration/fail-closed reporting using stubs, not native
    # emulation. Keep them in the portable gate as new cases are added.
    sys.path.insert(0, str(NATIVE_RUNNER_TESTS))
    try:
        suite.addTests(loader.loadTestsFromNames(sorted(p.stem for p in NATIVE_RUNNER_TESTS.glob("test_*.py"))))
    finally:
        sys.path.remove(str(NATIVE_RUNNER_TESTS))
    if loader.errors:
        raise ValueError("test discovery failed:\n" + "\n".join(loader.errors))
    return flatten(suite)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-images", action="store_true", help="require Pillow and run image tests too")
    args = parser.parse_args(argv)
    try:
        if args.with_images and importlib.util.find_spec("PIL") is None:
            raise ValueError("--with-images requires the Pillow version pinned in work/tools/requirements-runtime.txt")
        # No build/install: the normal runner's preflight verifies the sealed core.
        from check import Failed, preflight_save_core
        try:
            preflight_save_core()
        except Failed as error:
            raise ValueError(str(error)) from error
        suite, excluded = classify(discover(), args.with_images)
    except ValueError as error:
        parser.error(str(error))
    for name, reason in sorted(excluded.items()):
        print(f"EXCLUDED {name}: {reason}", flush=True)
    print(f"Running {suite.countTestCases()} portable save/harness tests; no ROM or emulator", flush=True)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if result.skipped:
        print("FAIL: unexpected skipped portable tests: " + repr(result.skipped), file=sys.stderr)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
