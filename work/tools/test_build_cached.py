import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import build_cached as bc

TREES = {'work/tools': 'a' * 40, 'work/translate': 'b' * 40}
IDENT = {'rom': ['stat', '/x', 1, 2]}


class KeyTests(unittest.TestCase):
    def key(self, trees=TREES, ident=IDENT, ignored=(), args=('--no-patch',)):
        return bc.cache_key(trees, ident, list(ignored), args)

    def test_stable(self):
        self.assertEqual(self.key(), self.key())

    def test_tree_change(self):
        self.assertNotEqual(self.key(), self.key(trees={**TREES, 'work/tools': 'c' * 40}))

    def test_input_change(self):
        self.assertNotEqual(self.key(), self.key(ident={'rom': ['stat', '/x', 1, 3]}))

    def test_args_change(self):
        self.assertNotEqual(self.key(), self.key(args=('--no-text-speed', '--no-patch')))

    def test_ignored_files_change(self):
        self.assertNotEqual(self.key(), self.key(ignored=[['work/graphics/a.png', 1, 2]]))

    def test_dict_order_irrelevant(self):
        self.assertEqual(self.key(), self.key(trees=dict(reversed(list(TREES.items())))))

    def test_option_value(self):
        self.assertEqual(bc.option_value(['--rom', 'a'], '--rom', 'd'), 'a')
        self.assertEqual(bc.option_value(['--rom=b'], '--rom', 'd'), 'b')
        self.assertEqual(bc.option_value([], '--rom', 'd'), 'd')


class MarkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.d / bc.ROM_NAME).write_bytes(b'rom')

    def mark(self, key='k', sha=None):
        sha = sha or bc.sha256_file(self.d / bc.ROM_NAME)
        (self.d / bc.MARKER).write_text(json.dumps({'key': key, 'rom_sha256': sha}))

    def test_hit(self):
        self.mark()
        self.assertEqual(bc.check_marker(self.d, 'k'), bc.sha256_file(self.d / bc.ROM_NAME))

    def test_wrong_key(self):
        self.mark()
        self.assertIsNone(bc.check_marker(self.d, 'other'))

    def test_rom_changed(self):
        self.mark()
        (self.d / bc.ROM_NAME).write_bytes(b'tampered')
        self.assertIsNone(bc.check_marker(self.d, 'k'))

    def test_missing_or_corrupt(self):
        self.assertIsNone(bc.check_marker(self.d, 'k'))
        (self.d / bc.MARKER).write_text('{nope')
        self.assertIsNone(bc.check_marker(self.d, 'k'))

    def test_file_identity_strict(self):
        f = self.d / bc.ROM_NAME
        self.assertEqual(bc.file_identity(f, True)[0], 'sha256')
        self.assertEqual(bc.file_identity(f)[0], 'stat')
        self.assertEqual(bc.file_identity(self.d / 'nope')[0], 'missing')


class GitTests(unittest.TestCase):
    def test_dirty_and_tree(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            run = lambda *a: subprocess.run(['git', *a], cwd=root, check=True, capture_output=True)
            run('init', '-q')
            run('config', 'user.email', 'a@b')
            run('config', 'user.name', 'n')
            (root / 'work/tools').mkdir(parents=True)
            (root / 'work/tools/x.py').write_text('1')
            run('add', '.')
            run('commit', '-qm', 'x')
            self.assertEqual(bc.dirty_files(root, ['work/tools']), [])
            before = bc.tree_hashes(root, ['work/tools'])
            (root / 'work/tools/y.py').write_text('2')
            self.assertEqual(len(bc.dirty_files(root, ['work/tools'])), 1)
            self.assertEqual(before, bc.tree_hashes(root, ['work/tools']))


if __name__ == '__main__':
    unittest.main()
