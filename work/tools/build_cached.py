#!/usr/bin/env python3
"""Cached wrapper around build.py, for agents that rebuild the same tree often.

  python3 work/tools/build_cached.py [--strict] [--allow-dirty] [build.py args...]

Cache key = sha256 over: git tree hashes of the paths the build reads (DEPENDS), the
bytes' identity of the input files (path+size+mtime; --strict hashes their content),
and the build args. A hit prints `cached <rom> <sha256>`; a miss runs build.py with
--work-dir work/build/cache/<key>/ and prints one result line (full log in
build.log there; on failure the last 30 lines). A dirty tree is refused;
--allow-dirty builds into work/build/cache/dirty-<pid>/ and never reuses or writes
the cache. Do not pass --work-dir/--out/--patch: the cache owns the output place.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
ROOT = WORK.parent
CACHE = WORK / 'build' / 'cache'
ROM_NAME = 'origin_hg_v4.0.3_en_wip.nds'
MARKER = 'COMPLETE.json'
# Everything build.py reads that is tracked: code, native payload sources, text, art.
DEPENDS = ['work/tools', 'work/patches', 'work/translate', 'work/graphics', 'work/glossary']
# Ignored (generated or local) trees whose files also feed the build.
IGNORED_INPUT_DIRS = ['work/graphics']
FORBIDDEN = ('--work-dir', '--out', '--patch')


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def git(*args, root=ROOT):
    r = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'git {" ".join(args)} failed: {r.stderr.strip()}')
    return r.stdout


def tree_hashes(root=ROOT, paths=DEPENDS):
    return {p: git('rev-parse', f'HEAD:{p}', root=root).strip() for p in paths}


def dirty_files(root=ROOT, paths=DEPENDS):
    out = git('status', '--porcelain=v1', '--untracked-files=all', '--', *paths, root=root)
    return out.splitlines()


def file_identity(path, strict=False):
    """Cheap identity of an input file or directory (strict: content hash of files)."""
    p = Path(path)
    if not p.exists():
        return ['missing', str(p)]
    st = p.stat()
    if p.is_dir():
        return ['dir', str(p.resolve()), st.st_mtime_ns]
    if strict:
        return ['sha256', sha256_file(p)]
    return ['stat', str(p.resolve()), st.st_size, st.st_mtime_ns]


def ignored_inputs(root=ROOT, dirs=IGNORED_INPUT_DIRS):
    """size+mtime of git-ignored files under the dirs (generated graphics)."""
    out = []
    for d in dirs:
        names = git('ls-files', '--others', '--ignored', '--exclude-standard', '--', d, root=root).splitlines()
        for n in sorted(names):
            try:
                st = (root / n).stat()
            except OSError:
                continue
            out.append([n, st.st_size, st.st_mtime_ns])
    return out


def option_value(args, name, default):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + '='):
            return a.split('=', 1)[1]
    return default


def input_paths(args):
    return [option_value(args, '--rom', str(WORK / 'rom' / 'origin_v4.0.3_cn.nds')),
            option_value(args, '--base', str(WORK / 'rom' / 'Pokemon - HeartGold Version (USA).nds')),
            option_value(args, '--extract', str(WORK / 'extract' / 'v4')),
            option_value(args, '--ws', str(WORK / 'translate' / 'banks'))]


def cache_key(trees, identities, ignored, args):
    """Pure function of its inputs (unit-tested)."""
    blob = json.dumps({'trees': trees, 'inputs': identities, 'ignored': ignored, 'args': list(args)},
                      sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def compute_key(args, strict=False):
    trees = tree_hashes()
    idents = {p: file_identity(p, strict and p.endswith('.nds')) for p in input_paths(args)}
    return cache_key(trees, idents, ignored_inputs(), args)


def check_marker(directory, key):
    """The recorded ROM sha256 if the directory holds a verified build for key, else None."""
    d = Path(directory)
    try:
        marker = json.loads((d / MARKER).read_text())
        rom = d / ROM_NAME
        if marker.get('key') != key or not rom.is_file():
            return None
        if sha256_file(rom) != marker.get('rom_sha256'):
            return None
        return marker['rom_sha256']
    except (OSError, ValueError, KeyError, AttributeError):
        return None


def run_build(args, directory, log_name='build.log'):
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / log_name
    t0 = time.time()
    with open(log, 'w') as f:
        code = subprocess.run([sys.executable, str(TOOLS / 'build.py'), *args, '--work-dir', str(directory)],
                              cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
    return code, log, time.time() - t0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--strict', action='store_true', help='content-hash the input ROMs instead of size+mtime')
    p.add_argument('--allow-dirty', action='store_true', help='build a dirty tree; never uses or fills the cache')
    a, build_args = p.parse_known_args(argv)
    for x in build_args:
        if x.split('=')[0] in FORBIDDEN:
            p.error(f'{x.split("=")[0]} is chosen by the cache; remove it')
    dirty = dirty_files()
    if dirty and not a.allow_dirty:
        print('refusing: tree is dirty for build inputs (commit or use --allow-dirty):\n  ' + '\n  '.join(dirty[:10]),
              file=sys.stderr)
        return 2
    if dirty:
        directory = CACHE / f'dirty-{os.getpid()}'
        code, log, secs = run_build(build_args, directory)
        return report(code, log, directory / ROM_NAME, secs, 'dirty, uncached')
    key = compute_key(build_args, a.strict)
    directory = CACHE / key
    sha = check_marker(directory, key)
    if sha:
        print(f'cached {(directory / ROM_NAME).relative_to(ROOT)} {sha}')
        return 0
    code, log, secs = run_build(build_args, directory)
    rom = directory / ROM_NAME
    if code == 0 and rom.is_file():
        (directory / MARKER).write_text(json.dumps({'key': key, 'rom_sha256': sha256_file(rom),
                                                     'args': build_args, 'git_head': git('rev-parse', 'HEAD').strip()}))
    return report(code, log, rom, secs, f'key {key[:12]}')


def report(code, log, rom, secs, note):
    if code == 0 and rom.is_file():
        print(f'built {rom.relative_to(ROOT)} {sha256_file(rom)} ({secs:.0f}s, {note})')
        return 0
    lines = log.read_text(errors='replace').splitlines()[-30:]
    print(f'FAILED exit {code} ({secs:.0f}s); full log {log}\n' + '\n'.join(lines))
    return 1


if __name__ == '__main__':
    sys.exit(main())
