"""Correzioni ai problemi aperti della revisione (R-16…R-18) e regressioni correlate."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from redattore import motore


def test_llama_avvia_con_api_key_casuale_e_bind_localhost(tmp_path, monkeypatch):
    """R-17: ogni avvio di llama-server ha --api-key casuale e --host 127.0.0.1."""
    gguf = tmp_path / "modello.gguf"
    gguf.write_bytes(b"fake")
    visti = {}

    class FakeProc:
        def __init__(self):
            self.pid = 1
            self.returncode = None
            self._handle = 1
        def poll(self):
            return None
        def terminate(self):
            pass
        def wait(self, timeout=None):
            return 0
        def kill(self):
            pass

    def fake_popen(args, **k):
        visti["args"] = list(args)
        return FakeProc()

    class FakeResp:
        status = 200
        def read(self):
            return b'{"build_info":"test"}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    monkeypatch.setattr(motore.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(motore, "_porta_libera", lambda: 8765)
    monkeypatch.setattr(motore, "_get", lambda url, timeout=2, api_key=None: FakeResp())
    m = motore.LlamaCpp("llama-server", str(gguf), timeout_avvio=2)
    with m:
        assert "--host" in visti["args"] and visti["args"][visti["args"].index("--host") + 1] == "127.0.0.1"
        assert "--api-key" in visti["args"]
        key = visti["args"][visti["args"].index("--api-key") + 1]
        assert len(key) >= 16 and key == m.api_key
    # seconda istanza: chiave diversa
    with motore.LlamaCpp("llama-server", str(gguf), timeout_avvio=2) as m2:
        key2 = visti["args"][visti["args"].index("--api-key") + 1]
        assert key2 == m2.api_key and key2 != key


def test_post_invia_authorization_bearer():
    """R-17: le richieste al server portano Authorization: Bearer <chiave>."""
    visti = {}

    class FakeResp:
        def read(self):
            return b'{"content":"{}"}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout=None):
        visti["headers"] = dict(req.headers)
        return FakeResp()

    with mock.patch("redattore.motore._apri", fake_urlopen):
        motore._post("http://127.0.0.1:9/completion", {"a": 1}, timeout=1, api_key="segreto-xyz")
    # urllib may title-case headers
    auth = visti["headers"].get("Authorization") or visti["headers"].get("authorization")
    assert auth == "Bearer segreto-xyz"
