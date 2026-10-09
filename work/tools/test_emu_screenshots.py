"""Image-only harness tests; no emulator or ROM, but explicitly require Pillow.

General unittest discovery reports a skip when Pillow is unavailable. CI uses
check_save_harness.py --with-images, which refuses to skip this dependency.
"""
import importlib.util
import unittest

import emu_harness as E


@unittest.skipUnless(importlib.util.find_spec("PIL"), "image checks require pinned Pillow")
class Screenshots(unittest.TestCase):
    def test_screen_diff(self):
        from PIL import Image
        a = Image.new("RGB", (10, 10), "white")
        b = a.copy()
        self.assertEqual(E.screen_diff(a, b)[0], 0)
        b.putpixel((0, 0), (0, 0, 0))
        self.assertAlmostEqual(E.screen_diff(a, b)[0], 0.01)
        self.assertEqual(E.screen_diff(a, b, box=(5, 5, 10, 10))[0], 0)


if __name__ == "__main__":
    unittest.main()
