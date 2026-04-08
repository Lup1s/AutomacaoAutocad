import unittest

from checker.core import _validate_config, merge_profile_into_config, merge_profiles_into_config


class TestCoreConfigValidation(unittest.TestCase):
    def test_validate_config_recovers_from_invalid_types(self):
        cfg = {
            "layers": {"required": "TEXTO", "naming_convention": 123},
            "text": {"min_height": "10", "max_height": "1"},
            "drawing": {"check_duplicates": "yes", "check_xrefs": "no"},
            "rules": {
                "severity_overrides": {
                    "DUPLICATE_ENTITIES": "warning",
                    "INVALID": "critical",
                    123: "error",
                }
            },
        }

        out = _validate_config(cfg)

        self.assertEqual(out["layers"]["required"], [])
        self.assertEqual(out["layers"]["naming_convention"], "")

        self.assertEqual(out["text"]["min_height"], 1.0)
        self.assertEqual(out["text"]["max_height"], 10.0)

        self.assertTrue(out["drawing"]["check_duplicates"])
        self.assertFalse(out["drawing"]["check_xrefs"])

        self.assertEqual(
            out["rules"]["severity_overrides"],
            {"DUPLICATE_ENTITIES": "WARNING"},
        )

    def test_merge_profile_into_config_applies_partial_overrides(self):
        base = _validate_config({
            "layers": {
                "required": ["TEXTO", "COTA"],
                "naming_convention": "^[A-Z_]+$",
            },
            "text": {"min_height": 1.5, "max_height": 10.0},
            "drawing": {"check_duplicates": True, "check_xrefs": True},
            "rules": {"severity_overrides": {"DUPLICATE_ENTITIES": "ERROR"}},
        })

        profile = {
            "layers": {"required": ["ELETRICA", "TEXTO"]},
            "drawing": {"check_xrefs": False},
            "rules": {"severity_overrides": {"MISSING_LAYER": "WARNING"}},
        }

        merged = merge_profile_into_config(base, profile)

        self.assertEqual(merged["layers"]["required"], ["ELETRICA", "TEXTO"])
        self.assertEqual(merged["layers"]["naming_convention"], "^[A-Z_]+$")
        self.assertTrue(merged["drawing"]["check_duplicates"])
        self.assertFalse(merged["drawing"]["check_xrefs"])
        self.assertEqual(merged["rules"]["severity_overrides"], {"MISSING_LAYER": "WARNING"})

    def test_merge_profiles_into_config_applies_in_sequence(self):
        base = _validate_config({
            "layers": {
                "required": ["TEXTO", "COTA"],
                "naming_convention": "^[A-Z_]+$",
            },
            "text": {"min_height": 1.5, "max_height": 10.0},
            "drawing": {"check_duplicates": True, "check_xrefs": True},
        })

        merged = merge_profiles_into_config(base, [
            {"layers": {"required": ["ELETRICA", "TEXTO"]}},
            {"drawing": {"check_xrefs": False}},
            {"text": {"min_height": 2.0}},
        ])

        self.assertEqual(merged["layers"]["required"], ["ELETRICA", "TEXTO"])
        self.assertFalse(merged["drawing"]["check_xrefs"])
        self.assertEqual(merged["text"]["min_height"], 2.0)


if __name__ == "__main__":
    unittest.main()
