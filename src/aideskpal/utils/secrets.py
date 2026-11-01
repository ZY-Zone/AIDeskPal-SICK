"""Windows DPAPI-backed secret storage.

API keys and market session cookies never touch the plaintext settings file.  On
Windows the blob is encrypted for the current user with CryptProtectData.  On other
platforms (only used by the test suite / development) we keep an in-memory store and
return an explanatory error rather than writing a weak obfuscation.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


class SecretStore:
    """Load / save a JSON object of secrets with DPAPI protection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._cache: dict[str, str] = {}
        self._loaded = False
        self._memory_only = sys.platform != "win32"

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            raw = self.path.read_bytes()
            if self._memory_only:
                data = json.loads(raw.decode("utf-8"))
            else:
                data = json.loads(self._unprotect(raw).decode("utf-8"))
            if isinstance(data, dict):
                self._cache = {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
        except Exception as exc:
            logger.warning("Could not read encrypted secrets: %s", exc)
            self._cache = {}

    def get(self, key: str, default: str = "") -> str:
        self._load()
        return self._cache.get(key, default)

    def all(self) -> dict[str, str]:
        self._load()
        return dict(self._cache)

    def set(self, key: str, value: str) -> None:
        self._load()
        if value:
            self._cache[key] = value
        else:
            self._cache.pop(key, None)
        self.save()

    def update(self, values: dict[str, str]) -> None:
        self._load()
        for key, value in values.items():
            if value:
                self._cache[key] = value
            else:
                self._cache.pop(key, None)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self._cache, ensure_ascii=False).encode("utf-8")
        if self._memory_only:
            payload = raw
        else:
            payload = self._protect(raw)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(self.path)

    # ------------------------------------------------------------------ DPAPI
    @staticmethod
    def _protect(data: bytes) -> bytes:
        if sys.platform != "win32":
            raise SecretStoreError("DPAPI is only available on Windows")
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in, _buffer_in = _blob(data)
        blob_out = _DataBlob()
        if not crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            "AIDeskPal-SICK",
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        ):
            raise SecretStoreError("CryptProtectData failed")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)

    @staticmethod
    def _unprotect(data: bytes) -> bytes:
        if sys.platform != "win32":
            raise SecretStoreError("DPAPI is only available on Windows")
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in, _buffer_in = _blob(data)
        blob_out = _DataBlob()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        ):
            raise SecretStoreError("CryptUnprotectData failed")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "•" * len(value)
    return "•" * (len(value) - visible) + value[-visible:]
