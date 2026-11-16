import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.ipa import convert_ipa

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = json.loads((ROOT / "engine/studio/src/fixtures/phonemes.json").read_text(encoding="utf-8"))["phoneme_tokens"]["symbols"]


class IPATests(unittest.TestCase):
    def convert(self, text):
        return convert_ipa(text, enabled=True, symbols=SYMBOLS)

    def test_disabled_is_exact_passthrough(self):
        self.assertEqual(convert_ipa("{{invalid", enabled=False), "{{invalid")

    def test_mixed_and_adjacent_groups(self):
        self.assertEqual(self.convert("中文{{kuɔ³⁵}}{{ni²¹⁴}}。"),
                         "中文\ue000kuɔ³⁵\ue001\ue000ni²¹⁴\ue001。")

    def test_unicode_groups_and_plain_braces_are_preserved(self):
        text = "{plain} \ue000{{kuɔ³⁵}}\ue001"
        self.assertEqual(self.convert(text), text)

    def test_bad_groups(self):
        for text in ["{{}}", "{{ }}", "{{ni", "ni}}", "{{ni{{a}}}}", "{{ni\ue000a\ue001}}",
                     "{{ni3}}", "{{/ni/}}", "{{ni hao}}", "{{你好}}", "{{[nǐ]}}"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.convert(text)

    def test_missing_rows_and_unknown_symbols(self):
        for symbols in [None, ["k", "u", "ɔ"]]:
            with self.assertRaises(ValueError):
                convert_ipa("{{kuɔ³⁵}}", enabled=True, symbols=symbols)

    def test_engine_composes_both_features_for_all_languages(self):
        from app.engine import TTSEngine
        engine = TTSEngine.__new__(TTSEngine)
        engine.settings = SimpleNamespace(zonos3_ipa_enabled=True, zonos3_pinyin_enabled=True)
        engine.model = SimpleNamespace(config=SimpleNamespace(text_tokenizer_spec={"phonemes": {"symbols": SYMBOLS}}))
        for language in ["en_us", "ja", "cmn"]:
            self.assertEqual(engine.prepare_text("{{ni²¹⁴}}", language=language), "\ue000ni²¹⁴\ue001")
        self.assertEqual(engine.prepare_text("[nǐ hǎo]，{{kuɔ³⁵}}", language="cmn"),
                         "\ue000ni³⁵xau̯²¹⁴\ue001，\ue000kuɔ³⁵\ue001")
        self.assertEqual(engine.prepare_text("[nǐ]{{kuɔ³⁵}}", language="en_us"),
                         "[nǐ]\ue000kuɔ³⁵\ue001")
        engine.settings.zonos3_pinyin_enabled = False
        self.assertEqual(engine.prepare_text("[nǐ]{{kuɔ³⁵}}", language="cmn"),
                         "[nǐ]\ue000kuɔ³⁵\ue001")


if __name__ == "__main__":
    unittest.main()
