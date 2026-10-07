"""Sigillo in due fasi (Ed25519, stesso schema di chiavi della v3).

- sigillo_tecnico: sulla PARTE TECNICA subito dopo l'aggregazione (tutto tranne manuali,
  osservazioni_dipendente, segnalazioni_dipendente, avvisi_revisione, totali.con_manuali e integrita);
- sigillo_finale: sul rendiconto rivisto INTERO, compreso sigillo_tecnico (quindi il suo hash), escluso
  solo sigillo_finale stesso.

JSON canonico per l'hash: chiavi ordinate, UTF-8, nessuno spazio (separatori "," e ":").
Chiavi: privata in <cartella>/privata.bin (DPAPI su Windows, "PLAIN" altrove — solo per test),
pubblica in <cartella>/pubblica.json con impronta (formato identico alla v3, quindi compatibile).
"""
from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from typing import Optional

_B32 = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # come v3 (senza I, O, 0, 1)
CAMPI_NON_TECNICI = ("manuali", "osservazioni_dipendente", "segnalazioni_dipendente", "avvisi_revisione", "sintesi_ai",
                     "integrita")


# ------------------------------------------------------------------------------------------ lettura JSON
class JsonAmbiguo(ValueError):
    """JSON con chiavi duplicate: Python tiene l'ultima, altri programmi la prima, quindi il file «vale» due cose."""


def _senza_duplicati(coppie):
    d = {}
    for k, v in coppie:
        if k in d:
            raise JsonAmbiguo(f"chiave duplicata nel JSON: {k!r}")
        d[k] = v
    return d


def _costante_non_valida(c):
    raise ValueError(f"valore JSON non ammesso: {c}")


def loads_stretto(testo: str):
    """json.loads che rifiuta chiavi duplicate e NaN/Infinity (non esistono nel JSON canonico dei sigilli)."""
    return json.loads(testo, object_pairs_hook=_senza_duplicati, parse_constant=_costante_non_valida)


def load_stretto(path: str):
    with open(path, encoding="utf-8") as f:
        return loads_stretto(f.read())


# ------------------------------------------------------------------------------------------ canonico/hash
def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def short_code(h: str) -> str:
    n = int(h[:16], 16) >> 4
    chars = []
    for _ in range(12):
        chars.append(_B32[n & 31])
        n >>= 5
    s = "".join(reversed(chars))
    return f"{s[:4]}-{s[4:8]}-{s[8:]}"


def fingerprint(pub: bytes) -> str:
    h = hashlib.sha256(pub).hexdigest()[:20].upper()
    return " ".join(h[i:i + 4] for i in range(0, 20, 4))


def parte_tecnica(doc: dict) -> dict:
    """Copre anche dati_tecnici_postazione, se presente; non cambia con la revisione del dipendente."""
    d = {k: copy.deepcopy(v) for k, v in doc.items() if k not in CAMPI_NON_TECNICI}
    if "totali" in d:
        d["totali"] = {k: v for k, v in d["totali"].items() if k != "con_manuali"}
    return d


def payload_finale(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    d.setdefault("integrita", {})
    d["integrita"] = {k: v for k, v in d["integrita"].items() if k != "sigillo_finale"}
    return d


# ------------------------------------------------------------------------------------------------ chiavi
def _protect(b: bytes) -> bytes:
    if sys.platform == "win32":
        import win32crypt  # type: ignore
        return b"DPAPI" + win32crypt.CryptProtectData(b, "RendicontoSW", None, None, None, 0)
    return b"PLAIN" + b


def _unprotect(b: bytes) -> bytes:
    if b.startswith(b"DPAPI"):
        import win32crypt  # type: ignore
        return win32crypt.CryptUnprotectData(b[5:], None, None, None, 0)[1]
    if b.startswith(b"PLAIN"):
        return b[5:]
    raise ValueError("formato chiave sconosciuto")


def identity() -> dict:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    dom = os.environ.get("USERDOMAIN", "")
    return {"account": f"{dom}\\{user}" if dom else user, "pc": os.environ.get("COMPUTERNAME") or socket.gethostname()}


@dataclass
class KeyPair:
    private: object
    public_raw: bytes
    account: str = ""
    pc: str = ""

    @property
    def impronta(self) -> str:
        return fingerprint(self.public_raw)


def load_or_create_key(folder: str, ident: Optional[dict] = None) -> KeyPair:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv_p, pub_p = os.path.join(folder, "privata.bin"), os.path.join(folder, "pubblica.json")
    raw_fmt = (serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if os.path.exists(priv_p) and os.path.exists(pub_p):
        with open(priv_p, "rb") as f:
            k = Ed25519PrivateKey.from_private_bytes(_unprotect(f.read()))
        with open(pub_p, encoding="utf-8") as f:
            meta = json.load(f)
        return KeyPair(k, k.public_key().public_bytes(*raw_fmt), meta.get("account", ""), meta.get("pc", ""))
    os.makedirs(folder, exist_ok=True)
    ident = ident or identity()
    k = Ed25519PrivateKey.generate()
    raw = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = k.public_key().public_bytes(*raw_fmt)
    with open(priv_p, "wb") as f:
        f.write(_protect(raw))
    try:
        os.chmod(priv_p, 0o600)
    except OSError:
        pass
    with open(pub_p, "w", encoding="utf-8") as f:
        json.dump({"algoritmo": "Ed25519", "chiave_pubblica": base64.b64encode(pub).decode(), "impronta": fingerprint(pub),
                   "account": ident["account"], "pc": ident["pc"],
                   "creata": dt.datetime.now().astimezone().isoformat(timespec="seconds")}, f, ensure_ascii=False, indent=1)
    return KeyPair(k, pub, ident["account"], ident["pc"])


# ------------------------------------------------------------------------------------------------ sigilli
def _seal(payload: dict, tipo: str, key: KeyPair, quando: str) -> dict:
    try:
        dt.datetime.fromisoformat(quando)
    except (TypeError, ValueError):
        raise ValueError(f"istante del sigillo non valido: {quando!r}") from None
    h = sha256_hex(canonical(payload))
    firmato = {"tipo": tipo, "sha256": h, "creato_il": quando, "impronta_chiave": key.impronta}
    sig = key.private.sign(canonical(firmato))
    return {**firmato, "algoritmo": "Ed25519", "codice": short_code(h), "firma": base64.b64encode(sig).decode(),
            "chiave_pubblica": base64.b64encode(key.public_raw).decode(), "account": key.account, "pc": key.pc}


def _now(now: Optional[str]) -> str:
    return now or dt.datetime.now().astimezone().isoformat(timespec="seconds")


def seal_technical(doc: dict, key: KeyPair, now: Optional[str] = None) -> dict:
    out = copy.deepcopy(doc)
    st = _seal(parte_tecnica(doc), "tecnico", key, _now(now))
    if doc.get("schema") in ("rendiconto-sw/giornaliero/4", "rendiconto-sw/giornaliero/5"):
        st.pop("account", None); st.pop("pc", None)
    out["integrita"] = {"sigillo_tecnico": st, "sigillo_finale": None}
    return out


def seal_final(doc: dict, key: KeyPair, now: Optional[str] = None) -> dict:
    st = (doc.get("integrita") or {}).get("sigillo_tecnico")
    if not st:
        raise ValueError("manca il sigillo tecnico: il sigillo finale si appone dopo quello tecnico")
    r = verify(doc, check_final=False)
    if not r["tecnico"]["valido"]:
        raise ValueError("la parte tecnica non corrisponde al sigillo tecnico: " + "; ".join(r["motivi"]))
    s = doc.get("sintesi_ai")
    if s:
        if not s.get("verificata_dal_dipendente"):
            raise ValueError("la sintesi della giornata non è stata confermata dal dipendente («Ho verificato la sintesi»)")
        from redattore import fatti as _fatti      # import locale: l'aggregatore resta usabile anche senza redattore
        if _fatti.impronta(_fatti.estrai(doc)) != s.get("impronta_fatti"):
            raise ValueError("la sintesi non corrisponde ai dati attuali della giornata: va rigenerata")
    out = copy.deepcopy(doc)
    out["integrita"] = {"sigillo_tecnico": st}
    out["integrita"]["sigillo_finale"] = _seal(payload_finale(out), "finale", key, _now(now))
    if doc.get("schema") in ("rendiconto-sw/giornaliero/4", "rendiconto-sw/giornaliero/5"):
        out["integrita"]["sigillo_finale"].pop("account", None)
        out["integrita"]["sigillo_finale"].pop("pc", None)
    return out


_CAMPI_SIGILLO = ("tipo", "sha256", "creato_il", "impronta_chiave", "codice", "firma", "chiave_pubblica")


def _sigillo_ben_formato(seal) -> bool:
    """Un sigillo manomesso (campi di tipo sbagliato) deve dare ALTERATO, non un'eccezione."""
    return (isinstance(seal, dict) and all(isinstance(seal.get(k), str) for k in _CAMPI_SIGILLO)
            and re.fullmatch(r"[0-9a-f]{64}", seal["sha256"]) is not None)


def _check(seal: Optional[dict], payload: dict, tipo: str, motivi: list) -> dict:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    res = {"presente": bool(seal), "valido": False, "codice": None, "impronta_chiave": None}
    if not seal:
        return res
    if not _sigillo_ben_formato(seal):
        motivi.append(f"sigillo {tipo}: struttura non valida (campi mancanti o di tipo errato)")
        return res
    res["codice"], res["impronta_chiave"] = seal.get("codice"), seal.get("impronta_chiave")
    ok = True
    h = sha256_hex(canonical(payload))
    if h != seal.get("sha256"):
        motivi.append(f"sigillo {tipo}: l'hash dei dati non corrisponde (dati modificati)")
        ok = False
    try:
        pub = base64.b64decode(seal["chiave_pubblica"])
        if fingerprint(pub) != seal.get("impronta_chiave"):
            motivi.append(f"sigillo {tipo}: impronta della chiave incoerente")
            ok = False
        firmato = {"tipo": seal["tipo"], "sha256": seal["sha256"], "creato_il": seal["creato_il"],
                   "impronta_chiave": seal["impronta_chiave"]}
        Ed25519PublicKey.from_public_bytes(pub).verify(base64.b64decode(seal["firma"]), canonical(firmato))
    except (InvalidSignature, KeyError, ValueError):
        motivi.append(f"sigillo {tipo}: firma Ed25519 non valida")
        ok = False
    if seal.get("tipo") != tipo:
        motivi.append(f"sigillo {tipo}: tipo errato")
        ok = False
    if seal.get("codice") != short_code(seal.get("sha256", "0" * 16)):
        motivi.append(f"sigillo {tipo}: codice breve incoerente")
        ok = False
    res["valido"] = ok
    return res


def registered_keys(dirs: list[str]) -> dict:
    out = {}
    for d in dirs or []:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                try:
                    j = json.load(open(os.path.join(d, fn), encoding="utf-8"))
                    out[j["impronta"]] = {**j, "file": fn}
                except (OSError, ValueError, KeyError):
                    pass
    return out


def verify(doc: dict, chiavi_dirs: Optional[list[str]] = None, check_final: bool = True) -> dict:
    """Esito: VALIDO (sigilli integri e chiave registrata), INTEGRO (integri, chiave non registrata),
    ALTERATO, NON SIGILLATO. Controlla anche la coerenza dei totali ricalcolati dalle fasce."""
    if isinstance(doc, dict) and doc.get("schema") == "rendiconto-sw/giornaliero/3":
        from .storico_v3 import compute_con_manuali, compute_rilevati
    else:
        from .aggrega import compute_con_manuali, compute_rilevati
    motivi: list[str] = []
    if not isinstance(doc, dict):
        return {"esito": "ALTERATO", "motivi": ["il documento non è un oggetto JSON"], "tecnico": {"presente": False, "valido": False},
                "finale": {"presente": False, "valido": False}, "fase": None}
    integ = doc.get("integrita") or {}
    if not isinstance(integ, dict):
        return {"esito": "ALTERATO", "motivi": ["campo «integrita» non valido"], "tecnico": {"presente": False, "valido": False},
                "finale": {"presente": False, "valido": False}, "fase": None}
    if doc.get("schema") in ("rendiconto-sw/giornaliero/4", "rendiconto-sw/giornaliero/5"):
        from .cli import validate
        motivi.extend("schema documento: " + e for e in validate(doc))
    t = _check(integ.get("sigillo_tecnico"), parte_tecnica(doc), "tecnico", motivi)
    f = {"presente": False, "valido": False}
    if check_final:
        f = _check(integ.get("sigillo_finale"), payload_finale(doc), "finale", motivi)
        if (f["presente"] and t["presente"] and isinstance(integ["sigillo_finale"], dict)
                and isinstance(integ["sigillo_tecnico"], dict)
                and integ["sigillo_finale"].get("impronta_chiave") != integ["sigillo_tecnico"].get("impronta_chiave")):
            motivi.append("i due sigilli usano chiavi diverse")
        # account e pc del sigillo finale non sono nella firma del sigillo stesso: devono coincidere con quelli del
        # sigillo tecnico, che il sigillo finale copre (altrimenti si potrebbero cambiare «chi» e «dove» senza chiave)
        if f["presente"] and t["presente"] and isinstance(integ.get("sigillo_finale"), dict) and isinstance(integ.get("sigillo_tecnico"), dict):
            for campo in ("account", "pc"):
                if integ["sigillo_finale"].get(campo) != integ["sigillo_tecnico"].get(campo):
                    motivi.append(f"sigillo finale: «{campo}» diverso da quello del sigillo tecnico")
    # coerenza: totali ricalcolabili dai dati (protegge da totali «ritoccati» con sigillo rifatto a mano)
    try:
        if doc.get("manuali") is not None and doc.get("totali", {}).get("con_manuali") != compute_con_manuali(doc):
            motivi.append("totali con manuali non coerenti con fasce e attività manuali")
        if doc.get("totali", {}).get("rilevati") != compute_rilevati(doc["fasce"], doc["giorno"], doc["fuso"]):
            motivi.append("totali rilevati non coerenti con le fasce")
    except (KeyError, TypeError, ValueError):
        motivi.append("struttura non valida per il ricalcolo dei totali")
    if not t["presente"]:
        esito = "NON SIGILLATO"
    elif motivi or not t["valido"] or (f["presente"] and not f["valido"]):
        esito = "ALTERATO"
    else:
        reg = registered_keys(chiavi_dirs or [])
        imp = integ["sigillo_tecnico"]["impronta_chiave"]
        acc = integ["sigillo_tecnico"].get("account", "")
        if imp in reg and (doc.get("schema") in ("rendiconto-sw/giornaliero/4", "rendiconto-sw/giornaliero/5") or not reg[imp].get("account") or reg[imp]["account"].lower() == acc.lower()):
            esito = "VALIDO"
        else:
            esito = "INTEGRO"
            motivi.append("sigilli integri, ma la chiave non è nel registro delle chiavi: non è confermato a chi appartiene")
    return {"esito": esito, "motivi": motivi, "tecnico": t, "finale": f,
            "fase": "finale" if f.get("presente") else ("tecnica" if t["presente"] else None)}
