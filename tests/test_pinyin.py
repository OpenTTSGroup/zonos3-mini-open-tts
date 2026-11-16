"""Run with python -m unittest discover -s tests after installing project dependencies."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.pinyin import convert_pinyin

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = json.loads((ROOT / "engine/studio/src/fixtures/phonemes.json").read_text(encoding="utf-8"))["phoneme_tokens"]["symbols"]


class PinyinTests(unittest.TestCase):
    def convert(self, value):
        return convert_pinyin(value, enabled=True, language="cmn", symbols=SYMBOLS)

    def test_feature_and_language_gates_leave_text_unchanged(self):
        for enabled, language in [(False, "cmn"), (True, "en_us"), (True, "ja")]:
            self.assertEqual(convert_pinyin("[broken", enabled=enabled, language=language), "[broken")

    def test_separate_brackets_keep_citation_tones(self):
        self.assertEqual(self.convert("[nǐ][hǎo]"), "\ue000ni²¹⁴\ue001\ue000xau̯²¹⁴\ue001")

    def test_shared_brackets_apply_third_tone_sandhi(self):
        self.assertEqual(self.convert("[nǐ hǎo]"), "\ue000ni³⁵xau̯²¹⁴\ue001")
        self.assertEqual(self.convert("[ni3 hao3]"), self.convert("[nǐ hǎo]"))

    def test_long_run_uses_original_tones(self):
        self.assertEqual(self.convert("[ni3 ni3 ni3]"), "\ue000ni³⁵ni³⁵ni²¹⁴\ue001")

    def test_mixed_text_and_existing_ipa_are_preserved(self):
        self.assertEqual(self.convert("你好，[nǐ]！\ue000kuɔ³⁵\ue001"),
                         "你好，\ue000ni²¹⁴\ue001！\ue000kuɔ³⁵\ue001")

    def test_neutral_tone_and_umlaut(self):
        self.assertEqual(self.convert("[ma]"), "\ue000ma\ue001")
        self.assertEqual(self.convert("[nǚ]"), self.convert("[nv3]"))
        self.assertEqual(self.convert("[nǚ]"), self.convert("[nu:3]"))

    def test_invalid_input(self):
        for text in ["[]", "[ ]", "[nǐ", "nǐ]", "[[nǐ]]", "[nǐ,hǎo]", "[nǐ3]", "[xyz]", "[你好]"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.convert(text)

    def test_erhua_spelling_and_independent_er(self):
        self.assertEqual(self.convert("[huār]"), "\ue000xwaɚ̯⁵⁵\ue001")
        self.assertEqual(self.convert("[hua1r]"), self.convert("[huār]"))
        self.assertEqual(self.convert("[huā ér]"), "\ue000xwa⁵⁵ɚ³⁵\ue001")
        self.assertEqual(self.convert("[er2]"), self.convert("[ér]"))
        self.assertEqual(self.convert("[ěr]"), "\ue000ɚ²¹⁴\ue001")

    def test_erhua_changes_finals_not_just_appending_r(self):
        for source, expected in [
            ("[wan2r]", "waɚ̯³⁵"), ("[gai4r]", "kaɚ̯⁵¹"),
            ("[fen4r]", "fɚ⁵¹"), ("[jin4r]", "tɕjɚ⁵¹"),
            ("[qun2r]", "tɕʰɥɚ³⁵"), ("[bang4r]", "pãɚ̯̃⁵¹"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(self.convert(source), "\ue000" + expected + "\ue001")

    def test_erhua_keeps_group_sandhi_boundaries(self):
        self.assertEqual(self.convert("[ni3 na3r]"), "\ue000ni³⁵naɚ̯²¹⁴\ue001")
        self.assertEqual(self.convert("[ni3][na3r]"), "\ue000ni²¹⁴\ue001\ue000naɚ̯²¹⁴\ue001")

    def test_invalid_erhua_suffixes(self):
        for text in ["[r]", "[hua1rr]", "[huā1r]", "[er2r]", "[ng2r]"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.convert(text)

    def test_missing_or_incompatible_phoneme_rows(self):
        for symbols in [None, ["n", "i"]]:
            with self.assertRaises(ValueError):
                convert_pinyin("[nǐ]", enabled=True, language="cmn", symbols=symbols)

    def test_effective_language_uses_environment_default(self):
        from app.config import Settings
        from app.schemas import GenerationOptions
        from app.server import _options
        with patch.dict("os.environ", {"ZONOS3_LANGUAGE": "cmn", "ZONOS3_PINYIN_ENABLED": "true"}):
            settings = Settings()
        self.assertTrue(settings.zonos3_pinyin_enabled)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
        with patch("app.server.normalize_language", side_effect=lambda value: value.lower()):
            for options in [GenerationOptions(), GenerationOptions(language=None)]:
                language = _options(options, request)["language"]
                self.assertEqual(language, "cmn")
                self.assertNotEqual(convert_pinyin("[nǐ]", enabled=True, language=language, symbols=SYMBOLS), "[nǐ]")
            self.assertEqual(_options(GenerationOptions(language="en_us"), request)["language"], "en_us")
            settings.zonos3_language = "en_us"
            self.assertEqual(_options(GenerationOptions(language="cmn"), request)["language"], "cmn")


if __name__ == "__main__":
    unittest.main()
