"""Mappatura applicazioni/siti -> etichetta e categoria (file config/applicazioni.json, modificabile dal CED).

- 'applicazioni': eseguibile (es. WINWORD.EXE) -> {id, etichetta, categoria};
- 'siti': etichetta della whitelist dei siti di lavoro -> {etichetta, categoria, [domini]} (es. Halley, che è un
  servizio web: gestionale.esempio.test); un dominio vale anche per i suoi sottodomini;
- 'categorie': le sei categorie di base sono fisse (CATEGORIE_BASE); il CED può aggiungerne altre;
- 'profili': ogni sito appartiene a un profilo (predefinito 'generale', valido per tutti). Gli altri profili (es.
  'sistemi_informativi', strumenti per il solo personale del CED) sono facoltativi: i loro siti vengono riconosciuti
  solo se il profilo è attivato per la postazione; altrimenti quei domini restano «navigazione web».
  Un dominio vale anche per i sottodomini; un indirizzo IPv4 (es. una console interna) vale solo per sé stesso.

Un eseguibile non elencato non viene registrato dal collector (bonifica B5); in un vecchio grezzo l'aggregatore lo
riduce a semplice «attività» senza nome (``altra_applicazione`` resta riservato). Un sito senza
etichetta o fuori elenco diventa ``web_generico``: «sconosciuto» non significa mai «non lavoro».
Il nome dell'eseguibile serve solo a trovare l'id: non viene mai copiato nel JSON giornaliero.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

RE_ID = re.compile(r"^[a-z0-9_]{1,40}\Z")
RE_DOMINIO = re.compile(r"^(?=.{1,253}\Z)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
RE_IPV4 = re.compile(r"^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\Z")
PROFILO_GENERALE = "generale"
_RE_SCHEMA = re.compile(r"^[a-z][a-z0-9+.-]*://")


def solo_host(valore: str) -> str:
    """Riduce un dominio o un URL al solo nome host: via schema, credenziali, porta, percorso, query e frammento.

    Esempio: ``https://gestionale.esempio.test:8443/halley/x?tok=…`` -> ``gestionale.esempio.test``.
    Porta, percorso e query (che possono contenere token di sessione) non vengono mai conservati."""
    v = str(valore or "").strip().lower()
    v = _RE_SCHEMA.sub("", v)
    v = re.split(r"[/?#\\]", v, maxsplit=1)[0]
    v = v.rpartition("@")[2]
    if v.startswith("["):                                   # IPv6 tra parentesi: non gestito, resta web generico
        return ""
    if v.count(":") == 1:
        v = v.partition(":")[0]
    elif ":" in v:
        return ""
    return v.rstrip(".")

CATEGORIE_BASE = {"office": "Strumenti d'ufficio", "posta": "Posta elettronica", "halley": "Gestionale Halley",
                  "web_generico": "Navigazione web", "rete": "Traffico di rete",
                  "interazione_postazione": "Uso della postazione"}
APP_SCONOSCIUTA = ("altra_applicazione", "Altra applicazione", "interazione_postazione")
PERCORSO_PREDEFINITO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config",
                                    "applicazioni.json")


class ErroreMappa(ValueError):
    """File di mappatura non valido."""


@dataclass
class Mappa:
    versione: str = "incorporata"
    categorie: dict = field(default_factory=lambda: dict(CATEGORIE_BASE))
    per_exe: dict = field(default_factory=dict)      # "WINWORD.EXE" -> (id, etichetta, categoria)
    per_id: dict = field(default_factory=dict)       # "word" -> (etichetta, categoria)
    siti: dict = field(default_factory=dict)         # "inps" -> (etichetta, categoria)
    per_dominio: dict = field(default_factory=dict)  # "gestionale.esempio.test" -> "halley"
    profili: dict = field(default_factory=lambda: {PROFILO_GENERALE: ""})   # profili disponibili -> descrizione
    profili_attivi: tuple = (PROFILO_GENERALE,)
    esclusi: dict = field(default_factory=dict)      # dominio -> motivo: mai sito di lavoro (es. simulazioni di phishing)

    # ------------------------------------------------------------------------------------- risoluzione
    def da_exe(self, exe: str) -> str:
        """Nome dell'eseguibile (con o senza percorso) -> id applicazione; sconosciuto -> altra_applicazione."""
        base = re.split(r"[\\/]", exe.strip())[-1].upper()
        hit = self.per_exe.get(base)
        return hit[0] if hit else APP_SCONOSCIUTA[0]

    def app(self, app_id: str) -> tuple[str, str]:
        """id -> (etichetta, categoria). Id fuori elenco: etichetta derivata dall'id, categoria interazione_postazione."""
        if app_id == APP_SCONOSCIUTA[0]:
            return APP_SCONOSCIUTA[1], APP_SCONOSCIUTA[2]
        return self.per_id.get(app_id, (app_id.replace("_", " ").capitalize(), "interazione_postazione"))

    def da_dominio(self, dominio: str) -> str:
        """Dominio -> id del sito in whitelist (anche sottodominio); fuori elenco -> "" (web generico)."""
        d = solo_host(dominio)                                  # la porta (es. :8443) non conta
        if self.escluso(d):
            return ""
        if RE_IPV4.match(d) or d.replace(".", "").isdigit():   # indirizzi numerici: solo corrispondenza esatta
            return self.per_dominio.get(d, "")
        while d:
            if d in self.per_dominio:
                return self.per_dominio[d]
            d = d.partition(".")[2]
        return ""

    def escluso(self, dominio: str) -> str:
        """Motivo dell'esclusione se il dominio (o un suo dominio padre) è nell'elenco 'esclusi', altrimenti ""."""
        d = solo_host(dominio)
        while d:
            if d in self.esclusi:
                return self.esclusi[d]
            d = d.partition(".")[2]
        return ""

    def sito(self, sito_id: str) -> tuple[str, str]:
        return self.siti.get(sito_id, ("Sito non in elenco", "web_generico"))

    def etichetta_categoria(self, cat: str) -> str:
        return self.categorie.get(cat, cat)

    # ------------------------------------------------------------------------------------------ lettura
    @classmethod
    def da_dict(cls, cfg: dict, profili=()) -> "Mappa":
        """``profili``: profili facoltativi da attivare oltre a 'generale' (es. ["sistemi_informativi"])."""
        if not isinstance(cfg, dict):
            raise ErroreMappa("la mappatura deve essere un oggetto JSON")
        disp = {PROFILO_GENERALE: ""}
        for k, v in (cfg.get("profili") or {}).items():
            if not RE_ID.match(str(k)) or not isinstance(v, dict):
                raise ErroreMappa(f"profilo non valido: {k!r}")
            disp[k] = str(v.get("descrizione", "")).strip()[:200]
        richiesti = [str(x).strip() for x in profili if str(x).strip()]
        for x in richiesti:
            if x not in disp:
                raise ErroreMappa(f"profilo {x!r} non definito in 'profili'")
        attivi = (PROFILO_GENERALE,) + tuple(sorted(set(richiesti) - {PROFILO_GENERALE}))
        cats = dict(CATEGORIE_BASE)
        for k, v in (cfg.get("categorie") or {}).items():
            if not RE_ID.match(k) or not isinstance(v, str) or not v.strip():
                raise ErroreMappa(f"categoria non valida: {k!r}")
            cats[k] = v.strip()[:60]
        ver = str(cfg.get("versione", "senza_versione"))[:40]
        if len(attivi) > 1:
            ver = (ver + "+" + "+".join(attivi[1:]))[:40]
        m = cls(versione=ver, categorie=cats, profili=disp, profili_attivi=attivi)
        for exe, d in (cfg.get("applicazioni") or {}).items():
            if not isinstance(d, dict):
                raise ErroreMappa(f"{exe}: atteso un oggetto {{id, etichetta, categoria}}")
            aid, et, cat = d.get("id", ""), str(d.get("etichetta", "")).strip()[:60], d.get("categoria", "")
            if not RE_ID.match(str(aid)) or aid == APP_SCONOSCIUTA[0]:
                raise ErroreMappa(f"{exe}: id non valido ({aid!r}); ammessi a-z0-9_")
            if cat not in cats:
                raise ErroreMappa(f"{exe}: categoria {cat!r} non definita in 'categorie'")
            if not et:
                raise ErroreMappa(f"{exe}: etichetta obbligatoria")
            if aid in m.per_id and m.per_id[aid] != (et, cat):
                raise ErroreMappa(f"{exe}: l'id {aid!r} ha già un'etichetta o una categoria diversa")
            m.per_exe[exe.strip().upper()] = (aid, et, cat)
            m.per_id[aid] = (et, cat)
        for dom, motivo in (cfg.get("esclusi") or {}).items():
            dom = str(dom).strip().lower()
            if not (RE_DOMINIO.match(dom) or RE_IPV4.match(dom)) or not str(motivo).strip():
                raise ErroreMappa(f"esclusi: voce non valida {dom!r} (serve il dominio e il motivo)")
            m.esclusi[dom] = str(motivo).strip()[:200]
        tutti = {}
        for sid, d in (cfg.get("siti") or {}).items():
            if not RE_ID.match(sid) or not isinstance(d, dict):
                raise ErroreMappa(f"sito non valido: {sid!r}")
            cat = d.get("categoria", "web_generico")
            if cat not in cats:
                raise ErroreMappa(f"sito {sid}: categoria {cat!r} non definita")
            prof = d.get("profilo", PROFILO_GENERALE)
            if prof not in disp:
                raise ErroreMappa(f"sito {sid}: profilo {prof!r} non definito in 'profili'")
            doms = []
            for dom in d.get("domini", []) or []:
                dom = str(dom).strip().lower()
                if not (RE_DOMINIO.match(dom) or RE_IPV4.match(dom)):
                    raise ErroreMappa(f"sito {sid}: dominio non valido {dom!r} (solo il dominio o un IPv4, senza https://, porta né percorso)")
                if m.escluso(dom):
                    raise ErroreMappa(f"sito {sid}: il dominio {dom} è nell'elenco 'esclusi' ({m.escluso(dom)})")
                if dom in tutti and tutti[dom] != sid:
                    raise ErroreMappa(f"dominio {dom} assegnato a due siti")
                tutti[dom] = sid
                doms.append(dom)
            if prof not in attivi:
                continue                      # profilo non attivo: il sito resta «navigazione web»
            m.siti[sid] = (str(d.get("etichetta", sid)).strip()[:60] or sid, cat)
            for dom in doms:
                m.per_dominio[dom] = sid
        return m

    @classmethod
    def da_file(cls, path: str, profili=()) -> "Mappa":
        try:
            with open(path, encoding="utf-8") as f:
                return cls.da_dict(json.load(f), profili)
        except json.JSONDecodeError as e:
            raise ErroreMappa(f"{path}: JSON non valido ({e.msg})") from e

    @classmethod
    def predefinita(cls, profili=()) -> "Mappa":
        return cls.da_file(PERCORSO_PREDEFINITO, profili) if os.path.exists(PERCORSO_PREDEFINITO) else cls()
