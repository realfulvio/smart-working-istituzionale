"""Conteggio delle operazioni SMB della sola sessione dell'utente (M8). Logica indipendente da Windows.

Problema (M3–M7): «SMB Client Shares(_Total)» somma TUTTO il PC: anche le letture di SYSVOL/NETLOGON dei criteri di
gruppo, i servizi di sistema e le altre sessioni. Senza diritti di amministratore non esiste un contatore per
sessione (ETW SMBClient e Get-SmbConnection richiedono l'amministratore: sulla postazione di prova «Accesso negato»).

Soluzione adottata, verificata in sola lettura sulla postazione di prova il 05/10/2026:
- i contatori PDH «SMB Client Shares» hanno un'istanza per condivisione (\\\\server\\condivisione);
- le connessioni di rete della sessione di accesso dell'utente si leggono con WNetGetConnection (unità mappate);
- si sommano solo le istanze che corrispondono alle unità dell'utente, escluse SYSVOL/NETLOGON/IPC$;
- si contano richieste di dati + richieste di metadati (elenco cartelle, apertura): le sole richieste di dati
  restano a 0 se l'utente sfoglia senza aprire file (era lo «0 richieste» del pilota M3);
- se nel PC ci sono più sessioni utente (attive o disconnesse) il dato non è attribuibile: «dato non disponibile».
Limiti dichiarati: accessi a percorsi UNC senza unità mappata non contati (sottostima); accessi di processi di
sistema alle STESSE condivisioni dell'utente contati (nella VDI a sessione singola sono marginali)."""
from __future__ import annotations

ESCLUSE = ("sysvol", "netlogon", "ipc$")
# stati WTS di una sessione con un utente collegato (WTSActive=0, WTSDisconnected=4); la sessione 0 è dei servizi
STATI_UTENTE = (0, 4)


def _parti(unc: str) -> tuple[str, str] | None:
    p = unc.strip().lstrip("\\").lower().split("\\")
    if len(p) < 2 or not p[0] or not p[1]:
        return None
    return p[0].split(".")[0], p[1]          # server senza dominio (l'istanza può avere il nome completo) + condivisione


def istanze_utente(istanze, connessioni) -> set[str]:
    """Istanze PDH (\\\\server\\condivisione) che corrispondono alle connessioni della sessione dell'utente."""
    mie = {x for x in (_parti(c) for c in connessioni) if x}
    out = set()
    for ist in istanze:
        p = _parti(ist)
        if p and p[1] not in ESCLUSE and p in mie:
            out.add(ist)
    return out


def sessioni_utente(sessioni) -> int:
    """Numero di sessioni con un utente collegato, da coppie (id, stato WTS)."""
    return sum(1 for sid, stato in sessioni if sid != 0 and stato in STATI_UTENTE)


class Accumulatore:
    """Totale cumulativo e monotono delle operazioni sulle condivisioni dell'utente.

    I contatori PDH per istanza ripartono da zero quando una connessione viene ricreata e un'istanza può comparire
    durante la giornata: si sommano solo gli incrementi positivi di ogni istanza rispetto alla lettura precedente."""

    def __init__(self):
        self.prec: dict[str, int] = {}
        self.totale = 0

    def aggiorna(self, valori: dict[str, int], connessioni, sessioni) -> int | None:
        if sessioni_utente(sessioni) != 1:
            self.prec = {}
            return None                                  # non attribuibile alla sola sessione: dato non disponibile
        mie = istanze_utente(valori, connessioni)
        nuovi = {}
        for ist in mie:
            v = int(valori[ist])
            if ist in self.prec and v >= self.prec[ist]:
                self.totale += v - self.prec[ist]
            nuovi[ist] = v
        self.prec = nuovi
        return self.totale
