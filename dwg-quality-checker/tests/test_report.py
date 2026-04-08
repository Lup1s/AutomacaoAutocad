import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from checker.report import _build_audit_summary, _build_issues_view, generate_html_report
from checker.i18n import set_lang
from checker.rules import Issue, Severity


class TestReportExplainability(unittest.TestCase):
    def tearDown(self):
        set_lang("pt-BR")

    def _sample_result(self):
        issues = [
            Issue(
                rule="DUPLICATE_ENTITIES",
                severity=Severity.ERROR,
                message="Entidade duplicada",
                entity_type="LINE",
                layer="0",
                handle="A1",
                location="X:10.00  Y:20.00",
                details="Duplicata do handle #9F",
            ),
            Issue(
                rule="EXTERNAL_FONT",
                severity=Severity.INFO,
                message="Fonte não padrão",
                entity_type="STYLE",
                layer="",
                handle="",
                location="",
                details="Fonte: custom.shx",
            ),
        ]
        return {
            "file": "sample_with_issues.dxf",
            "file_path": "samples/sample_with_issues.dxf",
            "passed": False,
            "errors": 1,
            "warnings": 0,
            "infos": 1,
            "total_issues": 2,
            "issues": issues,
            "geometry": [],
            "geo_bbox": {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100},
        }

    def test_build_issues_view_contains_stage2_fields(self):
        result = self._sample_result()
        issues_view = _build_issues_view(result)

        self.assertEqual(len(issues_view), 2)
        first = issues_view[0]

        for key in (
            "what",
            "where",
            "why",
            "fix",
            "probable_cause",
            "evidence",
            "confidence",
            "priority",
            "impact",
        ):
            self.assertIn(key, first)
            self.assertTrue(first[key])

        self.assertEqual(first["severity"], "ERROR")
        self.assertEqual(first["priority"], "Alta")

    def test_build_audit_summary_contains_stage3_fields(self):
        result = self._sample_result()
        issues_view = _build_issues_view(result)
        audit = _build_audit_summary(result, issues_view)

        for key in (
            "score",
            "recommendation",
            "top_rules",
            "top_layers",
            "action_plan",
            "priority_high",
        ):
            self.assertIn(key, audit)

        self.assertGreaterEqual(audit["score"], 0)
        self.assertLessEqual(audit["score"], 100)
        self.assertEqual(audit["errors"], 1)
        self.assertEqual(audit["infos"], 1)
        self.assertTrue(len(audit["top_rules"]) >= 1)
        self.assertTrue(len(audit["action_plan"]) >= 1)

    def test_probable_cause_is_localized_in_english(self):
        set_lang("en")
        result = self._sample_result()
        issues_view = _build_issues_view(result)

        cause = next(i["probable_cause"] for i in issues_view if i["rule"] == "DUPLICATE_ENTITIES")
        self.assertIn("Duplication", cause)

    def test_audit_summary_labels_are_localized_in_english(self):
        set_lang("en")
        result = self._sample_result()
        issues_view = _build_issues_view(result)
        audit = _build_audit_summary(result, issues_view)

        self.assertEqual(audit["recommendation"], "REJECT for correction")
        self.assertEqual(audit["priority_high"], 1)
        self.assertEqual(audit["priority_medium"], 0)
        self.assertEqual(audit["priority_low"], 1)

    def test_html_report_contains_english_audit_labels(self):
        set_lang("en")
        result = self._sample_result()

        with TemporaryDirectory() as td:
            out = Path(td) / "report.html"
            path = generate_html_report(result, str(out))
            html = Path(path).read_text(encoding="utf-8")

        self.assertIn("Executive Audit", html)
        self.assertIn("Recommendation", html)
        self.assertIn("REJECT for correction", html)
        self.assertIn('<html lang="en">', html)

    def test_html_report_contains_portuguese_audit_labels(self):
        set_lang("pt-BR")
        result = self._sample_result()

        with TemporaryDirectory() as td:
            out = Path(td) / "report_pt.html"
            path = generate_html_report(result, str(out))
            html = Path(path).read_text(encoding="utf-8")

        self.assertIn("Auditoria Executiva", html)
        self.assertIn("Recomendação", html)
        self.assertIn("REPROVAR para correção", html)
        self.assertIn('<html lang="pt-BR">', html)


if __name__ == "__main__":
    unittest.main()
