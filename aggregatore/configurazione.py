"""Policy tecnica del CED, condivisa: nessuna opzione amplia la raccolta consentita."""
from __future__ import annotations

import json
from pathlib import Path

PERCORSO = Path(__file__).resolve().parents[1] / "config" / "raccolta.json"
DEFAULT_FASCIA_MIN = 15


def valida_fascia(valore):
    # Divisori dell'ora: stesso ancoraggio a mezzanotte per collector e aggregatore,
    # anche durante il cambio ora. Non consentire granularità più fine del requisito.
    if type(valore) is not int or valore not in (15, 20, 30, 60):
        raise ValueError("durata_fascia_min: scegliere 15, 20, 30 o 60 minuti")
    return valore


def carica(percorso=None):
    try:
        with open(percorso or PERCORSO, encoding="utf-8-sig") as f:
            policy = json.load(f)
    except FileNotFoundError:
        policy = {}
    if not isinstance(policy, dict):
        raise ValueError("La configurazione della raccolta deve essere un oggetto")
    return {"durata_fascia_min": valida_fascia(policy.get("durata_fascia_min", DEFAULT_FASCIA_MIN)),
            # La V1 non abilita sensori sperimentali tramite impostazioni utente.
            "rete_abilitata": False, "halley_abilitato": False,
            "retention_raw_giorni": policy.get("retention_raw_giorni"),
            "retention_da_data": policy.get("retention_da_data")}


FASCIA_MIN = carica()["durata_fascia_min"]
FASCIA_S = FASCIA_MIN * 60
