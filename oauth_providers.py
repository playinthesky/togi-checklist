"""소셜 로그인 제공자 (Kakao · Google · Naver) — 표준 라이브러리 전용.

togi-checklist 서버(http.server 기반)에 추가 의존성 없이 OAuth 2.0
Authorization Code 플로우를 붙이기 위한 모듈입니다. 자격증명은 환경 변수로
주입하며, 값이 있는 제공자만 로그인 화면에 노출됩니다.
"""

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TIMEOUT = 10  # 초

PROVIDER_ORDER = ["kakao", "google", "naver"]


class OAuthError(Exception):
    pass


def _env(*names):
    for name in names:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    return ""


def _parse_google(data):
    return {
        "provider_uid": str(data.get("sub", "")),
        "email": (data.get("email") or "").lower(),
        "name": data.get("name") or data.get("given_name") or "",
    }


def _parse_kakao(data):
    account = data.get("kakao_account", {}) or {}
    profile = account.get("profile", {}) or {}
    return {
        "provider_uid": str(data.get("id", "")),
        "email": (account.get("email") or "").lower(),
        "name": profile.get("nickname", ""),
    }


def _parse_naver(data):
    res = data.get("response", {}) or {}
    return {
        "provider_uid": str(res.get("id", "")),
        "email": (res.get("email") or "").lower(),
        "name": res.get("name") or res.get("nickname") or "",
    }


_SPECS = {
    "google": {
        "label": "Google",
        "color": "#FFFFFF", "text_color": "#1F2937", "border": "#DADCE0",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "parse": _parse_google,
        "client_id_env": ("GOOGLE_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
        "client_secret_env": ("GOOGLE_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
        "secret_required": True,
        "extra": {"access_type": "online", "prompt": "select_account"},
    },
    "kakao": {
        "label": "카카오",
        "color": "#FEE500", "text_color": "#191600", "border": "#FEE500",
        "authorize_url": "https://kauth.kakao.com/oauth/authorize",
        "token_url": "https://kauth.kakao.com/oauth/token",
        "userinfo_url": "https://kapi.kakao.com/v2/user/me",
        "scope": "profile_nickname account_email",
        "parse": _parse_kakao,
        "client_id_env": ("KAKAO_CLIENT_ID", "KAKAO_REST_API_KEY"),
        "client_secret_env": ("KAKAO_CLIENT_SECRET",),
        "secret_required": False,
        "extra": {},
    },
    "naver": {
        "label": "네이버",
        "color": "#03C75A", "text_color": "#FFFFFF", "border": "#03C75A",
        "authorize_url": "https://nid.naver.com/oauth2.0/authorize",
        "token_url": "https://nid.naver.com/oauth2.0/token",
        "userinfo_url": "https://openapi.naver.com/v1/nid/me",
        "scope": "",
        "parse": _parse_naver,
        "client_id_env": ("NAVER_CLIENT_ID",),
        "client_secret_env": ("NAVER_CLIENT_SECRET",),
        "secret_required": True,
        "extra": {},
    },
}


class Provider:
    def __init__(self, key, spec):
        self.key = key
        self.label = spec["label"]
        self.color = spec["color"]
        self.text_color = spec["text_color"]
        self.border = spec["border"]
        self.authorize_url = spec["authorize_url"]
        self.token_url = spec["token_url"]
        self.userinfo_url = spec["userinfo_url"]
        self.scope = spec["scope"]
        self.extra = spec["extra"]
        self._parse = spec["parse"]
        self._secret_required = spec["secret_required"]
        self.client_id = _env(*spec["client_id_env"])
        self.client_secret = _env(*spec["client_secret_env"])

    @property
    def configured(self):
        if not self.client_id:
            return False
        if self._secret_required and not self.client_secret:
            return False
        return True

    def parse_profile(self, data):
        p = self._parse(data)
        p["provider"] = self.key
        return p

    def button(self):
        return {"key": self.key, "label": self.label, "color": self.color,
                "text_color": self.text_color, "border": self.border}


def get_provider(key):
    spec = _SPECS.get(key)
    return Provider(key, spec) if spec else None


def enabled_providers():
    return [p for p in (get_provider(k) for k in PROVIDER_ORDER) if p and p.configured]


# ── OAuth 플로우 (urllib) ─────────────────────────────────────────────────────
def build_authorize_url(provider, redirect_uri, state):
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if provider.scope:
        params["scope"] = provider.scope
    params.update(provider.extra)
    return f"{provider.authorize_url}?{urlencode(params)}"


def _http_json(req):
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        raise OAuthError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise OAuthError(f"네트워크 오류: {exc}") from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise OAuthError("응답을 해석할 수 없습니다.") from exc


def exchange_code_for_token(provider, code, redirect_uri, state=None):
    data = {
        "grant_type": "authorization_code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if provider.client_secret:
        data["client_secret"] = provider.client_secret
    if state is not None:
        data["state"] = state
    req = Request(
        provider.token_url,
        data=urlencode(data).encode("utf-8"),
        headers={"Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    payload = _http_json(req)
    if payload.get("error"):
        raise OAuthError(f"토큰 오류: {payload.get('error_description') or payload['error']}")
    token = payload.get("access_token")
    if not token:
        raise OAuthError("access_token이 없습니다.")
    return token


def fetch_profile(provider, access_token):
    req = Request(
        provider.userinfo_url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="GET",
    )
    data = _http_json(req)
    profile = provider.parse_profile(data)
    if not profile.get("provider_uid"):
        raise OAuthError("프로필에서 사용자 식별자를 찾을 수 없습니다.")
    return profile
