from __future__ import annotations

import base64
import ctypes
import json
import os
import platform
import subprocess
import threading
import time
import tempfile
import shutil
import glob
import uuid
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any

import ezdxf
import yaml

from checker.core import DXFChecker, merge_profiles_into_config
from checker.recovery import recover_dxf
from checker.report import (
    generate_csv_report,
    generate_excel_report,
    generate_html_report,
    generate_pdf_report,
)
from checker.version import APP_VERSION, APP_NAME, COMPANY
from web_desktop.auth_runtime import AuthSettings, SupabaseAuthManager, load_auth_settings


class DesktopBridge:
    """API exposta para o frontend React via pywebview."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.history_file = self.base_dir / "history.json"
        self.config_file = self.base_dir / "config.yaml"
        self.profiles_file = self.base_dir / "config_profiles.json"
        self.ui_boot_file = self.base_dir / "ui_boot.json"
        self.auth_session_file = self.base_dir / "auth_session.json"
        self.recover_jobs_snapshot_file = self.base_dir / "recover_jobs_snapshot.json"

        self._auth_settings: AuthSettings = load_auth_settings(self.base_dir)
        self._auth_manager: SupabaseAuthManager | None = (
            SupabaseAuthManager(self._auth_settings) if self._auth_settings.is_configured else None
        )
        self._authenticated_user: dict[str, Any] | None = None
        self._auth_status_message = ""
        self._last_session_validation_ts = 0.0
        self._session_validate_interval_sec = int(self._auth_settings.session_validate_interval_sec or 180)
        self._auth_event_log_enabled = bool(self._auth_settings.auth_event_log_enabled)
        self._auth_event_log_file = self.base_dir / "auth_events.jsonl"

        self._watch_lock = threading.Lock()
        self._watching = False
        self._watch_folder = ""
        self._watch_interval = 5
        self._watch_seen_files: dict[str, float] = {}
        self._watch_events: list[dict[str, Any]] = []
        self._watch_stop_event = threading.Event()
        self._watch_thread: threading.Thread | None = None

        self._verify_jobs_lock = threading.Lock()
        self._verify_jobs: dict[str, dict[str, Any]] = {}
        self._recover_jobs_lock = threading.Lock()
        self._recover_jobs: dict[str, dict[str, Any]] = {}

        self._load_recover_jobs_snapshot()

        self._auth_log(
            "bridge_init",
            ok=True,
            auth_enabled=bool(self._auth_manager),
            session_validate_interval_sec=self._session_validate_interval_sec,
        )

        self._restore_persisted_session()

    @staticmethod
    def _public_user(user: dict[str, Any] | None) -> dict[str, str] | None:
        if not user:
            return None
        return {
            "id": str(user.get("id", "")),
            "name": str(user.get("name", "")),
            "email": str(user.get("email", "")),
        }

    def _ensure_authenticated(self) -> None:
        if not self._authenticated_user:
            self._auth_log("auth_required", ok=False, reason="missing_authenticated_user")
            raise PermissionError("Login obrigatório para utilizar o programa.")
        self._validate_or_refresh_session(force=False)

    @staticmethod
    def _mask_email(value: str) -> str:
        email = str(value or "").strip()
        if "@" not in email:
            return ""
        name, domain = email.split("@", 1)
        if not name:
            return f"***@{domain}"
        if len(name) <= 2:
            safe_name = name[0] + "*" * (len(name) - 1)
        else:
            safe_name = name[:2] + "***"
        return f"{safe_name}@{domain}"

    @staticmethod
    def _safe_user_ref(user: dict[str, Any] | None) -> dict[str, str]:
        if not user:
            return {}
        user_id = str(user.get("id", "")).strip()
        email = str(user.get("email", "")).strip()
        return {
            "user_id": user_id[:8] if user_id else "",
            "email_masked": DesktopBridge._mask_email(email),
        }

    @staticmethod
    def _sanitize_auth_meta(meta: dict[str, Any]) -> dict[str, Any]:
        sensitive_tokens = {"token", "password", "secret", "key", "authorization", "cookie"}
        cleaned: dict[str, Any] = {}
        for key, value in (meta or {}).items():
            k = str(key)
            kl = k.lower()
            if any(token in kl for token in sensitive_tokens):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                cleaned[k] = value
            else:
                cleaned[k] = str(value)
        return cleaned

    def _auth_log(self, event: str, ok: bool, **meta: Any) -> None:
        if not self._auth_event_log_enabled:
            return
        try:
            payload: dict[str, Any] = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "event": str(event),
                "ok": bool(ok),
            }
            payload.update(self._sanitize_auth_meta(meta))
            with self._auth_event_log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @staticmethod
    def _protect_windows_dpapi(data: bytes) -> bytes:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        if not data:
            return b""

        buffer = ctypes.create_string_buffer(data, len(data))
        in_blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        ok = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
        if not ok:
            raise RuntimeError("Falha ao criptografar sessão com DPAPI.")

        try:
            return bytes(ctypes.string_at(out_blob.pbData, out_blob.cbData))
        finally:
            kernel32.LocalFree(out_blob.pbData)

    @staticmethod
    def _unprotect_windows_dpapi(data: bytes) -> bytes:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        if not data:
            return b""

        buffer = ctypes.create_string_buffer(data, len(data))
        in_blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
        if not ok:
            raise RuntimeError("Falha ao descriptografar sessão com DPAPI.")

        try:
            return bytes(ctypes.string_at(out_blob.pbData, out_blob.cbData))
        finally:
            kernel32.LocalFree(out_blob.pbData)

    def _encode_session_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if platform.system() == "Windows":
            protected = self._protect_windows_dpapi(raw)
            return {
                "version": 2,
                "scheme": "dpapi",
                "payload": base64.b64encode(protected).decode("ascii"),
            }

        return {
            "version": 1,
            "scheme": "plain-base64",
            "payload": base64.b64encode(raw).decode("ascii"),
        }

    def _decode_session_file(self, raw_text: str) -> dict[str, Any] | None:
        obj = json.loads(raw_text) or {}
        if not isinstance(obj, dict):
            return None

        if "payload" not in obj or "scheme" not in obj:
            # Compatibilidade com sessão legada em texto puro.
            if "id" in obj and "access_token" in obj:
                return obj
            return None

        scheme = str(obj.get("scheme", "")).strip().lower()
        payload_b64 = str(obj.get("payload", "")).strip()
        if not payload_b64:
            return None

        payload_bytes = base64.b64decode(payload_b64.encode("ascii"), validate=False)
        if scheme == "dpapi":
            payload_bytes = self._unprotect_windows_dpapi(payload_bytes)
        elif scheme != "plain-base64":
            return None

        decoded = json.loads(payload_bytes.decode("utf-8")) or {}
        return decoded if isinstance(decoded, dict) else None

    def _validate_or_refresh_session(self, force: bool = False) -> None:
        if not self._authenticated_user:
            self._auth_log("session_validation", ok=False, reason="missing_authenticated_user", forced=bool(force))
            raise PermissionError("Login obrigatório para utilizar o programa.")
        if not self._auth_manager:
            return

        now = time.time()
        if not force and (now - self._last_session_validation_ts) < self._session_validate_interval_sec:
            return

        current = dict(self._authenticated_user)
        token = str(current.get("access_token", "")).strip()
        expected_user_id = str(current.get("id", "")).strip()
        refresh_token = str(current.get("refresh_token", "")).strip()

        if not token or not expected_user_id:
            self._clear_session()
            self._auth_status_message = "Sessão local inválida. Faça login novamente."
            self._auth_log("session_validation", ok=False, reason="invalid_local_session", forced=bool(force))
            raise PermissionError(self._auth_status_message)

        validated_user, validate_err = self._auth_manager.validate_access_token(
            token,
            expected_user_id=expected_user_id,
        )
        if validated_user:
            validated_user["refresh_token"] = refresh_token
            validated_user["expires_in"] = int(current.get("expires_in", 0) or 0)
            self._authenticated_user = validated_user
            self._auth_status_message = ""
            self._last_session_validation_ts = now
            self._save_session(validated_user)
            self._auth_log(
                "session_validate_access_token",
                ok=True,
                forced=bool(force),
                **self._safe_user_ref(validated_user),
            )
            return

        if refresh_token:
            refreshed_user, refresh_err = self._auth_manager.refresh_access_token(refresh_token)
            if refreshed_user and str(refreshed_user.get("id", "")).strip() == expected_user_id:
                self._authenticated_user = refreshed_user
                self._auth_status_message = ""
                self._last_session_validation_ts = now
                self._save_session(refreshed_user)
                self._auth_log(
                    "session_refresh_token",
                    ok=True,
                    forced=bool(force),
                    **self._safe_user_ref(refreshed_user),
                )
                return
            validate_err = refresh_err or validate_err
            self._auth_log(
                "session_refresh_token",
                ok=False,
                forced=bool(force),
                reason=str(validate_err or "refresh_failed")[:200],
                **self._safe_user_ref(current),
            )

        self._clear_session()
        self._auth_status_message = validate_err or "Sua sessão expirou. Faça login novamente para continuar."
        self._auth_log(
            "session_validation",
            ok=False,
            forced=bool(force),
            reason=str(self._auth_status_message)[:200],
            **self._safe_user_ref(current),
        )
        raise PermissionError(self._auth_status_message)

    def _save_session(self, user: dict[str, Any]) -> None:
        payload = {
            "id": str(user.get("id", "")).strip(),
            "name": str(user.get("name", "")).strip(),
            "email": str(user.get("email", "")).strip(),
            "access_token": str(user.get("access_token", "")).strip(),
            "refresh_token": str(user.get("refresh_token", "")).strip(),
            "expires_in": int(user.get("expires_in", 0) or 0),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        if not payload["id"] or not payload["access_token"]:
            return
        try:
            encoded_payload = self._encode_session_file(payload)
            self.auth_session_file.write_text(
                json.dumps(encoded_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._auth_log("session_saved", ok=True, **self._safe_user_ref(payload))
        except Exception:
            self._auth_status_message = "Não foi possível salvar sessão segura neste dispositivo."
            self._auth_log("session_saved", ok=False, reason="write_failed", **self._safe_user_ref(payload))
            pass

    def _clear_session(self) -> None:
        self._authenticated_user = None
        self._last_session_validation_ts = 0.0
        try:
            if self.auth_session_file.exists():
                self.auth_session_file.unlink()
        except Exception:
            pass

    def _restore_persisted_session(self) -> None:
        self._authenticated_user = None
        self._auth_status_message = ""

        if not self._auth_manager:
            self._auth_log("session_restore", ok=False, reason="auth_manager_not_configured")
            return
        if not self.auth_session_file.exists():
            self._auth_log("session_restore", ok=False, reason="session_file_not_found")
            return

        try:
            raw = self._decode_session_file(self.auth_session_file.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                self._clear_session()
                return
        except Exception:
            self._clear_session()
            self._auth_log("session_restore", ok=False, reason="invalid_session_file")
            return

        token = str(raw.get("access_token", "")).strip()
        expected_user_id = str(raw.get("id", "")).strip()
        refresh_token = str(raw.get("refresh_token", "")).strip()
        if not token or not expected_user_id:
            self._clear_session()
            self._auth_log("session_restore", ok=False, reason="missing_token_or_user")
            return

        self._authenticated_user = {
            "id": expected_user_id,
            "name": str(raw.get("name", "")).strip(),
            "email": str(raw.get("email", "")).strip(),
            "access_token": token,
            "refresh_token": refresh_token,
            "expires_in": int(raw.get("expires_in", 0) or 0),
        }

        try:
            self._validate_or_refresh_session(force=True)
            self._auth_log("session_restore", ok=True, **self._safe_user_ref(self._authenticated_user))
        except PermissionError as exc:
            self._auth_status_message = str(exc)
            self._auth_log(
                "session_restore",
                ok=False,
                reason=str(exc)[:200],
                **self._safe_user_ref(self._authenticated_user),
            )

    def get_auth_state(self) -> dict:
        if not self._auth_manager:
            return {
                "enabled": False,
                "backend": "none",
                "authenticated": False,
                "user": None,
                "can_register": False,
                "require_subscription": bool(self._auth_settings.require_subscription),
                "config_error": (
                    "SUPABASE_URL e SUPABASE_ANON_KEY são obrigatórios. "
                    "Preencha auth_config.json na pasta do programa."
                ),
            }

        if self._authenticated_user:
            try:
                self._validate_or_refresh_session(force=False)
            except PermissionError:
                pass

        return {
            "enabled": True,
            "backend": self._auth_manager.backend_name,
            "authenticated": bool(self._authenticated_user),
            "user": self._public_user(self._authenticated_user),
            "can_register": True,
            "require_subscription": bool(self._auth_settings.require_subscription),
            "config_error": self._auth_status_message,
        }

    def auth_login(self, email: str, password: str) -> dict:
        if not self._auth_manager:
            return {
                "ok": False,
                "error": (
                    "SUPABASE_URL e SUPABASE_ANON_KEY são obrigatórios. "
                    "Preencha auth_config.json na pasta do programa."
                ),
            }

        user, err = self._auth_manager.authenticate(email, password)
        if not user:
            self._auth_log("auth_login", ok=False, reason=str(err or "login_failed")[:200], email_masked=self._mask_email(email))
            return {
                "ok": False,
                "error": err or "Falha no login.",
            }

        self._authenticated_user = user
        self._auth_status_message = ""
        self._save_session(user)
        self._auth_log("auth_login", ok=True, **self._safe_user_ref(user))
        return {
            "ok": True,
            "user": self._public_user(user),
        }

    def auth_register(self, name: str, email: str, password: str) -> dict:
        if not self._auth_manager:
            return {
                "ok": False,
                "error": (
                    "SUPABASE_URL e SUPABASE_ANON_KEY são obrigatórios. "
                    "Preencha auth_config.json na pasta do programa."
                ),
            }

        ok, message = self._auth_manager.register(name, email, password)
        if ok:
            self._auth_log("auth_register", ok=True, email_masked=self._mask_email(email))
            return {
                "ok": True,
                "message": message,
            }
        self._auth_log("auth_register", ok=False, reason=str(message)[:200], email_masked=self._mask_email(email))
        return {
            "ok": False,
            "error": message,
        }

    def auth_logout(self) -> bool:
        token = ""
        if self._authenticated_user:
            token = str(self._authenticated_user.get("access_token", "")).strip()

        if self._auth_manager and token:
            try:
                ok, err = self._auth_manager.logout(token)
                self._auth_log("auth_logout_remote", ok=ok, reason="" if ok else str(err or "logout_failed")[:200])
            except Exception:
                self._auth_log("auth_logout_remote", ok=False, reason="logout_exception")
                pass

        self._clear_session()
        self._auth_status_message = ""
        self._auth_log("auth_logout_local", ok=True)
        return True

    def get_bootstrap_state(self) -> dict:
        return {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "company": COMPANY,
            "platform": platform.platform(),
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    def list_history(self) -> list[dict]:
        self._ensure_authenticated()
        if not self.history_file.exists():
            return []
        try:
            data = json.loads(self.history_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data[:200]
        except Exception:
            pass
        return []

    def _append_history_entry(self, result: dict, html_path: str | None) -> None:
        entry = {
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "file": str(Path(str(result.get("file_path", ""))).name),
            "file_path": str(result.get("file_path", "")),
            "passed": bool(result.get("passed", False)),
            "errors": int(result.get("errors", 0)),
            "warnings": int(result.get("warnings", 0)),
            "infos": int(result.get("infos", 0)),
            "total": int(result.get("total_issues", 0)),
            "html_path": html_path or "",
        }
        rows = self.list_history()
        rows.insert(0, entry)
        rows = rows[:500]
        try:
            self.history_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def pick_file(self) -> str:
        """Abre diálogo nativo para escolher arquivo DXF/DWG."""
        self._ensure_authenticated()
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askopenfilename(
                title="Selecionar arquivo DXF/DWG",
                filetypes=[("CAD", "*.dxf *.dwg"), ("Todos", "*.*")],
            )
            root.destroy()
            return selected or ""
        except Exception:
            return ""

    def pick_folder(self) -> str:
        """Abre diálogo nativo para escolher pasta."""
        self._ensure_authenticated()
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Selecionar pasta")
            root.destroy()
            return selected or ""
        except Exception:
            return ""

    def open_path(self, path: str) -> bool:
        self._ensure_authenticated()
        target = Path(path)
        if not target.exists():
            return False

        try:
            if platform.system() == "Windows":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return True
        except Exception:
            return False

    @staticmethod
    def _find_oda() -> str | None:
        """Procura o ODA File Converter em locais padrão no Windows."""
        candidates = [
            r"C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter 25.6.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter 24.12.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter 24.6.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
        ]

        for pattern in [r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe"]:
            matches = sorted(glob.glob(pattern), reverse=True)
            if matches:
                return matches[0]

        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    def _convert_dwg_to_temp_dxf(self, dwg_path: Path) -> tuple[Path | None, list[Path], str | None]:
        """Converte DWG para DXF em pasta temporária (ODA) e retorna caminho DXF."""
        temp_dirs: list[Path] = []
        oda = self._find_oda()
        if not oda:
            return None, temp_dirs, (
                "Suporte a .DWG requer ODA File Converter. "
                "Instale em: https://www.opendesign.com/guestfiles/oda_file_converter"
            )

        in_dir = Path(tempfile.mkdtemp(prefix="dwgqc_in_"))
        out_dir = Path(tempfile.mkdtemp(prefix="dwgqc_out_"))
        temp_dirs.extend([in_dir, out_dir])

        try:
            isolated_dwg = in_dir / dwg_path.name
            shutil.copy2(dwg_path, isolated_dwg)

            # ODAFileConverter <InputDir> <OutputDir> <version> <type> <recurse> <audit>
            file_size_mb = max(1.0, dwg_path.stat().st_size / (1024 * 1024))
            timeout_sec = int(min(1200, max(180, file_size_mb * 8)))
            result = subprocess.run(
                [oda, str(in_dir), str(out_dir), "ACAD2018", "DXF", "0", "1"],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if result.returncode != 0:
                return None, temp_dirs, (
                    f"Conversão DWG→DXF falhou (ODA code {result.returncode}). "
                    f"stderr: {result.stderr.strip()} stdout: {result.stdout.strip()}"
                )

            candidates = list(out_dir.glob(f"{dwg_path.stem}.dxf"))
            if not candidates:
                candidates = list(out_dir.rglob("*.dxf"))
            if not candidates:
                return None, temp_dirs, (
                    "ODA finalizou sem gerar DXF. "
                    f"stdout: {result.stdout.strip()} stderr: {result.stderr.strip()}"
                )

            return candidates[0], temp_dirs, None
        except Exception as exc:
            return None, temp_dirs, str(exc)

    def _convert_dxf_to_dwg(self, dxf_path: Path, output_dwg: Path) -> tuple[bool, str | None]:
        """Converte DXF para DWG via ODA File Converter."""
        oda = self._find_oda()
        if not oda:
            return False, (
                "Conversão DXF→DWG requer ODA File Converter. "
                "Instale em: https://www.opendesign.com/guestfiles/oda_file_converter"
            )

        in_dir = Path(tempfile.mkdtemp(prefix="dwgqc_in_dxf_"))
        out_dir = Path(tempfile.mkdtemp(prefix="dwgqc_out_dwg_"))

        try:
            isolated_dxf = in_dir / dxf_path.name
            shutil.copy2(dxf_path, isolated_dxf)

            file_size_mb = max(1.0, dxf_path.stat().st_size / (1024 * 1024))
            timeout_sec = int(min(1200, max(180, file_size_mb * 8)))
            result = subprocess.run(
                [oda, str(in_dir), str(out_dir), "ACAD2018", "DWG", "0", "1"],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if result.returncode != 0:
                return False, (
                    f"Conversão DXF→DWG falhou (ODA code {result.returncode}). "
                    f"stderr: {result.stderr.strip()} stdout: {result.stdout.strip()}"
                )

            candidates = list(out_dir.glob(f"{dxf_path.stem}.dwg"))
            if not candidates:
                candidates = list(out_dir.rglob("*.dwg"))
            if not candidates:
                return False, (
                    "ODA finalizou sem gerar DWG. "
                    f"stdout: {result.stdout.strip()} stderr: {result.stderr.strip()}"
                )

            output_dwg.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidates[0], output_dwg)
            return True, None
        except Exception as exc:
            return False, str(exc)
        finally:
            try:
                shutil.rmtree(in_dir, ignore_errors=True)
            except Exception:
                pass
            try:
                shutil.rmtree(out_dir, ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _normalize_issue(issue: object) -> dict:
        severity = str(getattr(getattr(issue, "severity", "INFO"), "value", getattr(issue, "severity", "INFO")))
        return {
            "severity": severity,
            "rule": str(getattr(issue, "rule", "")),
            "message": str(getattr(issue, "message", "")),
            "entity_type": str(getattr(issue, "entity_type", "")),
            "layer": str(getattr(issue, "layer", "")),
            "location": str(getattr(issue, "location", "")),
            "handle": str(getattr(issue, "handle", "")),
            "details": str(getattr(issue, "details", "")),
        }

    def _set_verify_job(self, job_id: str, **fields: Any) -> None:
        with self._verify_jobs_lock:
            job = self._verify_jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")

    def _cleanup_old_verify_jobs(self) -> None:
        now = time.time()
        with self._verify_jobs_lock:
            stale: list[str] = []
            for jid, job in self._verify_jobs.items():
                created = float(job.get("created_ts", now))
                if now - created > 60 * 60:
                    stale.append(jid)
            for jid in stale:
                self._verify_jobs.pop(jid, None)

    def start_verify(self, file_path: str) -> dict:
        self._ensure_authenticated()
        self._cleanup_old_verify_jobs()

        job_id = uuid.uuid4().hex
        now_iso = datetime.now().isoformat(timespec="seconds")
        with self._verify_jobs_lock:
            self._verify_jobs[job_id] = {
                "job_id": job_id,
                "state": "running",
                "progress": 1,
                "stage": "Iniciando verificação...",
                "file_path": file_path,
                "created_at": now_iso,
                "updated_at": now_iso,
                "created_ts": time.time(),
                "result": None,
                "error": "",
            }

        def _worker() -> None:
            def _progress(stage: str, progress: int) -> None:
                self._set_verify_job(job_id, stage=stage, progress=max(1, min(100, int(progress))))

            try:
                result = self.verify_file(file_path, progress_cb=_progress)
                self._set_verify_job(
                    job_id,
                    state="done",
                    progress=100,
                    stage="Concluído",
                    result=result,
                    error="",
                )
            except Exception as exc:
                self._set_verify_job(
                    job_id,
                    state="error",
                    progress=100,
                    stage="Falha na verificação",
                    result=None,
                    error=str(exc),
                )

        threading.Thread(target=_worker, daemon=True).start()
        return {"job_id": job_id}

    def get_verify_status(self, job_id: str) -> dict:
        self._ensure_authenticated()
        with self._verify_jobs_lock:
            job = self._verify_jobs.get(job_id)
            if not job:
                return {
                    "found": False,
                    "job_id": job_id,
                    "state": "not_found",
                    "progress": 0,
                    "stage": "Job não encontrado",
                    "result": None,
                    "error": "",
                }

            return {
                "found": True,
                "job_id": job_id,
                "state": str(job.get("state", "running")),
                "progress": int(job.get("progress", 0)),
                "stage": str(job.get("stage", "")),
                "result": job.get("result"),
                "error": str(job.get("error", "")),
                "created_at": str(job.get("created_at", "")),
                "updated_at": str(job.get("updated_at", "")),
            }

    def _set_recover_job(self, job_id: str, **fields: Any) -> None:
        should_persist = any(
            k in fields
            for k in {
                "state",
                "result",
                "error",
                "cancel_requested",
                "pause_requested",
            }
        )
        if not should_persist and "progress" in fields:
            try:
                p = int(fields.get("progress", 0))
                should_persist = p in {1, 100} or (p % 10 == 0)
            except Exception:
                should_persist = False

        with self._recover_jobs_lock:
            job = self._recover_jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")

        if should_persist:
            self._persist_recover_jobs_snapshot()

    def _cleanup_old_recover_jobs(self) -> None:
        now = time.time()
        changed = False
        with self._recover_jobs_lock:
            stale: list[str] = []
            for jid, job in self._recover_jobs.items():
                created = float(job.get("created_ts", now))
                if now - created > 60 * 60:
                    stale.append(jid)
            for jid in stale:
                self._recover_jobs.pop(jid, None)
                changed = True
        if changed:
            self._persist_recover_jobs_snapshot()

    @staticmethod
    def _recover_job_snapshot(job: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": str(job.get("job_id", "")),
            "state": str(job.get("state", "")),
            "progress": int(job.get("progress", 0)),
            "stage": str(job.get("stage", "")),
            "folder": str(job.get("folder", "")),
            "mode": str(job.get("mode", "")),
            "preview_only": bool(job.get("preview_only", False)),
            "max_retries": int(job.get("max_retries", 0)),
            "created_at": str(job.get("created_at", "")),
            "updated_at": str(job.get("updated_at", "")),
            "created_ts": float(job.get("created_ts", 0.0) or 0.0),
            "cancel_requested": bool(job.get("cancel_requested", False)),
            "pause_requested": bool(job.get("pause_requested", False)),
            "processed": int(job.get("processed", 0)),
            "total": int(job.get("total", 0)),
            "ok": int(job.get("ok", 0)),
            "fail": int(job.get("fail", 0)),
            "eta_seconds": job.get("eta_seconds"),
            "current_file": str(job.get("current_file", "")),
            "error": str(job.get("error", "")),
            "result": job.get("result"),
        }

    def _persist_recover_jobs_snapshot(self) -> None:
        try:
            with self._recover_jobs_lock:
                rows = [self._recover_job_snapshot(j) for j in self._recover_jobs.values()]
            rows.sort(key=lambda r: float(r.get("created_ts", 0.0) or 0.0), reverse=True)
            payload = {
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "items": rows[:60],
            }
            self.recover_jobs_snapshot_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_recover_jobs_snapshot(self) -> None:
        if not self.recover_jobs_snapshot_file.exists():
            return
        try:
            data = json.loads(self.recover_jobs_snapshot_file.read_text(encoding="utf-8")) or {}
            items = data.get("items") if isinstance(data, dict) else []
            if not isinstance(items, list):
                return
        except Exception:
            return

        restored: dict[str, dict[str, Any]] = {}
        now_iso = datetime.now().isoformat(timespec="seconds")
        now_ts = time.time()
        for row in items[:60]:
            if not isinstance(row, dict):
                continue
            jid = str(row.get("job_id", "")).strip()
            if not jid:
                continue
            job = dict(row)
            state = str(job.get("state", ""))
            if state in {"running", "paused"}:
                job["state"] = "error"
                job["stage"] = "Interrompido por reinicialização do aplicativo"
                if not str(job.get("error", "")).strip():
                    job["error"] = "Processamento interrompido por reinicialização."
                job["eta_seconds"] = 0
            job["created_at"] = str(job.get("created_at", "") or now_iso)
            job["updated_at"] = str(job.get("updated_at", "") or now_iso)
            job["created_ts"] = float(job.get("created_ts", 0.0) or now_ts)
            restored[jid] = job

        with self._recover_jobs_lock:
            self._recover_jobs = restored

    def list_recover_history(self, limit: int = 20) -> list[dict]:
        self._ensure_authenticated()
        n = max(1, min(100, int(limit)))
        with self._recover_jobs_lock:
            rows = [self._recover_job_snapshot(j) for j in self._recover_jobs.values()]
        rows.sort(key=lambda r: float(r.get("created_ts", 0.0) or 0.0), reverse=True)
        return rows[:n]

    def start_recover_folder(
        self,
        folder_path: str,
        mode: str = "balanced",
        preview_only: bool = False,
        max_retries: int = 1,
    ) -> dict:
        self._ensure_authenticated()
        self._cleanup_old_recover_jobs()
        retry_limit = max(0, min(5, int(max_retries)))

        job_id = uuid.uuid4().hex
        now_iso = datetime.now().isoformat(timespec="seconds")
        with self._recover_jobs_lock:
            self._recover_jobs[job_id] = {
                "job_id": job_id,
                "state": "running",
                "progress": 1,
                "stage": "Iniciando recuperação em lote...",
                "folder": folder_path,
                "mode": mode,
                "preview_only": bool(preview_only),
                "max_retries": retry_limit,
                "created_at": now_iso,
                "updated_at": now_iso,
                "created_ts": time.time(),
                "cancel_requested": False,
                "pause_requested": False,
                "processed": 0,
                "total": 0,
                "ok": 0,
                "fail": 0,
                "eta_seconds": None,
                "current_file": "",
                "result": None,
                "error": "",
            }
            self._persist_recover_jobs_snapshot()

        def _worker() -> None:
            def _progress(
                stage: str,
                progress: int,
                processed: int,
                total: int,
                ok_count: int,
                fail_count: int,
                eta_seconds: int | None,
                current_file: str,
            ) -> None:
                self._set_recover_job(
                    job_id,
                    stage=str(stage),
                    progress=max(1, min(100, int(progress))),
                    processed=max(0, int(processed)),
                    total=max(0, int(total)),
                    ok=max(0, int(ok_count)),
                    fail=max(0, int(fail_count)),
                    eta_seconds=(None if eta_seconds is None else max(0, int(eta_seconds))),
                    current_file=str(current_file or ""),
                )

            def _cancelled() -> bool:
                with self._recover_jobs_lock:
                    job = self._recover_jobs.get(job_id) or {}
                    return bool(job.get("cancel_requested", False))

            def _paused() -> bool:
                with self._recover_jobs_lock:
                    job = self._recover_jobs.get(job_id) or {}
                    return bool(job.get("pause_requested", False))

            try:
                result = self.recover_folder(
                    folder_path,
                    mode=mode,
                    preview_only=preview_only,
                    max_retries=retry_limit,
                    progress_cb=_progress,
                    cancel_cb=_cancelled,
                    pause_cb=_paused,
                )
                self._set_recover_job(
                    job_id,
                    state="cancelled" if bool(result.get("cancelled", False)) else "done",
                    progress=100,
                    stage="Cancelado" if bool(result.get("cancelled", False)) else "Concluído",
                    result=result,
                    error="",
                    eta_seconds=0,
                )
            except Exception as exc:
                self._set_recover_job(
                    job_id,
                    state="error",
                    progress=100,
                    stage="Falha na recuperação em lote",
                    result=None,
                    error=str(exc),
                    eta_seconds=0,
                )

        threading.Thread(target=_worker, daemon=True).start()
        return {"job_id": job_id}

    def cancel_recover(self, job_id: str) -> dict:
        self._ensure_authenticated()
        changed = False
        with self._recover_jobs_lock:
            job = self._recover_jobs.get(job_id)
            if not job:
                return {
                    "found": False,
                    "job_id": job_id,
                    "state": "not_found",
                    "cancel_requested": False,
                }
            if str(job.get("state", "")) not in {"running", "paused"}:
                return {
                    "found": True,
                    "job_id": job_id,
                    "state": str(job.get("state", "")),
                    "cancel_requested": bool(job.get("cancel_requested", False)),
                }
            job["cancel_requested"] = True
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            response = {
                "found": True,
                "job_id": job_id,
                "state": str(job.get("state", "running")),
                "cancel_requested": True,
            }
        if changed:
            self._persist_recover_jobs_snapshot()
        return response

    def pause_recover(self, job_id: str) -> dict:
        self._ensure_authenticated()
        changed = False
        with self._recover_jobs_lock:
            job = self._recover_jobs.get(job_id)
            if not job:
                return {
                    "found": False,
                    "job_id": job_id,
                    "state": "not_found",
                    "pause_requested": False,
                }
            if str(job.get("state", "")) != "running":
                return {
                    "found": True,
                    "job_id": job_id,
                    "state": str(job.get("state", "")),
                    "pause_requested": bool(job.get("pause_requested", False)),
                }
            job["pause_requested"] = True
            job["state"] = "paused"
            job["stage"] = "Pausado pelo usuário"
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            response = {
                "found": True,
                "job_id": job_id,
                "state": "paused",
                "pause_requested": True,
            }
        if changed:
            self._persist_recover_jobs_snapshot()
        return response

    def resume_recover(self, job_id: str) -> dict:
        self._ensure_authenticated()
        changed = False
        with self._recover_jobs_lock:
            job = self._recover_jobs.get(job_id)
            if not job:
                return {
                    "found": False,
                    "job_id": job_id,
                    "state": "not_found",
                    "pause_requested": False,
                }
            if str(job.get("state", "")) not in {"paused", "running"}:
                return {
                    "found": True,
                    "job_id": job_id,
                    "state": str(job.get("state", "")),
                    "pause_requested": bool(job.get("pause_requested", False)),
                }
            job["pause_requested"] = False
            if str(job.get("state", "")) == "paused":
                job["state"] = "running"
                job["stage"] = "Retomando processamento..."
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            response = {
                "found": True,
                "job_id": job_id,
                "state": str(job.get("state", "running")),
                "pause_requested": False,
            }
        if changed:
            self._persist_recover_jobs_snapshot()
        return response

    def get_recover_status(self, job_id: str) -> dict:
        self._ensure_authenticated()
        with self._recover_jobs_lock:
            job = self._recover_jobs.get(job_id)
            if not job:
                return {
                    "found": False,
                    "job_id": job_id,
                    "state": "not_found",
                    "progress": 0,
                    "stage": "Job não encontrado",
                    "processed": 0,
                    "total": 0,
                    "ok": 0,
                    "fail": 0,
                    "eta_seconds": None,
                    "current_file": "",
                    "result": None,
                    "error": "",
                }

            return {
                "found": True,
                "job_id": job_id,
                "state": str(job.get("state", "running")),
                "progress": int(job.get("progress", 0)),
                "stage": str(job.get("stage", "")),
                "processed": int(job.get("processed", 0)),
                "total": int(job.get("total", 0)),
                "ok": int(job.get("ok", 0)),
                "fail": int(job.get("fail", 0)),
                "eta_seconds": job.get("eta_seconds"),
                "current_file": str(job.get("current_file", "")),
                "cancel_requested": bool(job.get("cancel_requested", False)),
                "pause_requested": bool(job.get("pause_requested", False)),
                "max_retries": int(job.get("max_retries", 0)),
                "result": job.get("result"),
                "error": str(job.get("error", "")),
                "created_at": str(job.get("created_at", "")),
                "updated_at": str(job.get("updated_at", "")),
            }

    def verify_file(self, file_path: str, progress_cb: Any = None) -> dict:
        self._ensure_authenticated()
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")

        check_target = path
        temp_dirs_to_cleanup: list[Path] = []
        converted_from_dwg = False

        try:
            if progress_cb:
                progress_cb("Preparando arquivo", 5)

            if path.suffix.lower() == ".dwg":
                if progress_cb:
                    progress_cb("Convertendo DWG para DXF", 15)
                converted_dxf, temp_dirs, conv_err = self._convert_dwg_to_temp_dxf(path)
                temp_dirs_to_cleanup = temp_dirs
                if not converted_dxf:
                    raise ValueError(
                        "Não foi possível verificar o arquivo .DWG porque a conversão para .DXF falhou.\n"
                        f"Detalhes: {conv_err or 'erro desconhecido'}"
                    )
                check_target = converted_dxf
                converted_from_dwg = True

            checker = DXFChecker()
            if progress_cb:
                progress_cb("Lendo e analisando entidades", 25)

            def _rule_progress(rule_name: str, idx: int, total: int) -> None:
                if not progress_cb:
                    return
                if total <= 0:
                    progress_cb(f"Executando regra: {rule_name}", 50)
                    return
                pct = 25 + int((idx / total) * 55)
                progress_cb(f"Executando regra: {rule_name}", pct)

            result = checker.check(str(check_target), progress_cb=_rule_progress)

            if converted_from_dwg:
                result["file"] = path.name
                result["file_path"] = str(path.resolve())

            base = str(path.with_name(path.stem + "_report"))
            if progress_cb:
                progress_cb("Gerando relatório HTML", 82)
            html = generate_html_report(result, base + ".html")
            if progress_cb:
                progress_cb("Gerando relatório CSV", 88)
            csv_ = generate_csv_report(result, base + ".csv")
            pdf = None
            xlsx = None
            try:
                if progress_cb:
                    progress_cb("Gerando relatório PDF", 92)
                pdf = generate_pdf_report(result, base + ".pdf")
            except Exception:
                pass
            try:
                if progress_cb:
                    progress_cb("Gerando relatório XLSX", 96)
                xlsx = generate_excel_report(result, base + ".xlsx")
            except Exception:
                pass

            self._append_history_entry(result, html)

            if progress_cb:
                progress_cb("Finalizando", 99)

            return {
                "file": str(path),
                "passed": bool(result.get("passed", False)),
                "errors": int(result.get("errors", 0)),
                "warnings": int(result.get("warnings", 0)),
                "infos": int(result.get("infos", 0)),
                "total_issues": int(result.get("total_issues", 0)),
                "issues": [self._normalize_issue(i) for i in (result.get("issues", []) or [])],
                "reports": {
                    "html": html,
                    "csv": csv_,
                    "pdf": pdf,
                    "xlsx": xlsx,
                },
                "conversion": {
                    "dwg_to_dxf": converted_from_dwg,
                    "target_path": str(check_target),
                },
            }
        finally:
            for temp_dir in temp_dirs_to_cleanup:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    def _recover_single_file(self, path: Path, mode: str = "balanced", preview_only: bool = False) -> dict:
        ext = path.suffix.lower()
        if ext == ".dxf":
            out = str(path.with_name(path.stem + "_recovered.dxf"))
            info = recover_dxf(str(path), out, mode=mode, preview_only=preview_only)
            info["conversion"] = {
                "dwg_to_dxf": False,
                "dxf_to_dwg": False,
                "source": str(path),
                "recovered_dxf": str(path.with_name(path.stem + "_recovered.dxf")),
                "recovered_dwg": "",
            }
            return info

        if ext != ".dwg":
            raise ValueError("Recuperação suporta apenas .DXF e .DWG")

        temp_dirs_to_cleanup: list[Path] = []
        converted_dxf, temp_dirs, conv_err = self._convert_dwg_to_temp_dxf(path)
        temp_dirs_to_cleanup.extend(temp_dirs)
        if not converted_dxf:
            raise ValueError(
                "Não foi possível recuperar o arquivo .DWG porque a conversão para .DXF falhou.\n"
                f"Detalhes: {conv_err or 'erro desconhecido'}"
            )

        temp_recover_dir = Path(tempfile.mkdtemp(prefix="dwgqc_recover_"))
        temp_dirs_to_cleanup.append(temp_recover_dir)

        try:
            temp_out_dxf = temp_recover_dir / f"{path.stem}_recovered.dxf"
            info = recover_dxf(
                str(converted_dxf),
                str(temp_out_dxf),
                mode=mode,
                preview_only=preview_only,
            )

            if preview_only:
                info["file"] = str(path)
                info["conversion"] = {
                    "dwg_to_dxf": True,
                    "dxf_to_dwg": False,
                    "source": str(path),
                    "recovered_dxf": str(path.with_name(path.stem + "_recovered.dxf")),
                    "recovered_dwg": str(path.with_name(path.stem + "_recovered.dwg")),
                    "warning": "Modo preview não grava saída convertida.",
                }
                return info

            final_out_dxf = path.with_name(f"{path.stem}_recovered.dxf")
            final_out_report = final_out_dxf.with_suffix(".recovery.json")
            final_out_dwg = path.with_name(f"{path.stem}_recovered.dwg")

            shutil.copy2(temp_out_dxf, final_out_dxf)

            temp_report = temp_out_dxf.with_suffix(".recovery.json")
            if temp_report.exists():
                shutil.copy2(temp_report, final_out_report)

            ok_dwg, err_dwg = self._convert_dxf_to_dwg(final_out_dxf, final_out_dwg)

            info["file"] = str(path)
            info["output"] = str(final_out_dwg if ok_dwg else final_out_dxf)
            info["report"] = str(final_out_report) if final_out_report.exists() else ""
            info["conversion"] = {
                "dwg_to_dxf": True,
                "dxf_to_dwg": bool(ok_dwg),
                "source": str(path),
                "recovered_dxf": str(final_out_dxf),
                "recovered_dwg": str(final_out_dwg) if ok_dwg else "",
                "warning": "" if ok_dwg else (err_dwg or "Falha na conversão DXF→DWG"),
            }
            return info
        finally:
            for temp_dir in temp_dirs_to_cleanup:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    def recover_file(self, file_path: str, mode: str = "balanced", preview_only: bool = False) -> dict:
        self._ensure_authenticated()
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        return self._recover_single_file(path=path, mode=mode, preview_only=preview_only)

    def recover_folder(
        self,
        folder_path: str,
        mode: str = "balanced",
        preview_only: bool = False,
        max_retries: int = 1,
        progress_cb: Any = None,
        cancel_cb: Any = None,
        pause_cb: Any = None,
    ) -> dict:
        self._ensure_authenticated()
        root = Path(folder_path)
        if not root.exists() or not root.is_dir():
            raise NotADirectoryError(f"Pasta inválida: {root}")

        files = sorted(
            [
                p
                for p in root.rglob("*")
                if p.is_file() and p.suffix.lower() in {".dxf", ".dwg"}
            ]
        )

        rows: list[dict[str, Any]] = []
        ok = 0
        fail = 0
        cancelled = False
        total = len(files)
        started_ts = time.time()
        retry_limit = max(0, min(5, int(max_retries)))
        by_ext: dict[str, dict[str, Any]] = {
            ".dxf": {"total": 0, "processed": 0, "ok": 0, "fail": 0, "total_seconds": 0.0},
            ".dwg": {"total": 0, "processed": 0, "ok": 0, "fail": 0, "total_seconds": 0.0},
        }
        remaining_by_ext: dict[str, int] = {".dxf": 0, ".dwg": 0}
        for p in files:
            ext = p.suffix.lower()
            if ext not in by_ext:
                by_ext[ext] = {"total": 0, "processed": 0, "ok": 0, "fail": 0, "total_seconds": 0.0}
                remaining_by_ext[ext] = 0
            by_ext[ext]["total"] = int(by_ext[ext].get("total", 0)) + 1
            remaining_by_ext[ext] = int(remaining_by_ext.get(ext, 0)) + 1

        if progress_cb:
            progress_cb(
                "Preparando lote",
                1,
                0,
                total,
                ok,
                fail,
                None,
                "",
            )

        for idx, fp in enumerate(files, start=1):
            if cancel_cb and bool(cancel_cb()):
                cancelled = True
                break

            while pause_cb and bool(pause_cb()):
                if cancel_cb and bool(cancel_cb()):
                    cancelled = True
                    break
                if progress_cb:
                    progress_cb(
                        "Pausado pelo usuário",
                        max(1, min(99, 10 + int(((ok + fail) / max(1, total)) * 85))),
                        ok + fail,
                        total,
                        ok,
                        fail,
                        None,
                        "",
                    )
                time.sleep(0.25)

            if cancelled:
                break

            current_file = str(fp)
            current_ext = fp.suffix.lower()
            attempts = 0
            last_exc: Exception | None = None
            info: dict[str, Any] | None = None
            file_started_ts = time.time()

            for attempts in range(1, retry_limit + 2):
                if cancel_cb and bool(cancel_cb()):
                    cancelled = True
                    break
                while pause_cb and bool(pause_cb()):
                    if cancel_cb and bool(cancel_cb()):
                        cancelled = True
                        break
                    if progress_cb:
                        progress_cb(
                            f"Pausado pelo usuário: {fp.name}",
                            max(1, min(99, 10 + int(((ok + fail) / max(1, total)) * 85))),
                            ok + fail,
                            total,
                            ok,
                            fail,
                            None,
                            current_file,
                        )
                    time.sleep(0.25)
                if cancelled:
                    break
                try:
                    info = self._recover_single_file(path=fp, mode=mode, preview_only=preview_only)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempts <= retry_limit and progress_cb:
                        progress_cb(
                            f"Retentativa {attempts}/{retry_limit} para {fp.name}",
                            max(1, min(99, 10 + int(((ok + fail) / max(1, total)) * 85))),
                            ok + fail,
                            total,
                            ok,
                            fail,
                            None,
                            current_file,
                        )

            if cancelled:
                break

            retries_used = max(0, attempts - 1)
            elapsed_file_sec = max(0.0, time.time() - file_started_ts)
            if current_ext not in by_ext:
                by_ext[current_ext] = {"total": 0, "processed": 0, "ok": 0, "fail": 0, "total_seconds": 0.0}
            by_ext[current_ext]["processed"] = int(by_ext[current_ext].get("processed", 0)) + 1
            by_ext[current_ext]["total_seconds"] = float(by_ext[current_ext].get("total_seconds", 0.0)) + elapsed_file_sec
            remaining_by_ext[current_ext] = max(0, int(remaining_by_ext.get(current_ext, 0)) - 1)

            if info is not None:
                rows.append(
                    {
                        "file": str(fp),
                        "extension": current_ext,
                        "status": "preview" if preview_only else "ok",
                        "output": str(info.get("output", "")),
                        "report": str(info.get("report", "")),
                        "health_score": info.get("health_score", 0),
                        "issues": len(info.get("issues", []) or []),
                        "conversion": info.get("conversion", {}),
                        "attempts": int(attempts),
                        "retries_used": int(retries_used),
                        "elapsed_seconds": round(elapsed_file_sec, 3),
                    }
                )
                ok += 1
                by_ext[current_ext]["ok"] = int(by_ext[current_ext].get("ok", 0)) + 1
            else:
                rows.append(
                    {
                        "file": str(fp),
                        "extension": current_ext,
                        "status": "error",
                        "error": str(last_exc) if last_exc else "Falha desconhecida",
                        "attempts": int(attempts),
                        "retries_used": int(retries_used),
                        "elapsed_seconds": round(elapsed_file_sec, 3),
                    }
                )
                fail += 1
                by_ext[current_ext]["fail"] = int(by_ext[current_ext].get("fail", 0)) + 1

            processed = ok + fail
            progress = 10 + int((processed / max(1, total)) * 85)
            elapsed = max(0.0, time.time() - started_ts)
            eta_seconds: int | None = None
            if processed > 0 and processed < total:
                global_avg = elapsed / processed
                remaining_estimate = 0.0
                for ext_key, rem in remaining_by_ext.items():
                    rem_n = int(rem or 0)
                    if rem_n <= 0:
                        continue
                    ext_stats = by_ext.get(ext_key, {})
                    ext_processed = int(ext_stats.get("processed", 0) or 0)
                    ext_total_seconds = float(ext_stats.get("total_seconds", 0.0) or 0.0)
                    ext_avg = (ext_total_seconds / ext_processed) if ext_processed > 0 else global_avg
                    remaining_estimate += rem_n * ext_avg
                eta_seconds = int(max(0.0, remaining_estimate))

            if progress_cb:
                progress_cb(
                    f"Processando {processed}/{total}: {fp.name} (tentativas: {attempts})",
                    max(1, min(99, progress)),
                    processed,
                    total,
                    ok,
                    fail,
                    eta_seconds,
                    current_file,
                )

        elapsed_total_sec = max(0.0, time.time() - started_ts)
        by_ext_summary: dict[str, dict[str, Any]] = {}
        for ext_key, ext_stats in by_ext.items():
            ext_processed = int(ext_stats.get("processed", 0) or 0)
            ext_total_seconds = float(ext_stats.get("total_seconds", 0.0) or 0.0)
            by_ext_summary[ext_key] = {
                "total": int(ext_stats.get("total", 0) or 0),
                "processed": ext_processed,
                "ok": int(ext_stats.get("ok", 0) or 0),
                "fail": int(ext_stats.get("fail", 0) or 0),
                "avg_seconds": round((ext_total_seconds / ext_processed), 3) if ext_processed > 0 else 0.0,
                "total_seconds": round(ext_total_seconds, 3),
            }

        out_json = root / f"recovery_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        summary = {
            "folder": str(root.resolve()),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "preview_only": bool(preview_only),
            "max_retries": retry_limit,
            "recursive": True,
            "total": total,
            "processed": ok + fail,
            "ok": ok,
            "fail": fail,
            "cancelled": bool(cancelled),
            "elapsed_seconds": round(elapsed_total_sec, 3),
            "avg_seconds_per_file": round((elapsed_total_sec / max(1, ok + fail)), 3) if (ok + fail) > 0 else 0.0,
            "by_extension": by_ext_summary,
            "items": rows,
            "summary_file": str(out_json.resolve()) if not preview_only else "",
        }
        if not preview_only:
            out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        if progress_cb:
            progress_cb(
                "Cancelado" if cancelled else "Finalizando",
                100,
                ok + fail,
                total,
                ok,
                fail,
                0,
                "",
            )

        return summary

    def diagnostics(self) -> dict:
        self._ensure_authenticated()
        return {
            "app_version": APP_VERSION,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cwd": str(Path.cwd()),
            "base_dir": str(self.base_dir),
            "history_exists": self.history_file.exists(),
            "watching": self._watching,
            "watch_folder": self._watch_folder,
            "watch_events": len(self._watch_events),
            "config_file": str(self.config_file),
            "profiles_file": str(self.profiles_file),
        }

    def _read_config(self) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            data = yaml.safe_load(self.config_file.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_config(self, config: dict) -> bool:
        try:
            self.config_file.write_text(
                yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def _read_profiles(self) -> dict:
        if not self.profiles_file.exists():
            return {}
        try:
            data = json.loads(self.profiles_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _read_ui_boot(self) -> dict:
        if not self.ui_boot_file.exists():
            return {
                "mode": "auto",
                "fallback_to_legacy": True,
            }
        try:
            data = json.loads(self.ui_boot_file.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                return {
                    "mode": "auto",
                    "fallback_to_legacy": True,
                }
            mode = str(data.get("mode", "auto")).strip().lower()
            if mode not in {"auto", "web", "legacy"}:
                mode = "auto"
            return {
                "mode": mode,
                "fallback_to_legacy": bool(data.get("fallback_to_legacy", True)),
            }
        except Exception:
            return {
                "mode": "auto",
                "fallback_to_legacy": True,
            }

    def _write_ui_boot(self, state: dict) -> bool:
        if not isinstance(state, dict):
            return False
        mode = str(state.get("mode", "auto")).strip().lower()
        if mode not in {"auto", "web", "legacy"}:
            mode = "auto"
        payload = {
            "mode": mode,
            "fallback_to_legacy": bool(state.get("fallback_to_legacy", True)),
        }
        try:
            self.ui_boot_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def get_config_state(self) -> dict:
        self._ensure_authenticated()
        return self._read_config()

    def save_config_state(self, config: dict) -> bool:
        self._ensure_authenticated()
        if not isinstance(config, dict):
            return False
        return self._write_config(config)

    def get_ui_boot_state(self) -> dict:
        self._ensure_authenticated()
        return self._read_ui_boot()

    def save_ui_boot_state(self, state: dict) -> bool:
        self._ensure_authenticated()
        return self._write_ui_boot(state)

    def list_profiles(self) -> list[str]:
        self._ensure_authenticated()
        return sorted(list(self._read_profiles().keys()))

    def load_profile(self, profile_name: str) -> dict:
        self._ensure_authenticated()
        profiles = self._read_profiles()
        base_cfg = self._read_config()
        if not profile_name or profile_name not in profiles:
            return base_cfg
        merged = merge_profiles_into_config(base_cfg, [profiles[profile_name]])
        return merged if isinstance(merged, dict) else base_cfg

    def save_profile(self, profile_name: str, config: dict) -> bool:
        self._ensure_authenticated()
        name = str(profile_name or "").strip()
        if not name or not isinstance(config, dict):
            return False
        profiles = self._read_profiles()
        profiles[name] = config
        try:
            self.profiles_file.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def delete_profile(self, profile_name: str) -> bool:
        self._ensure_authenticated()
        name = str(profile_name or "").strip()
        if not name:
            return False
        profiles = self._read_profiles()
        if name not in profiles:
            return False
        del profiles[name]
        try:
            self.profiles_file.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    @staticmethod
    def _entity_signature(entity: Any) -> tuple:
        dxf = getattr(entity, "dxf", None)
        layer = str(getattr(dxf, "layer", ""))
        kind = str(entity.dxftype())

        def p(attr: str) -> tuple[float, float]:
            if dxf is None or not hasattr(dxf, attr):
                return (0.0, 0.0)
            point = getattr(dxf, attr)
            try:
                return (round(float(point.x), 3), round(float(point.y), 3))
            except Exception:
                return (0.0, 0.0)

        return (kind, layer, p("insert"), p("start"), p("end"), p("center"))

    def compare_files(self, file_a: str, file_b: str) -> dict:
        self._ensure_authenticated()
        pa = Path(file_a)
        pb = Path(file_b)
        if not pa.exists() or not pb.exists():
            raise FileNotFoundError("Arquivos de comparação não encontrados.")

        da = ezdxf.readfile(str(pa))
        db = ezdxf.readfile(str(pb))

        a_map: dict[str, Any] = {}
        b_map: dict[str, Any] = {}

        for entity in da.modelspace():
            handle = str(getattr(entity.dxf, "handle", "")).strip()
            if not handle:
                continue
            a_map[handle] = entity

        for entity in db.modelspace():
            handle = str(getattr(entity.dxf, "handle", "")).strip()
            if not handle:
                continue
            b_map[handle] = entity

        rows: list[dict[str, str]] = []

        for handle in sorted(set(b_map.keys()) - set(a_map.keys())):
            entity = b_map[handle]
            rows.append({
                "type": "Adicionado",
                "layer": str(getattr(entity.dxf, "layer", "")),
                "handle": handle,
                "detail": f"{entity.dxftype()} presente apenas na revisão B",
            })

        for handle in sorted(set(a_map.keys()) - set(b_map.keys())):
            entity = a_map[handle]
            rows.append({
                "type": "Removido",
                "layer": str(getattr(entity.dxf, "layer", "")),
                "handle": handle,
                "detail": f"{entity.dxftype()} presente apenas na revisão A",
            })

        for handle in sorted(set(a_map.keys()) & set(b_map.keys())):
            sig_a = self._entity_signature(a_map[handle])
            sig_b = self._entity_signature(b_map[handle])
            if sig_a != sig_b:
                rows.append({
                    "type": "Modificado",
                    "layer": str(getattr(b_map[handle].dxf, "layer", "")),
                    "handle": handle,
                    "detail": f"{b_map[handle].dxftype()} alterado entre revisões",
                })

        return {
            "file_a": str(pa),
            "file_b": str(pb),
            "added": sum(1 for r in rows if r["type"] == "Adicionado"),
            "removed": sum(1 for r in rows if r["type"] == "Removido"),
            "modified": sum(1 for r in rows if r["type"] == "Modificado"),
            "total": len(rows),
            "items": rows[:3000],
        }

    def get_watch_state(self) -> dict:
        self._ensure_authenticated()
        with self._watch_lock:
            return {
                "watching": self._watching,
                "folder": self._watch_folder,
                "interval": self._watch_interval,
                "events": len(self._watch_events),
            }

    def get_watch_events(self, limit: int = 200) -> list[dict]:
        self._ensure_authenticated()
        n = max(1, min(2000, int(limit)))
        with self._watch_lock:
            return list(reversed(self._watch_events[-n:]))

    def start_watch(self, folder_path: str, interval_sec: int = 5) -> dict:
        self._ensure_authenticated()
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise NotADirectoryError(f"Pasta inválida: {folder_path}")

        interval = max(3, int(interval_sec))

        with self._watch_lock:
            self._watch_folder = str(folder.resolve())
            self._watch_interval = interval
            self._watch_seen_files = {
                str(f): f.stat().st_mtime for f in folder.rglob("*.dxf") if f.is_file()
            }
            self._watching = True
            self._watch_stop_event.clear()

        self._watch_thread = threading.Thread(target=self._watch_worker, daemon=True)
        self._watch_thread.start()
        return self.get_watch_state()

    def stop_watch(self) -> dict:
        self._ensure_authenticated()
        with self._watch_lock:
            self._watching = False
            self._watch_stop_event.set()
        return self.get_watch_state()

    def _watch_worker(self) -> None:
        while not self._watch_stop_event.wait(self._watch_interval):
            with self._watch_lock:
                if not self._watching:
                    return
                folder = self._watch_folder

            try:
                current = {
                    str(f): f.stat().st_mtime
                    for f in Path(folder).rglob("*.dxf")
                    if f.is_file()
                }
            except Exception:
                continue

            changed = []
            with self._watch_lock:
                for fp, mt in current.items():
                    if fp not in self._watch_seen_files or self._watch_seen_files[fp] != mt:
                        changed.append(fp)
                self._watch_seen_files = current

            for fp in changed:
                try:
                    verify = self.verify_file(fp)
                    row = {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "file": Path(fp).name,
                        "file_path": fp,
                        "status": "✅ OK" if bool(verify.get("passed", False)) else "❌ FALHOU",
                        "errors": int(verify.get("errors", 0)),
                        "warnings": int(verify.get("warnings", 0)),
                        "html_path": str((verify.get("reports", {}) or {}).get("html", "")),
                    }
                except Exception as exc:
                    row = {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "file": Path(fp).name,
                        "file_path": fp,
                        "status": "❌ FALHOU",
                        "errors": 0,
                        "warnings": 0,
                        "html_path": "",
                        "error": str(exc),
                    }

                with self._watch_lock:
                    self._watch_events.append(row)
                    if len(self._watch_events) > 2000:
                        self._watch_events = self._watch_events[-2000:]
