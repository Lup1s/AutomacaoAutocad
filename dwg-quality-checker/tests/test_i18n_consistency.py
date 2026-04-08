from __future__ import annotations

import re
import string
import unittest
from pathlib import Path

from checker.i18n import TRANSLATIONS
from checker.report import _RULE_EXPLAIN_SLUG


class TestI18nConsistency(unittest.TestCase):
    def _placeholders(self, text: str) -> set[str]:
        names: set[str] = set()
        for _, field_name, _, _ in string.Formatter().parse(text):
            if field_name:
                names.add(field_name)
        return names

    def test_languages_have_same_keys(self) -> None:
        pt = TRANSLATIONS["pt-BR"]
        en = TRANSLATIONS["en"]

        self.assertEqual(set(pt.keys()), set(en.keys()))

    def test_placeholders_match_between_languages(self) -> None:
        pt = TRANSLATIONS["pt-BR"]
        en = TRANSLATIONS["en"]

        for key in pt:
            with self.subTest(key=key):
                self.assertEqual(
                    self._placeholders(pt[key]),
                    self._placeholders(en[key]),
                    msg=f"Placeholder mismatch in key '{key}'",
                )

    def test_template_tr_keys_exist_in_translations(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tpl = (root / "templates" / "report.html").read_text(encoding="utf-8")

        keys = set(re.findall(r"\{\{\s*tr\.([A-Za-z0-9_]+)", tpl))
        self.assertTrue(keys, "No tr.<key> references found in report template")

        pt = TRANSLATIONS["pt-BR"]
        en = TRANSLATIONS["en"]
        for key in sorted(keys):
            with self.subTest(key=key):
                self.assertIn(key, pt)
                self.assertIn(key, en)

    def test_python_i18n_call_keys_exist_in_translations(self) -> None:
        root = Path(__file__).resolve().parents[1]
        files = [
            root / "launcher.py",
            root / "checker" / "report.py",
            root / "checker" / "cli.py",
        ]
        pattern = re.compile(r"_\(\s*['\"]([A-Za-z0-9_]+)['\"]")

        pt = TRANSLATIONS["pt-BR"]
        en = TRANSLATIONS["en"]

        for file_path in files:
            content = file_path.read_text(encoding="utf-8")
            keys = set(pattern.findall(content))
            for key in sorted(keys):
                with self.subTest(file=file_path.name, key=key):
                    self.assertIn(key, pt)
                    self.assertIn(key, en)

    def test_report_explainability_keys_exist_for_all_rules(self) -> None:
        pt = TRANSLATIONS["pt-BR"]
        en = TRANSLATIONS["en"]

        for rule, slug in sorted(_RULE_EXPLAIN_SLUG.items()):
            for field in ("what", "why", "fix"):
                key = f"report_explain_{slug}_{field}"
                with self.subTest(rule=rule, key=key):
                    self.assertIn(key, pt)
                    self.assertIn(key, en)


if __name__ == "__main__":
    unittest.main()
