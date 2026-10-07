"""Logica del collector indipendente da Windows (testabile ovunque).

Il ciclo principale chiama ``tick`` ogni pochi secondi con: l'istante, il contatore dell'ultimo input
(GetLastInputInfo, in millisecondi dall'avvio del sistema) e una funzione che restituisce l'eseguibile in primo piano.
Le notifiche di sessione arrivano con ``sessione``; il contatore SMB, se disponibile, con ``rete``.

Regole (minimizzazione):
- per ogni fascia di 15 minuti al più **un** evento ``attivita`` (la prima volta che si vede input nella fascia);
- l'eseguibile in primo piano si legge **solo quando c'è stato input** dall'ultimo controllo, e ogni eseguibile si
  registra al più una volta per fascia (niente durate, niente sequenze fini);
- si registrano solo gli eseguibili ammessi (elenco del CED in config/applicazioni.json): gli altri non lasciano
  traccia nel registro (bonifica B5), l'input resta contato come «attività» della fascia;
- con sessione bloccata o disconnessa non si registrano né attività né applicazioni;
- la rete è un solo numero per fascia (richieste SMB del client), mai destinazioni o file.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from aggregatore.configurazione import FASCIA_S

# notifiche WM_WTSSESSION_CHANGE (wParam) -> evento di sessione del formato M1
WTS_EVENTI = {
    0x1: "riconnessione",   # WTS_CONSOLE_CONNECT
    0x2: "disconnessione",  # WTS_CONSOLE_DISCONNECT
    0x3: "riconnessione",   # WTS_REMOTE_CONNECT
    0x4: "disconnessione",  # WTS_REMOTE_DISCONNECT
    0x5: "accesso",         # WTS_SESSION_LOGON
    0x6: "chiusura",        # WTS_SESSION_LOGOFF
    0x7: "blocco",          # WTS_SESSION_LOCK
    0x8: "sblocco",         # WTS_SESSION_UNLOCK
}
# WM_POWERBROADCAST (wParam)
POWER_EVENTI = {0x4: "sospensione", 0x7: "ripresa", 0x12: "ripresa"}
NON_ATTIVA = {"blocco": True, "disconnessione": True, "sospensione": True, "chiusura": True, "spegnimento": True,
              "sblocco": False, "riconnessione": False, "accesso": False, "ripresa": False}


def inizio_fascia(t: dt.datetime) -> dt.datetime:
    """Inizio della fascia in tempo assoluto (le fasce sono di 15 minuti anche nei giorni del cambio d'ora)."""
    epoch = int(t.timestamp())
    return dt.datetime.fromtimestamp(epoch - epoch % FASCIA_S, t.tzinfo)


class Campionatore:
    def __init__(self, scrivi: Callable[..., dict], ammessi=None):
        self.scrivi = scrivi
        self.ammessi = None if ammessi is None else frozenset(x.upper() for x in ammessi)   # None: solo nei test
        self.fascia: Optional[dt.datetime] = None
        self.input_visto = False
        self.app_viste: set[str] = set()
        self.ultimo_input: Optional[int] = None
        self.non_attiva = False
        self.rete_prec: Optional[int] = None
        self.rete_fascia = 0
        self.ultimo_tick: Optional[dt.datetime] = None
        self.conteggi = {"attivita": 0, "app": 0, "sessione": 0, "rete": 0, "orologio": 0}

    # ---------------------------------------------------------------------------------------- fasce
    def _cambia_fascia(self, now: dt.datetime):
        f = inizio_fascia(now)
        if self.fascia is not None and f != self.fascia:
            self.chiudi_fascia()
        if f != self.fascia:
            self.fascia, self.input_visto, self.app_viste = f, False, set()

    def chiudi_fascia(self):
        """Scrive il conteggio di rete della fascia corrente (con l'istante dell'ultimo controllo nella fascia)."""
        if self.rete_fascia > 0 and self.ultimo_tick is not None:
            self.scrivi("rete", self.ultimo_tick, operazioni=int(self.rete_fascia))
            self.conteggi["rete"] += 1
        self.rete_fascia = 0

    # ------------------------------------------------------------------------------------------ tick
    def tick(self, now: dt.datetime, ultimo_input: Optional[int], exe_primo_piano: Callable[[], str] = lambda: ""):
        self._cambia_fascia(now)
        self.ultimo_tick = now
        nuovo_input = (ultimo_input is not None and self.ultimo_input is not None and ultimo_input != self.ultimo_input)
        self.ultimo_input = ultimo_input
        if self.non_attiva or not nuovo_input:
            return
        if not self.input_visto:
            self.scrivi("attivita", now)
            self.input_visto = True
            self.conteggi["attivita"] += 1
        exe = (exe_primo_piano() or "").strip().upper()
        if exe and self.ammessi is not None and exe not in self.ammessi:
            self.conteggi["app_non_ammesse"] = self.conteggi.get("app_non_ammesse", 0) + 1   # solo il numero
            return
        if exe and exe not in self.app_viste:
            self.app_viste.add(exe)
            try:
                self.scrivi("app", now, exe=exe)
                self.conteggi["app"] += 1
            except ValueError:                 # nome non conforme: non si registra (mai un percorso)
                self.conteggi["app_scartate"] = self.conteggi.get("app_scartate", 0) + 1

    # -------------------------------------------------------------------------------------- sessione
    def sessione(self, now: dt.datetime, evento: str):
        if evento not in NON_ATTIVA:
            return
        self._cambia_fascia(now)
        self.non_attiva = NON_ATTIVA[evento]
        self.scrivi("sessione", now, evento=evento)
        self.conteggi["sessione"] += 1

    def wts(self, now: dt.datetime, codice: int):
        ev = WTS_EVENTI.get(int(codice))
        if ev:
            self.sessione(now, ev)

    def power(self, now: dt.datetime, codice: int):
        ev = POWER_EVENTI.get(int(codice))
        if ev:
            self.sessione(now, ev)

    # ------------------------------------------------------------------------------------------ rete
    def rete(self, contatore: Optional[int]):
        """Contatore cumulativo delle richieste SMB: si somma la differenza alla fascia corrente."""
        if contatore is None:
            return
        if self.rete_prec is not None and contatore >= self.rete_prec:
            self.rete_fascia += contatore - self.rete_prec
        self.rete_prec = contatore

    # -------------------------------------------------------------------------------------- orologio
    def orologio(self, now: dt.datetime, delta_s: int):
        if abs(int(delta_s)) >= 1:
            self.scrivi("orologio", now, delta_s=int(delta_s))
            self.conteggi["orologio"] += 1
