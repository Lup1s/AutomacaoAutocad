import unittest

import ezdxf

from checker.rules import (
    check_entities_on_layer_zero,
    check_required_layers,
    get_all_rules,
)


class TestRulesSmoke(unittest.TestCase):
    def test_get_all_rules_returns_callables(self):
        rules = get_all_rules()
        self.assertTrue(len(rules) >= 10)
        self.assertTrue(all(callable(rule) for rule in rules))

    def test_check_required_layers_reports_missing_layer(self):
        doc = ezdxf.new("R2018")
        doc.layers.new("EXISTING")

        issues = check_required_layers(
            doc,
            {"layers": {"required": ["EXISTING", "A-WALL"]}},
        )

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule, "REQUIRED_LAYER_MISSING")
        self.assertEqual(issues[0].layer, "A-WALL")

    def test_check_entities_on_layer_zero_finds_entities(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "0"})

        issues = check_entities_on_layer_zero(
            doc,
            {"drawing": {"check_entities_on_layer_0": True}},
        )

        self.assertGreaterEqual(len(issues), 1)
        self.assertEqual(issues[0].rule, "ENTITIES_ON_LAYER_0")


if __name__ == "__main__":
    unittest.main()
