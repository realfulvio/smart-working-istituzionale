"""Elimina solo raw marcati dopo l'adozione, confermati e scaduti secondo policy CED.

Non importa dataset storici. Il modulo non viene eseguito dall'agente sui dati reali.
I sigilli, le giornate aggregate, i PDF e le chiavi non sono cancellati.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from aggregatore.configurazione import carica
from aggregatore.sigillo import load_stretto, verify


def marca_nuova(p, giorno):
    dt.date.fromisoformat(giorno)
    base = Path(p.base).resolve()
    raw = base / "raw" / f"{giorno}.jsonl"
    if raw.exists() or (base / "giorni" / f"{giorno}.json").exists():
        return  # non marcare dati preesistenti
    folder = base / "retention"
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / f"{giorno}.json"
    if not marker.exists():
        marker.write_text(json.dumps({"giorno": giorno, "schema": "rendiconto-sw/giornaliero/5"}), encoding="utf-8")


def applica(p, oggi=None, policy=None, confermati=None, esegui=False):
    """Anteprima di default. Esecuzione solo dopo conferma, con policy validata dal CED.

    confermati: cartella dei JSON finali salvati dal Servizio. Nessun path proviene dal raw.
    """
    policy = carica() if policy is None else policy
    giorni, da = policy.get("retention_raw_giorni"), policy.get("retention_da_data")
    if giorni is None or da is None:
        return {"stato": "policy_da_validare", "eleggibili": [], "eliminati": []}
    if type(giorni) is not int or giorni < 1:
        raise ValueError("retention_raw_giorni: intero >= 1 richiesto")
    if not isinstance(da, str):
        raise ValueError("retention_da_data: data YYYY-MM-DD richiesta")
    decorrenza = dt.date.fromisoformat(da)
    oggi = oggi or dt.date.today()
    base = Path(p.base).resolve()
    finali = Path(confermati).resolve() if confermati else base / "finali"
    eleggibili, eliminati = [], []
    for marker in sorted((base / "retention").glob("????-??-??.json")):
        if marker.is_symlink() or not marker.resolve().is_relative_to(base):
            continue
        try:
            giorno = dt.date.fromisoformat(marker.stem)
            m = load_stretto(str(marker))
            if m != {"giorno": marker.stem, "schema": "rendiconto-sw/giornaliero/5"}:
                continue
            if giorno < decorrenza or (oggi - giorno).days < giorni:
                continue
            finale = finali / f"{marker.stem}.json"
            doc = load_stretto(str(finale))
            if doc.get("giorno") != marker.stem or doc.get("schema") != m["schema"]:
                continue
            risultato = verify(doc)
            if risultato["esito"] not in ("INTEGRO", "VALIDO") or risultato["fase"] != "finale":
                continue
            raw = base / "raw" / f"{marker.stem}.jsonl"
            if not raw.is_file() or raw.is_symlink() or not raw.resolve().is_relative_to(base):
                continue
            eleggibili.append(marker.stem)
            if esegui:
                backup = Path(str(raw) + ".prima_della_chiusura")
                if backup.exists():
                    if backup.is_symlink() or not backup.resolve().is_relative_to(base):
                        continue
                    backup.unlink()
                raw.unlink()
                eliminati.append(marker.stem)
        except (OSError, ValueError, TypeError, KeyError):
            continue  # dati dubbi conservati, nessuna cancellazione
    return {"stato": "eseguita" if esegui else "anteprima", "eleggibili": eleggibili, "eliminati": eliminati}
