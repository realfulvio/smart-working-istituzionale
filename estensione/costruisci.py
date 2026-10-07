"""Genera i pacchetti dell'estensione (Chrome/Edge e Firefox) e i manifest dell'host Native Messaging.

    python -m estensione.costruisci --uscita dist_estensione [--chiave-pubblica <base64 DER>] [--profilo X]

- host_permissions = SOLO i domini dei siti della mappatura del CED (config/applicazioni.json), esclusi gli
  «esclusi»: è questo, e non il permesso «tabs», a rendere visibile l'indirizzo della scheda, e solo per quei siti.
- La chiave PRIVATA di firma non entra mai nel repository: per un ID fisso su Chrome/Edge si passa solo la chiave
  pubblica (campo «key» del manifest); l'ID si ricava da essa.
- Nessun permesso «tabs», «history», «webRequest», «scripting», nessun content script, nessuna CSP allentata."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil

from aggregatore.mappa import RE_IPV4, Mappa

from . import NOME_HOST

VERSIONE = "0.8.0"
ID_FIREFOX = "rendiconto-sw@smartworking.invalid"
PERMESSI = ["alarms", "idle", "storage", "nativeMessaging"]
SORGENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sorgente")
DESCRIZIONE = ("Rendiconto lavoro agile (Ente): conta per fasce di 15 minuti i soli siti di lavoro "
               "dell'elenco del CED. Non legge indirizzi completi, titoli o testo.")


def id_chromium(chiave_pubblica_b64: str) -> str:
    """ID dell'estensione Chrome/Edge dalla chiave pubblica (SHA-256 del DER, primi 32 esadecimali in a-p)."""
    der = base64.b64decode(chiave_pubblica_b64)
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])


def permessi_host(mappa: Mappa) -> list[str]:
    out = set()
    for d in mappa.per_dominio:
        if mappa.escluso(d):
            continue
        out.add(f"*://{d}/*")
        if not RE_IPV4.match(d):
            out.add(f"*://*.{d}/*")
    return sorted(out)


def manifest(mappa: Mappa, browser: str, chiave_pubblica: str | None = None) -> dict:
    m = {"manifest_version": 3, "name": "Rendiconto SW", "version": VERSIONE, "description": DESCRIZIONE,
         "permissions": list(PERMESSI), "host_permissions": permessi_host(mappa)}
    if browser == "firefox":
        m["background"] = {"scripts": ["background.js"]}
        m["browser_specific_settings"] = {"gecko": {"id": ID_FIREFOX, "strict_min_version": "128.0",
                                                    "data_collection_permissions": {"required": ["none"]}}}
    else:
        m["background"] = {"service_worker": "background.js"}
        m["minimum_chrome_version"] = "121"
        if chiave_pubblica:
            m["key"] = chiave_pubblica
    return m


def manifest_host(percorso_exe: str, browser: str, id_ext: str | None) -> dict:
    m = {"name": NOME_HOST, "description": "Rendiconto SW - host locale dell'estensione",
         "path": percorso_exe, "type": "stdio"}
    if browser == "firefox":
        m["allowed_extensions"] = [ID_FIREFOX]
    else:
        m["allowed_origins"] = [f"chrome-extension://{id_ext}/"] if id_ext else []
    return m


def costruisci(uscita: str, mappa: Mappa, chiave_pubblica: str | None = None,
               percorso_exe: str = r"%LOCALAPPDATA%\Programs\RendicontoSW\RendicontoSW-host.exe") -> dict:
    id_ext = id_chromium(chiave_pubblica) if chiave_pubblica else None
    for browser in ("chromium", "firefox"):
        d = os.path.join(uscita, browser)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(os.path.join(SORGENTE, "background.js"), os.path.join(d, "background.js"))
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest(mappa, browser, chiave_pubblica), f, ensure_ascii=False, indent=2)
        with open(os.path.join(uscita, f"host-{browser}.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_host(percorso_exe, browser, id_ext), f, ensure_ascii=False, indent=2)
    return {"id_chromium": id_ext, "id_firefox": ID_FIREFOX, "host_permissions": permessi_host(mappa)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--uscita", required=True)
    ap.add_argument("--chiave-pubblica", help="chiave pubblica (base64 DER) per un ID fisso su Chrome/Edge")
    ap.add_argument("--profilo", action="append", default=[])
    a = ap.parse_args(argv)
    if a.chiave_pubblica and not re.fullmatch(r"[A-Za-z0-9+/=]{100,}", a.chiave_pubblica):
        ap.error("chiave pubblica non valida (serve il base64 del DER, non la chiave privata)")
    r = costruisci(a.uscita, Mappa.predefinita(a.profilo), a.chiave_pubblica)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
