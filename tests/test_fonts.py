"""Font lookup and fallback. Run: python3 -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from countdown.fonts import FontIndex, norm  # noqa: E402


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()


class Fonts(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.plugin = os.path.join(self.root, "plugin")
        self.system = os.path.join(self.root, "system")
        os.makedirs(self.plugin)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def index(self):
        return FontIndex([self.plugin, self.system])

    def test_norm(self):
        self.assertEqual(norm("DejaVu Sans-Bold"), norm("dejavusans_bold"))

    def test_lookup_ignores_case_spaces_and_dashes(self):
        touch(os.path.join(self.system, "truetype/dejavu/DejaVuSans-Bold.ttf"))
        idx = self.index()
        for name in ("DejaVuSans-Bold", "DejaVuSans-bold", "dejavu sans bold", "DEJAVUSANS_BOLD"):
            self.assertEqual(idx.find(name), "DejaVuSans-Bold", name)

    def test_missing_font_falls_back_to_preferred_bold_sans(self):
        touch(os.path.join(self.system, "X11/Type1/C059-Bold.pfb"))
        touch(os.path.join(self.system, "X11/Type1/NimbusSans-Bold.pfb"))
        touch(os.path.join(self.system, "truetype/zzz/Zany.ttf"))
        path, used = self.index().resolve("DejaVuSans-Bold")
        self.assertEqual(used, "NimbusSans-Bold")
        self.assertTrue(path.endswith("NimbusSans-Bold.pfb"))

    def test_fallback_prefers_any_truetype_when_none_preferred(self):
        touch(os.path.join(self.system, "X11/Type1/C059-Bold.pfb"))
        touch(os.path.join(self.system, "truetype/zzz/Zany.ttf"))
        self.assertEqual(self.index().resolve("Missing")[1], "Zany")

    def test_no_fonts_at_all_means_builtin(self):
        self.assertEqual(self.index().resolve("Missing"), (None, None))

    def test_empty_name_is_builtin_on_purpose(self):
        touch(os.path.join(self.system, "truetype/dejavu/DejaVuSans-Bold.ttf"))
        self.assertEqual(self.index().resolve(""), (None, None))

    def test_bundled_font_wins_over_system_copy(self):
        touch(os.path.join(self.plugin, "DejaVuSans-Bold.ttf"))
        touch(os.path.join(self.system, "truetype/dejavu/DejaVuSans-Bold.ttf"))
        self.assertTrue(self.index().resolve("DejaVuSans-Bold")[0].startswith(self.plugin))

    def test_symlinked_font_files_count_but_linked_dirs_are_not_followed(self):
        real = os.path.join(self.root, "elsewhere", "LiberationSans-Bold.ttf")
        touch(real)
        os.makedirs(self.system)
        os.symlink(real, os.path.join(self.system, "LiberationSans-Bold.ttf"))
        os.symlink(self.system, os.path.join(self.system, "loop"))   # would recurse forever
        self.assertEqual(self.index().find("LiberationSans-Bold"), "LiberationSans-Bold")


if __name__ == "__main__":
    unittest.main()
