#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""build - build libmelonds_shim (the headless melonDS 1.1 backend of the emulator harness).

    python3 work/tools/melonds_shim/build.py [--src DIR] [--out DIR] [--fetch] [--jobs N]

1. Checks the melonDS checkout (--src, $MELONDS_SRC, default <repo>/../melonDS) is the pinned release:
   tag 1.1, commit PIN_COMMIT, no modified tracked files. --fetch clones it there first (git clone --depth 1
   --branch 1.1 https://github.com/melonDS-emu/melonDS); without --fetch nothing is downloaded.
2. Builds the core as a static library with CMake (no Qt/SDL frontend, no OpenGL, no JIT, no GDB stub, no LTO)
   into <out>/core. The core needs no library beyond the C++ standard library for this configuration.
3. Compiles melonds_shim.cpp and links it with the core into <out>/libmelonds_shim.dylib (.so elsewhere).

Default --out: <work>/build/melonds (git-ignored). work/tools/melonds.py loads the library from there, or from
$MELONDS_SHIM. Versions and why: work/notes/toolchain.md and work/notes/melonds_backend.md. The shim and this
script are GPLv3 (see LICENSE.md here); melonDS itself is never copied into this repository.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent.parent
REPO = WORK.parent
PIN_URL = "https://github.com/melonDS-emu/melonDS"
PIN_TAG = "1.1"
PIN_COMMIT = "b86390e4428bf38ce4c1ce0e9ca446d6d25955e8"   # tag 1.1 is a lightweight tag: no tag object
CMAKE_OPTIONS = [
    "-DCMAKE_BUILD_TYPE=Release", "-DUSE_VCPKG=OFF", "-DBUILD_QT_SDL=OFF", "-DENABLE_OGLRENDERER=OFF",
    "-DENABLE_GDBSTUB=OFF",
    "-DENABLE_JIT=OFF", "-DENABLE_LTO_RELEASE=OFF", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
    "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",           # CMake 4 refuses the policy level teakra asks for
]
LIB = "libmelonds_shim.dylib" if sys.platform == "darwin" else "libmelonds_shim.so"


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def git(src, *args):
    return subprocess.run(["git", "-C", str(src), *args], check=True, capture_output=True, text=True).stdout.strip()


def check_checkout(src):
    if not (src / "src" / "NDS.h").is_file():
        raise SystemExit(f"{src} is not a melonDS checkout: pass --src, set MELONDS_SRC, or use --fetch")
    head = git(src, "rev-parse", "HEAD")
    if head != PIN_COMMIT:
        raise SystemExit(f"{src} is at {head}, not melonDS {PIN_TAG} ({PIN_COMMIT}): git checkout {PIN_TAG}")
    dirty = git(src, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise SystemExit(f"{src} has modified tracked files; the shim is built against the unmodified release:\n"
                         + dirty)
    return head


def arch_define():
    m = platform.machine().lower()
    return {"arm64": "ARM64", "aarch64": "ARM64", "x86_64": "x86_64", "amd64": "x86_64"}.get(m)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.environ.get("MELONDS_SRC", str(REPO.parent / "melonDS")))
    ap.add_argument("--out", default=str(WORK / "build" / "melonds"))
    ap.add_argument("--fetch", action="store_true", help=f"clone {PIN_URL} at tag {PIN_TAG} into --src if missing")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))
    a = ap.parse_args(argv)
    src, out = Path(a.src).resolve(), Path(a.out).resolve()
    if a.fetch and not src.exists():
        run(["git", "clone", "--depth", "1", "--branch", PIN_TAG, PIN_URL, src])
    commit = check_checkout(src)
    if not shutil.which("cmake"):
        raise SystemExit("cmake not found")
    core = out / "core"
    run(["cmake", "-S", src, "-B", core, *CMAKE_OPTIONS])
    run(["cmake", "--build", core, "--target", "core", "-j", str(a.jobs)])
    libs = [core / "src" / "libcore.a", core / "src" / "teakra" / "src" / "libteakra.a"]
    for lib in libs:
        if not lib.is_file():
            raise SystemExit(f"missing {lib}")
    flags = ["-std=gnu++17", "-O2", "-DNDEBUG", "-fPIC", "-fwrapv", "-fvisibility=hidden", "-Wall",
             "-Wno-invalid-offsetof", "-Wno-missing-braces", "-shared"]
    if arch_define():
        flags.append(f"-DARCHITECTURE_{arch_define()}=1")
    if sys.platform == "darwin":
        flags += ["-mmacosx-version-min=10.15", "-install_name", "@rpath/" + LIB,
                  "-Wl,-exported_symbol,_mds_*"]           # only the C API, not the melonDS/C++ symbols
    run([a.cxx, *flags, f"-I{src / 'src'}", f"-I{core / 'src'}", "-o", out / LIB, HERE / "melonds_shim.cpp",
         *libs, "-lpthread"])
    (out / "BUILD_INFO.txt").write_text(
        f"melonDS {PIN_TAG} {commit} ({PIN_URL})\nsource {src}\ncmake {' '.join(CMAKE_OPTIONS)}\n"
        f"cxx {a.cxx} {' '.join(flags)}\n", encoding="utf-8")
    print(f"built {out / LIB} against melonDS {PIN_TAG} ({commit})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
