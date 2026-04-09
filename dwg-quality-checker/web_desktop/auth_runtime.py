from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


def _to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_login(value: str) -> str:
    return value.strip().lower()


def _is_valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


@dataclass(frozen=True)
class AuthSettings:
    supabase_url: str
    supabase_anon_key: str
    require_subscription: bool
    subscriptions_table: str
    session_validate_interval_sec: int
    auth_event_log_enabled: bool

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)


def load_auth_settings(base_dir: Path) -> AuthSettings:
    cfg_file = base_dir / "auth_config.json"
    cfg: dict = {}

    if cfg_file.exists():
        try:
            loaded = json.loads(cfg_file.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            cfg = {}

    supabase_url = str(cfg.get("SUPABASE_URL", "")).strip().rstrip("/")
    supabase_anon_key = str(cfg.get("SUPABASE_ANON_KEY", "")).strip()
    require_sub = _to_bool(cfg.get("SUPABASE_REQUIRE_SUBSCRIPTION", False), default=False)
    subscriptions_table = str(cfg.get("SUPABASE_SUBSCRIPTIONS_TABLE", "subscriptions")).strip() or "subscriptions"
    session_validate_interval_sec = int(cfg.get("AUTH_SESSION_VALIDATE_INTERVAL_SEC", 180) or 180)
    auth_event_log_enabled = _to_bool(cfg.get("AUTH_EVENT_LOG_ENABLED", True), default=True)

    env_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    env_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    env_sub_table = os.getenv("SUPABASE_SUBSCRIPTIONS_TABLE", "").strip()
    env_session_validate_interval = os.getenv("AUTH_SESSION_VALIDATE_INTERVAL_SEC", "").strip()
    env_auth_event_log_enabled = os.getenv("AUTH_EVENT_LOG_ENABLED")

    if env_url:
        supabase_url = env_url
    if env_key:
        supabase_anon_key = env_key
    if env_sub_table:
        subscriptions_table = env_sub_table
    if env_session_validate_interval:
        try:
            session_validate_interval_sec = int(env_session_validate_interval)
        except Exception:
            pass
    if env_auth_event_log_enabled is not None:
        auth_event_log_enabled = _to_bool(env_auth_event_log_enabled, default=auth_event_log_enabled)
    if os.getenv("SUPABASE_REQUIRE_SUBSCRIPTION") is not None:
        require_sub = _to_bool(os.getenv("SUPABASE_REQUIRE_SUBSCRIPTION"), default=require_sub)

    session_validate_interval_sec = max(15, min(3600, int(session_validate_interval_sec or 180)))

    return AuthSettings(
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        require_subscription=require_sub,
        subscriptions_table=subscriptions_table,
        session_validate_interval_sec=session_validate_interval_sec,
        auth_event_log_enabled=auth_event_log_enabled,
    )


class SupabaseAuthManager:
    backend_name = "Supabase"

    def __init__(self, settings: AuthSettings) -> None:
        self.url = settings.supabase_url.rstrip("/")
        self.anon_key = settings.supabase_anon_key
        self.require_subscription = settings.require_subscription
        self.subscriptions_table = settings.subscriptions_table

    def has_users(self) -> bool:
        return True

    def _request_json(
        self,
        method: str,
        path_with_query: str,
        payload: dict | None = None,
        access_token: str | None = None,
    ) -> tuple[int, dict | list | None, str | None]:
        url = f"{self.url}{path_with_query}"
        headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
        }

        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        else:
            headers["Authorization"] = f"Bearer {self.anon_key}"

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                obj = json.loads(raw) if raw else None
                return int(resp.status), obj, None
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
                obj = json.loads(raw) if raw else {}
                msg = obj.get("msg") or obj.get("message") or obj.get("error_description") or str(obj)
            except Exception:
                msg = str(exc)
            return int(getattr(exc, "code", 500)), None, msg
        except Exception as exc:
            return 0, None, str(exc)

    def register(self, name: str, email: str, password: str) -> tuple[bool, str]:
        name = name.strip()
        email_n = _normalize_login(email)

        if len(name) < 2:
            return False, "Nome deve ter pelo menos 2 caracteres."
        if not _is_valid_email(email_n):
            return False, "E-mail inválido."
        if len(password) < 8:
            return False, "A senha deve ter no mínimo 8 caracteres."

        status, _, err = self._request_json(
            "POST",
            "/auth/v1/signup",
            {
                "email": email_n,
                "password": password,
                "data": {"full_name": name},
            },
        )
        if status in (200, 201):
            return True, "Conta criada com sucesso."
        return False, err or "Falha ao criar conta no Supabase."

    def _has_active_subscription(self, user_id: str, access_token: str) -> tuple[bool, str | None]:
        if not self.require_subscription:
            return True, None

        uid = urllib.parse.quote(user_id, safe="")
        q = (
            f"/rest/v1/{self.subscriptions_table}"
            f"?select=id,status,current_period_end"
            f"&user_id=eq.{uid}"
            f"&status=in.(active,trialing)"
            f"&order=current_period_end.desc"
            f"&limit=1"
        )
        status, obj, err = self._request_json("GET", q, access_token=access_token)
        if status != 200:
            return False, err or "Falha ao validar assinatura."
        if isinstance(obj, list) and obj:
            return True, None
        return False, "Assinatura inativa. Entre em contato para ativar seu acesso."

    def authenticate(self, email: str, password: str) -> tuple[dict | None, str | None]:
        email_n = _normalize_login(email)
        status, obj, err = self._request_json(
            "POST",
            "/auth/v1/token?grant_type=password",
            {"email": email_n, "password": password},
        )

        if status != 200 or not isinstance(obj, dict):
            return None, err or "Credenciais inválidas."

        access_token = str(obj.get("access_token", ""))
        user_obj = obj.get("user") if isinstance(obj.get("user"), dict) else {}
        user_id = str(user_obj.get("id", ""))

        if not user_id and access_token:
            st_u, obj_u, err_u = self._request_json("GET", "/auth/v1/user", access_token=access_token)
            if st_u == 200 and isinstance(obj_u, dict):
                user_obj = obj_u
                user_id = str(obj_u.get("id", ""))
            elif err_u:
                return None, err_u

        if not user_id:
            return None, "Usuário não identificado no Supabase."

        ok_sub, sub_err = self._has_active_subscription(user_id, access_token)
        if not ok_sub:
            return None, sub_err

        md = user_obj.get("user_metadata") if isinstance(user_obj.get("user_metadata"), dict) else {}
        return {
            "id": user_id,
            "name": md.get("full_name") or email_n.split("@")[0],
            "email": user_obj.get("email", email_n),
            "access_token": access_token,
            "refresh_token": str(obj.get("refresh_token", "")),
            "expires_in": int(obj.get("expires_in", 0) or 0),
        }, None

    def refresh_access_token(self, refresh_token: str) -> tuple[dict | None, str | None]:
        token = str(refresh_token or "").strip()
        if not token:
            return None, "Refresh token ausente."

        status, obj, err = self._request_json(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": token},
        )
        if status != 200 or not isinstance(obj, dict):
            return None, err or "Não foi possível renovar a sessão."

        access_token = str(obj.get("access_token", "")).strip()
        if not access_token:
            return None, "Resposta de renovação sem access token."

        returned_refresh = str(obj.get("refresh_token", "")).strip() or token
        st_u, obj_u, err_u = self._request_json("GET", "/auth/v1/user", access_token=access_token)
        if st_u != 200 or not isinstance(obj_u, dict):
            return None, err_u or "Não foi possível validar usuário após renovação."

        user_id = str(obj_u.get("id", "")).strip()
        if not user_id:
            return None, "Usuário inválido após renovação da sessão."

        ok_sub, sub_err = self._has_active_subscription(user_id, access_token)
        if not ok_sub:
            return None, sub_err or "Assinatura inválida."

        md = obj_u.get("user_metadata") if isinstance(obj_u.get("user_metadata"), dict) else {}
        return {
            "id": user_id,
            "name": md.get("full_name") or str(obj_u.get("email", "")).split("@")[0],
            "email": obj_u.get("email", ""),
            "access_token": access_token,
            "refresh_token": returned_refresh,
            "expires_in": int(obj.get("expires_in", 0) or 0),
        }, None

    def logout(self, access_token: str) -> tuple[bool, str | None]:
        token = str(access_token or "").strip()
        if not token:
            return False, "Token ausente para logout."

        status, _, err = self._request_json(
            "POST",
            "/auth/v1/logout",
            payload={},
            access_token=token,
        )

        # Supabase pode retornar 200/204 e em alguns cenários 401 se o token já expirou.
        if status in (200, 204, 401):
            return True, None
        return False, err or "Falha ao encerrar sessão no servidor."

    def validate_access_token(
        self,
        access_token: str,
        expected_user_id: str | None = None,
    ) -> tuple[dict | None, str | None]:
        token = str(access_token or "").strip()
        if not token:
            return None, "Token ausente."

        st_u, obj_u, err_u = self._request_json("GET", "/auth/v1/user", access_token=token)
        if st_u != 200 or not isinstance(obj_u, dict):
            return None, err_u or "Sessão inválida ou expirada."

        user_id = str(obj_u.get("id", "")).strip()
        if not user_id:
            return None, "Usuário inválido na sessão."
        if expected_user_id and str(expected_user_id).strip() and user_id != str(expected_user_id).strip():
            return None, "Sessão não corresponde ao usuário autenticado."

        ok_sub, sub_err = self._has_active_subscription(user_id, token)
        if not ok_sub:
            return None, sub_err or "Assinatura inválida."

        md = obj_u.get("user_metadata") if isinstance(obj_u.get("user_metadata"), dict) else {}
        return {
            "id": user_id,
            "name": md.get("full_name") or str(obj_u.get("email", "")).split("@")[0],
            "email": obj_u.get("email", ""),
            "access_token": token,
            "refresh_token": "",
            "expires_in": 0,
        }, None