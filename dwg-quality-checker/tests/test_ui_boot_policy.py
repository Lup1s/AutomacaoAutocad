import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher_web


class TestUiBootPolicy(unittest.TestCase):
    def test_resolve_mode_cli_priority(self):
        mode, fallback = launcher_web._resolve_mode(["--legacy"], {"mode": "web", "fallback_to_legacy": False})
        self.assertEqual(mode, "legacy")
        self.assertFalse(fallback)

    def test_resolve_mode_env_priority_over_config(self):
        with patch("launcher_web.os.getenv") as getenv_mock:
            def _fake_getenv(key: str, default=None):
                if key == "DWGQC_UI_MODE":
                    return "web"
                if key == "DWGQC_UI_FALLBACK_LEGACY":
                    return "0"
                return default

            getenv_mock.side_effect = _fake_getenv
            mode, fallback = launcher_web._resolve_mode([], {"mode": "legacy", "fallback_to_legacy": True})

        self.assertEqual(mode, "web")
        self.assertFalse(fallback)

    def test_web_failure_falls_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            with patch("launcher_web.start_web_desktop", side_effect=RuntimeError("web crash")) as web_mock:
                with patch("launcher_web._start_legacy") as legacy_mock:
                    launcher_web._start_web_with_fallback(base_dir=base_dir, allow_fallback=True)

            web_mock.assert_called_once()
            legacy_mock.assert_called_once()

    def test_web_failure_without_fallback_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            with patch("launcher_web.start_web_desktop", side_effect=RuntimeError("web crash")):
                with self.assertRaises(RuntimeError):
                    launcher_web._start_web_with_fallback(base_dir=base_dir, allow_fallback=False)


if __name__ == "__main__":
    unittest.main()
