import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ezdxf


class TestCLIContract(unittest.TestCase):
    def test_json_mode_reports_missing_file(self):
        root = Path(__file__).resolve().parents[1]
        cmd = [
            sys.executable,
            "main.py",
            "__arquivo_inexistente__.dxf",
            "--json",
            "--quiet",
        ]

        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["file"], "__arquivo_inexistente__.dxf")
        self.assertIn("error", data[0])

    def test_json_mode_batch_partial_failure_and_json_log(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ok_file = tmp_path / "ok.dxf"
            log_file = tmp_path / "run.jsonl"

            doc = ezdxf.new("R2018")
            doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "0"})
            doc.saveas(str(ok_file))

            cmd = [
                sys.executable,
                "main.py",
                str(ok_file),
                "__arquivo_inexistente__.dxf",
                "--json",
                "--quiet",
                "--json-log",
                str(log_file),
            ]

            proc = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 1)
            data = json.loads(proc.stdout)
            self.assertEqual(len(data), 2)

            ok = next(item for item in data if item.get("file") == "ok.dxf")
            missing = next(item for item in data if item.get("file") == "__arquivo_inexistente__.dxf")

            self.assertIn("passed", ok)
            self.assertIn("errors", ok)
            self.assertIn("error", missing)

            self.assertTrue(log_file.exists())
            lines = [ln for ln in log_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2)
            for line in lines:
                event = json.loads(line)
                self.assertIn("ts", event)
                self.assertIn("status", event)
                self.assertIn("file", event)

    def test_summary_json_and_cache_hits_for_duplicate_content(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.dxf"
            file_b = tmp_path / "b.dxf"
            summary_file = tmp_path / "summary.json"

            doc = ezdxf.new("R2018")
            doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "0"})
            doc.saveas(str(file_a))
            file_b.write_bytes(file_a.read_bytes())

            cmd = [
                sys.executable,
                "main.py",
                str(file_a),
                str(file_b),
                "--json",
                "--quiet",
                "--summary-json",
                str(summary_file),
            ]

            proc = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload), 2)
            self.assertTrue(any(item.get("cached") is True for item in payload))

            self.assertTrue(summary_file.exists())
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertEqual(summary["files_total"], 2)
            self.assertEqual(summary["processed"], 2)
            self.assertGreaterEqual(summary["cache_hits"], 1)
            self.assertIn("duration_seconds", summary)


if __name__ == "__main__":
    unittest.main()
