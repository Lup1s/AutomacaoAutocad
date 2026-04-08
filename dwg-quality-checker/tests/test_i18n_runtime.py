from __future__ import annotations

import unittest

from checker.i18n import get_active_lang, set_lang


class TestI18nRuntime(unittest.TestCase):
    def tearDown(self) -> None:
        set_lang("pt-BR")

    def test_set_lang_accepts_common_english_aliases(self) -> None:
        for candidate in ("en", "EN", "en-US", "en_us"):
            with self.subTest(candidate=candidate):
                set_lang(candidate)
                self.assertEqual(get_active_lang(), "en")

    def test_set_lang_accepts_common_portuguese_aliases(self) -> None:
        for candidate in ("pt-BR", "PT-BR", "pt_br", "pt"):
            with self.subTest(candidate=candidate):
                set_lang(candidate)
                self.assertEqual(get_active_lang(), "pt-BR")

    def test_set_lang_falls_back_to_portuguese_for_unknown_value(self) -> None:
        set_lang("es")
        self.assertEqual(get_active_lang(), "pt-BR")


if __name__ == "__main__":
    unittest.main()
