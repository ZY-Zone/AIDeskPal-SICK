"""HTTP client for the /cwusr market portal."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


class MarketError(RuntimeError):
    def __init__(self, message: str, *, code: str = "market_error", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def normalize_market_url(value: str) -> str:
    """Normalize the desktop market endpoint.

    The desktop market address is fixed by the application; this is an API base,
    not a browser landing page.
    """
    base = (value or "").strip().rstrip("/")
    if not base:
        base = "http://sickcc.online/cwusr"
    if "://" not in base:
        base = "http://" + base
    if not (base.startswith("http://") or base.startswith("https://")):
        raise MarketError("市场地址必须以 http:// 或 https:// 开头", code="bad_url")
    return base


class MarketClient:
    def __init__(self, base_url: str, session_cookie: str = "", *, timeout: float = 40.0) -> None:
        self.base_url = self._normalize_base(base_url)
        self.session_cookie = session_cookie
        self._timeout = httpx.Timeout(timeout, connect=15.0)

    @staticmethod
    def _normalize_base(value: str) -> str:
        return normalize_market_url(value)

    @property
    def portal_url(self) -> str:
        return self.base_url + "/"

    def _cookies(self) -> dict[str, str]:
        return {"cw_session": self.session_cookie} if self.session_cookie else {}

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"User-Agent": "AIDeskPal-SICK/1.0", "Accept": "application/json"},
            cookies=self._cookies(),
        )

    def _url(self, path: str) -> str:
        return self.base_url + "/api/" + path.lstrip("/")

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            message = "登录已过期，请在市场页重新登录"
            try:
                error = response.json().get("error") or {}
                message = error.get("message") or message
            except Exception:
                pass
            raise MarketError(message, code="unauthorized", status=response.status_code)
        if response.status_code >= 400:
            message = f"市场请求失败（HTTP {response.status_code}）"
            code = "http_error"
            try:
                error = response.json().get("error") or {}
                message = error.get("message") or message
                code = error.get("code") or code
            except Exception:
                pass
            raise MarketError(message, code=code, status=response.status_code)

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with self._client() as client:
                response = client.request(method, self._url(path), **kwargs)
        except httpx.HTTPError as exc:
            raise MarketError(f"无法连接市场服务器：{type(exc).__name__}", code="network") from exc
        self._raise_for_response(response)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise MarketError("市场返回了无法解析的数据", code="bad_json") from exc
        if isinstance(data, dict) and data.get("ok") is False:
            error = data.get("error") or {}
            raise MarketError(
                str(error.get("message", "市场返回错误")),
                code=str(error.get("code", "market_error")),
                status=response.status_code,
            )
        return data.get("data", data) if isinstance(data, dict) else {"data": data}

    def health(self) -> dict[str, Any]:
        return self._json("GET", "health")

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self._json("POST", "login", json={"username": username, "password": password})
        cookie = data.get("session") or data.get("cookie")
        if cookie:
            self.session_cookie = cookie
        return data

    def register(self, username: str, password: str, email: str = "") -> dict[str, Any]:
        data = self._json(
            "POST", "register", json={"username": username, "password": password, "email": email}
        )
        cookie = data.get("session") or data.get("cookie")
        if cookie:
            self.session_cookie = cookie
        return data

    def me(self) -> dict[str, Any]:
        return self._json("GET", "me")

    def logout(self) -> None:
        try:
            self._json("POST", "logout")
        finally:
            self.session_cookie = ""

    def bundles(self, query: str = "") -> list[dict[str, Any]]:
        data = self._json("GET", "bundles", params={"q": query})
        items = data.get("items", data if isinstance(data, list) else [])
        return list(items)

    def plugins(self, query: str = "") -> list[dict[str, Any]]:
        data = self._json("GET", "plugins", params={"q": query})
        items = data.get("items", data if isinstance(data, list) else [])
        return list(items)

    def download(
        self,
        kind: str,
        resource_id: int | str,
        destination: Path | None = None,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        if kind not in {"bundle", "plugin"}:
            raise MarketError("未知的资源类型", code="bad_kind")
        path = f"{kind}s/{int(resource_id)}/download"
        target = destination or (
            Path(tempfile.gettempdir()) / f"aideskpal-{kind}-{int(resource_id)}.zip"
        )
        try:
            with self._client() as client:
                with client.stream("GET", self._url(path)) as response:
                    self._raise_for_response(response)
                    total = int(response.headers.get("Content-Length", "0") or 0)
                    received = 0
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("wb") as handle:
                        for chunk in response.iter_bytes(256 * 1024):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            received += len(chunk)
                            if received > 512 * 1024 * 1024:
                                raise MarketError("资源包超过 512 MB，已中止下载", code="too_large")
                            if progress:
                                progress(received, total)
        except httpx.HTTPError as exc:
            raise MarketError(f"下载失败：{type(exc).__name__}", code="network") from exc
        return target

    def fetch_catalog(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return self.bundles(), self.plugins()
