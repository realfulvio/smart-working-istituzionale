"""Cartelle di lavoro: %LOCALAPPDATA%\\RendicontoSW (sovrascrivibile con RSW_BASE, per i test)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Percorsi:
    base: str

    @classmethod
    def predefiniti(cls) -> "Percorsi":
        b = os.environ.get("RSW_BASE")
        if not b:
            root = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
            b = os.path.join(root, "RendicontoSW")
        return cls(os.path.abspath(b))

    def _d(self, *p) -> str:
        d = os.path.join(self.base, *p)
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def raw(self) -> str:
        return self._d("raw")

    @property
    def giorni(self) -> str:
        return self._d("giorni")

    @property
    def stato(self) -> str:
        return self._d("stato")

    @property
    def chiave(self) -> str:
        return self._d("chiave")

    @property
    def diagnostica(self) -> str:
        return self._d("diagnostica")

    def raw_giorno(self, giorno: str) -> str:
        return os.path.join(self.raw, f"{giorno}.jsonl")

    def json_giorno(self, giorno: str) -> str:
        return os.path.join(self.giorni, f"{giorno}.json")
