"""M8 – contatore SMB della sola sessione dell'utente (logica indipendente da Windows)."""
from collector.campionatore import Campionatore
from collector.smb import Accumulatore, istanze_utente, sessioni_utente

CONN = [r"\\srv01\Dati", r"\\srv02.ente.local\Pubblica"]
SESS = [(0, 4), (1, 0), (65536, 6)]          # servizi, console attiva, listener RDP (come sulla postazione di prova)


def test_istanze_solo_unita_dell_utente():
    ist = [r"\\srv01.ente.local\dati", r"\\srv02\pubblica", r"\\dc01.ente.local\SYSVOL", r"\\dc01\NETLOGON",
           r"\\srv01\IPC$", r"\\srv03\altro", "_Total", "", r"\\srv01"]
    assert istanze_utente(ist, CONN) == {r"\\srv01.ente.local\dati", r"\\srv02\pubblica"}
    assert istanze_utente(ist, []) == set()
    assert istanze_utente(ist, [r"\\dc01\sysvol"]) == set()      # SYSVOL esclusa anche se mappata


def test_sessioni():
    assert sessioni_utente(SESS) == 1
    assert sessioni_utente(SESS + [(2, 4)]) == 2                    # altra sessione disconnessa
    assert sessioni_utente([(0, 4)]) == 0


def test_accumulatore_somma_solo_incrementi_dell_utente():
    a = Accumulatore()
    v = {r"\\srv01\dati": 10, r"\\dc01\sysvol": 500, "_Total": 510}
    assert a.aggiorna(v, CONN, SESS) == 0                          # prima lettura: riferimento
    v = {r"\\srv01\dati": 13, r"\\dc01\sysvol": 900, "_Total": 913}
    assert a.aggiorna(v, CONN, SESS) == 3                          # i criteri di gruppo non contano
    v = {r"\\srv01\dati": 2, r"\\srv02\pubblica": 7, "_Total": 9}  # connessione ricreata + nuova unità
    assert a.aggiorna(v, CONN, SESS) == 3
    v = {r"\\srv01\dati": 5, r"\\srv02\pubblica": 8}
    assert a.aggiorna(v, CONN, SESS) == 7


def test_piu_sessioni_dato_non_disponibile():
    a = Accumulatore()
    assert a.aggiorna({r"\\srv01\dati": 1}, CONN, SESS) == 0
    assert a.aggiorna({r"\\srv01\dati": 50}, CONN, SESS + [(2, 0)]) is None
    assert a.aggiorna({r"\\srv01\dati": 60}, CONN, SESS) == 0      # si riparte dal nuovo riferimento


def test_campionatore_ignora_none():
    righe = []
    c = Campionatore(lambda *a, **k: righe.append((a, k)))
    for x in (0, None, 4, None, 6):
        c.rete(x)
    assert c.rete_fascia == 6
