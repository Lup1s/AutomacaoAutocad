import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_desktop.auth_runtime import AuthSettings
from web_desktop.bridge import DesktopBridge


class _FakeAuthManagerRefreshOk:
    backend_name = "Supabase"

    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings

    def validate_access_token(self, access_token: str, expected_user_id: str | None = None):
        return None, "Sessão inválida ou expirada."

    def refresh_access_token(self, refresh_token: str):
        return (
            {
                "id": "user-1",
                "name": "Teste",
                "email": "teste@example.com",
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
            None,
        )


class TestWebBridgeAuthAndJobs(unittest.TestCase):
    def test_restore_session_uses_refresh_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "auth_session.json").write_text(
                json.dumps(
                    {
                        "id": "user-1",
                        "name": "Teste",
                        "email": "teste@example.com",
                        "access_token": "expired-access",
                        "refresh_token": "valid-refresh",
                        "expires_in": 10,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            settings = AuthSettings(
                supabase_url="https://example.supabase.co",
                supabase_anon_key="anon-key",
                require_subscription=False,
                subscriptions_table="subscriptions",
                session_validate_interval_sec=180,
                auth_event_log_enabled=False,
            )

            with patch("web_desktop.bridge.load_auth_settings", return_value=settings):
                with patch("web_desktop.bridge.SupabaseAuthManager", _FakeAuthManagerRefreshOk):
                    bridge = DesktopBridge(base_dir=base_dir)

            state = bridge.get_auth_state()
            self.assertTrue(state["authenticated"])
            self.assertEqual((state.get("user") or {}).get("id"), "user-1")

    def test_recover_snapshot_marks_running_job_as_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "recover_jobs_snapshot.json").write_text(
                json.dumps(
                    {
                        "saved_at": "2026-04-09T10:00:00",
                        "items": [
                            {
                                "job_id": "job-abc",
                                "state": "running",
                                "progress": 42,
                                "stage": "Processando",
                                "folder": str(base_dir),
                                "created_at": "2026-04-09T09:59:00",
                                "updated_at": "2026-04-09T10:00:00",
                                "created_ts": 1000,
                                "cancel_requested": False,
                                "pause_requested": False,
                                "processed": 4,
                                "total": 10,
                                "ok": 3,
                                "fail": 1,
                                "eta_seconds": 12,
                                "current_file": "file.dwg",
                                "error": "",
                                "result": None,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            settings = AuthSettings(
                supabase_url="",
                supabase_anon_key="",
                require_subscription=False,
                subscriptions_table="subscriptions",
                session_validate_interval_sec=180,
                auth_event_log_enabled=False,
            )

            with patch("web_desktop.bridge.load_auth_settings", return_value=settings):
                bridge = DesktopBridge(base_dir=base_dir)

            job = bridge._recover_jobs.get("job-abc")  # noqa: SLF001 - teste de estado interno
            self.assertIsNotNone(job)
            self.assertEqual(job["state"], "error")
            self.assertIn("reinicialização", str(job.get("stage", "")).lower())


if __name__ == "__main__":
    unittest.main()
