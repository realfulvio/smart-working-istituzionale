"""Genera i 3 giorni sintetici di esempio (raw.jsonl + revisione.jsonl) e le uscite dell'aggregatore.

revisione.jsonl contiene ciò che dichiara il dipendente: attività manuali, segnalazioni di dato apparentemente errato.
rivisto.json contiene anche la sintesi della giornata (M5) generata con il testo standard deterministico e confermata.

  python examples/genera_esempi.py

Dati INVENTATI. Gli esempi sono sigillati con una chiave di prova generata al momento in una cartella temporanea
(o indicata con --chiave) e MAI inclusa nel repository: in examples/chiavi_registrate/ resta solo la chiave pubblica,
sufficiente a verificare i sigilli. Rigenerando gli esempi si genera una chiave nuova e il file pubblico cambia.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from aggregatore import mappa  # noqa: E402
from aggregatore.cli import main  # noqa: E402
from redattore.__main__ import main as redattore  # noqa: E402

OFF = "+02:00"
# gli esempi usano la mappatura di PROVA (un sito inventato): quella predefinita del programma ha i siti vuoti
mappa.PERCORSO_PREDEFINITO = os.path.join(os.path.dirname(HERE), "tests", "dati", "applicazioni_prova.json")


def ts(g, hm, s="00"):
    return f"{g}T{hm}:{s}{OFF}"


def meta(g, postazione, cop, stato_iniziale="sconosciuta", modalita="consuntivo"):
    return {"tipo": "meta", "giorno": g, "fuso": "Europe/Rome", "modalita": modalita,
            "dipendente": {"nome": "Rossi Maria (ESEMPIO)", "account": "ENTE\\esempio", "ufficio": "Ufficio Tributi"},
            "postazione": postazione, "versioni": {"collector": "consuntivo-v3-lettori"},
            "presa_visione": {"versione": "2026-10-01.1", "data": "2026-10-01T08:10:00+02:00"},
            "copertura_fonti": cop, "stato_iniziale_sessione": stato_iniziale}


def app_run(g, app, start, end, step_min=7, exe=False):
    """exe=True: l'evento porta il nome dell'eseguibile (come lo darà il collector), risolto con la mappatura."""
    h, m = map(int, start.split(":")); eh, em = map(int, end.split(":"))
    t, out = h * 60 + m, []
    while t < eh * 60 + em:
        out.append({"tipo": "app", "ts": ts(g, f"{t // 60:02d}:{t % 60:02d}"), ("exe" if exe else "app"): app})
        t += step_min
    return out


def rete_run(g, start, end, step_min=15, ops=3):
    h, m = map(int, start.split(":")); eh, em = map(int, end.split(":"))
    t, out = h * 60 + m, []
    while t < eh * 60 + em:
        out.append({"tipo": "rete", "ts": ts(g, f"{t // 60:02d}:{t % 60:02d}"), "operazioni": ops + (t // 15) % 4})
        t += step_min
    return out


def halley_run(g, start, end, step_min=7):
    """Halley è un servizio web (gestionale.esempio.test): il collector vede il browser e il dominio in whitelist."""
    out = []
    for e in app_run(g, "MSEDGE.EXE", start, end, step_min, exe=True):
        out += [e, {"tipo": "web", "ts": e["ts"], "dominio": "gestionale.esempio.test"}]
    return out


def giorno1():
    """Giornata di esempio con attività d'ufficio e Halley."""
    g = "2026-10-05"
    ev = [meta(g, {"host": "PC-TRIB-03", "tipo": "fisica", "ram_gb": 15.8},
               {"sessione": "completa", "app": "parziale", "attivita": "non_installato",
                "rete": "completa", "browser": "parziale"}, "chiusa"),
          {"tipo": "sessione", "ts": ts(g, "07:58"), "evento": "accesso"}]
    ev += app_run(g, "OUTLOOK.EXE", "08:00", "08:40", 10, exe=True)
    ev += halley_run(g, "08:35", "10:30")
    ev += [r for r in rete_run(g, "07:45", "14:15") if not r["ts"].startswith(g + "T12:3")]  # rete: solo conteggi
    ev += [{"tipo": "web", "ts": ts(g, "09:12"), "dominio": "www.agenziaentrate.gov.it"},
           {"tipo": "web", "ts": ts(g, "09:20"), "dominio": "www.agenziaentrate.gov.it"},
           {"tipo": "web", "ts": ts(g, "12:12"), "dominio": "www.esempio-non-in-elenco.it"},   # fuori whitelist: generico
           {"tipo": "app", "ts": ts(g, "12:50"), "exe": "C:\\Programmi\\Gest\\GESTPRATICHE.EXE"}]  # non ammesso (vecchio grezzo): solo attività
    ev += [{"tipo": "sessione", "ts": ts(g, "10:31"), "evento": "blocco"},
           {"tipo": "sessione", "ts": ts(g, "10:47"), "evento": "sblocco"}]
    ev += app_run(g, "WINWORD.EXE", "10:50", "11:00", 6, exe=True)
    # 11:00-11:45 nessuna traccia sul PC: riunione dichiarata
    ev += app_run(g, "EXCEL.EXE", "11:47", "12:29", 9, exe=True)
    ev += [{"tipo": "app", "ts": ts(g, "12:05"), "exe": "WINWORD.EXE"}, {"tipo": "app", "ts": ts(g, "12:20"), "exe": "WINWORD.EXE"}]
    ev += [{"tipo": "raccolta", "ts": ts(g, "12:30"), "evento": "pausa"},           # «Pausa raccolta»
           {"tipo": "raccolta", "ts": ts(g, "12:45"), "evento": "ripresa"}]
    ev += halley_run(g, "12:46", "13:29")
    ev += [{"tipo": "sessione", "ts": ts(g, "14:02"), "evento": "chiusura"},
           {"tipo": "sessione", "ts": ts(g, "14:03"), "evento": "spegnimento"}]
    man = [{"tipo": "manuale", "inizio": ts(g, "11:00"), "fine": ts(g, "11:45"), "categoria": "riunione",
            "descrizione": "Riunione di servizio sulle scadenze IMU"},
           {"tipo": "manuale", "inizio": ts(g, "13:40"), "fine": ts(g, "14:00"), "categoria": "telefonata",
            "descrizione": "Chiarimenti a un contribuente sulla TARI"},
           {"tipo": "segnalazione", "campo": "stato", "fascia": 42,
            "nota": "Stavo consultando una pratica su Halley: probabilmente lo sblocco non è stato registrato."}]
    return "01_giornata_ufficio", ev, man, "Mattinata con molte richieste allo sportello telefonico."


def giorno2():
    g = "2026-10-06"
    ev = [meta(g, {"host": "PC-TECN-01", "tipo": "portatile", "ram_gb": 8},
               {"sessione": "completa", "app": "parziale", "attivita": "non_installato",
                "rete": "non_installato", "browser": "non_installato"}, "chiusa"),
          {"tipo": "sessione", "ts": ts(g, "08:15"), "evento": "accesso"}]
    ev += app_run(g, "outlook", "08:16", "08:50", 8)
    ev += app_run(g, "pdf", "08:50", "09:25", 12)
    # 09:30-10:45 nessuna traccia (sopralluogo, PC acceso e non bloccato) -> nessuna_attivita_informatica_rilevata
    ev += app_run(g, "word", "10:50", "12:55", 10)
    ev += [{"tipo": "sessione", "ts": ts(g, "13:02"), "evento": "blocco"},
           {"tipo": "sessione", "ts": ts(g, "13:05"), "evento": "sospensione"},
           {"tipo": "sessione", "ts": ts(g, "13:58"), "evento": "ripresa"},
           {"tipo": "sessione", "ts": ts(g, "14:00"), "evento": "sblocco"}]
    ev += app_run(g, "excel", "14:05", "14:40", 10)
    # 14:40-16:00 lungo vuoto senza blocco
    ev += app_run(g, "browser", "16:00", "16:30", 10)
    ev += [{"tipo": "sessione", "ts": ts(g, "16:41"), "evento": "spegnimento"}]
    man = [{"tipo": "manuale", "inizio": ts(g, "09:30"), "fine": ts(g, "10:45"), "categoria": "sopralluogo",
            "descrizione": "Sopralluogo cantiere scuola primaria"},
           {"tipo": "manuale", "inizio": ts(g, "14:45"), "fine": ts(g, "15:45"), "categoria": "cartaceo",
            "descrizione": "Revisione elaborati cartacei"},
           {"tipo": "segnalazione", "campo": "altro", "nota": "Due risposte inviate dalla webmail nel pomeriggio non "
                                                             "risultano nel resoconto."}]
    return "02_pause_lunghe_pranzo", ev, man, "Pausa pranzo con PC in sospensione; mattina in cantiere."


def giorno3():
    g = "2026-10-07"
    ev = [meta(g, {"host": "VD-0042", "tipo": "vdi", "ram_gb": 8},
               {"sessione": "parziale", "app": "parziale", "attivita": "non_installato",
                "rete": "non_installato", "browser": "non_installato"}),
          # sessione VDI lasciata disconnessa la sera prima: a cavallo della mezzanotte
          {"tipo": "sessione", "ts": "2026-10-06T18:10:00+02:00", "evento": "disconnessione"},
          {"tipo": "sessione", "ts": ts(g, "08:05"), "evento": "riconnessione"}]
    ev += halley_run(g, "08:06", "09:05", 6)
    ev += [{"tipo": "sessione", "ts": ts(g, "09:10"), "evento": "blocco"}]
    # nessun «sblocco» registrato (registro Security non leggibile) ma attività alle 09:40 -> sblocco implicito
    ev += halley_run(g, "09:40", "10:25", 6)
    ev += [{"tipo": "sessione", "ts": ts(g, "10:30"), "evento": "disconnessione"},
           {"tipo": "sessione", "ts": ts(g, "10:52"), "evento": "riconnessione"}]
    ev += app_run(g, "word", "10:55", "11:30", 8)
    ev += [{"tipo": "sessione", "ts": ts(g, "11:31"), "evento": "disconnessione"},
           {"tipo": "sessione", "ts": ts(g, "11:33"), "evento": "riconnessione"},
           {"tipo": "orologio", "ts": ts(g, "11:34"), "delta_s": -300}]
    ev += halley_run(g, "11:35", "12:30", 6)
    ev += [{"tipo": "app", "ts": ts(g, "11:41"), "exe": "MSEDGE.EXE"},       # duplicato
           {"tipo": "app", "ts": ts(g, "11:50"), "app": "word", "file": "C:\\Users\\x\\segreto.docx"},  # campo vietato
           {"tipo": "app", "ts": ts(g, "12:00"), "app": "Relazione finale.docx"},                       # nome non conforme
           {"tipo": "sessione", "ts": ts(g, "12:35"), "evento": "disconnessione"},
           {"tipo": "sessione", "ts": ts(g, "14:30"), "evento": "riconnessione"}]
    ev += halley_run(g, "14:31", "15:20", 6)
    ev += [{"tipo": "sessione", "ts": ts(g, "15:25"), "evento": "disconnessione"},
           {"tipo": "app", "ts": "2026-10-08T08:00:00+02:00", "exe": "MSEDGE.EXE"}]    # giorno successivo: ignorato
    man = [{"tipo": "manuale", "inizio": ts(g, "12:40"), "fine": ts(g, "13:30"), "categoria": "formazione",
            "descrizione": "Webinar ANUSCA (da cellulare)"},
           {"tipo": "manuale", "inizio": ts(g, "15:00"), "fine": ts(g, "16:00"), "categoria": "altro",
            "descrizione": "Archiviazione pratiche"},
           {"tipo": "segnalazione", "campo": "stato", "dalle": "09:15", "alle": "09:45",
            "nota": "Risulta sessione bloccata, ma stavo consultando una pratica su Halley: la VDI non ha registrato lo "
                    "sblocco."}]
    return "03_vdi_disconnessioni", ev, man, "VDI lenta, molte disconnessioni."


def write_jsonl(p, recs):
    with open(p, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chiave", help="cartella della chiave di prova (predefinita: una cartella temporanea, poi eliminata)")
    args = ap.parse_args()
    # identità FITTIZIA nella chiave e nei sigilli (mai l'account o il PC di chi esegue lo script)
    os.environ.update({"USERNAME": "esempio", "USER": "esempio", "USERDOMAIN": "", "COMPUTERNAME": "PC-ESEMPIO"})
    tmp = None if args.chiave else tempfile.mkdtemp(prefix="rsw_chiave_esempio_")
    key = args.chiave or tmp
    for fn, adesso in ((giorno1, "2026-10-05T14:10:00+02:00"), (giorno2, "2026-10-06T16:50:00+02:00"),
                       (giorno3, "2026-10-07T16:05:00+02:00")):
        nome, ev, man, oss = fn()
        d = os.path.join(HERE, nome)
        os.makedirs(d, exist_ok=True)
        write_jsonl(os.path.join(d, "raw.jsonl"), ev)
        write_jsonl(os.path.join(d, "revisione.jsonl"), man)
        rev_t = adesso[:14] + "30:00" + adesso[-6:]   # stessa ora, minuto 30
        assert main(["aggrega", os.path.join(d, "raw.jsonl"), "-o", os.path.join(d, "giorno.json"), "--chiave", key, "--adesso", adesso]) == 0
        assert main(["rivedi", os.path.join(d, "giorno.json"), "--revisione", os.path.join(d, "revisione.jsonl"),
                     "--osservazioni", oss, "-o", os.path.join(d, "rivisto.json")]) == 0
        # «Genera resoconto» con il testo standard (deterministico, senza modello) e «Ho verificato la sintesi»
        riv = os.path.join(d, "rivisto.json")
        sint_t = adesso[:14] + "20:00" + adesso[-6:]
        assert redattore(["sintetizza", riv, "-o", riv, "--motore", "standard", "--adesso", sint_t]) == 0
        assert redattore(["conferma", riv, "-o", riv, "--adesso", adesso[:14] + "25:00" + adesso[-6:]]) == 0
        assert main(["sigilla-finale", os.path.join(d, "rivisto.json"), "--chiave", key, "-o", os.path.join(d, "finale.json"),
                     "--adesso", rev_t]) == 0
    # registro delle chiavi pubbliche: resta SOLO la chiave pubblica (mai quella privata)
    reg = os.path.join(HERE, "chiavi_registrate")
    for vecchio in glob.glob(os.path.join(reg, "esempio_*.json")):
        os.remove(vecchio)
    pub = json.load(open(os.path.join(key, "pubblica.json"), encoding="utf-8"))
    os.makedirs(reg, exist_ok=True)
    shutil.copy(os.path.join(key, "pubblica.json"),
                os.path.join(reg, f"esempio_{pub['pc']}_{pub['impronta'].replace(' ', '')[:8]}.json"))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
