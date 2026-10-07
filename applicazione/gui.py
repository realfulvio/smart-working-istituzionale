"""Interfaccia dell'applicazione Smart Working Istituzionale (Tk).

Schermate: informativa (primo avvio) · Oggi (da avviare / in corso / in pausa) · Aggiungi attività ·
chiusura e generazione · revisione (dati automatici in sola lettura, «Segnala», attività dichiarate, osservazioni,
sintesi con Modifica/Riscrivi, «Ho verificato la sintesi» obbligatorio) · conferma (PDF salvato) ·
giornata precedente non chiusa · Resoconti salvati · Aiuto · Informazioni («i»).
Le operazioni lunghe (chiusura, generazione) girano in un thread: l'interfaccia resta reattiva.
"""
from __future__ import annotations

import datetime as dt
import gc
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

from resoconto import VERSIONE_APP, ente
from resoconto.edizione import identita
from resoconto.formati import CAMPI_SEGNALAZIONE, COLORI_STATO, MANUALI, ST_LAB, Giornata, avviso_leggibile, data_lunga

from . import tema
from .movimento import Movimento, progresso, mescola, sigillo
import math
from .servizio import (MAX_DESCRIZIONE, MAX_NOTA, MAX_OSSERVAZIONI, MAX_RISCRITTURE, VERSIONE_INFORMATIVA, ErroreApp,
                       Servizio)
from .tema import (C, F, Bottone, Casella, Scheda, Scorrevole, TestoLimitato, badge, barra_giornata, etichetta, legenda,
                   percorso_breve, px)

_ENTE = ente.carica()
NOME_ENTE = _ENTE["nome"]
TITOLO = f"Resoconto lavoro agile — {NOME_ENTE}"
ASSISTENZA = _ENTE["assistenza"] or "Sistemi Informativi dell'Ente"
TERZE_PARTI = [("Python 3.13 · Tcl/Tk", "PSF-2.0 · Tcl/Tk"), ("cryptography (firma dei sigilli)", "Apache-2.0 / BSD-3"),
               ("cffi · pycparser", "MIT-0 · BSD-3-Clause"), ("jsonschema · attrs · referencing · rpds-py", "MIT"),
               ("ReportLab · pypdf (PDF)", "BSD-3-Clause"), ("Pillow · charset-normalizer", "MIT-CMU · MIT"),
               ("pywin32 (protezione della chiave)", "PSF-2.0"), ("llama.cpp (assistente locale)", "MIT"),
               ("Modelli Qwen3-1.7B / Qwen3-4B", "Apache-2.0"), ("Titillium Web · Roboto Mono", "OFL-1.1")]
# Informativa breve del primo avvio, modalità «collector» (predefinita dal 06/10/2026). Stessi contenuti di
# tools/pacchetto/setup/informativa_breve.rtf: se cambia la raccolta vanno aggiornati entrambi.
INFORMATIVA_COLLECTOR = [
    "Solo a giornata avviata, escluse le pause",
    "Accesso, blocco, sblocco e disconnessione, con l'ora",
    "Per fascia configurata: attività sì/no e programmi dell'elenco del CED (es. «Microsoft Word»)",
    "Rete e integrazione Halley disabilitate"]
INFORMATIVA_WEB = "Browser solo come «Web»"
INFORMATIVA_HALLEY = "Browser come «Web»; Halley solo come nome"
INFORMATIVA_MAI = [
    "Tasti, testo scritto, movimenti del mouse",
    "Schermate, titoli delle finestre, nomi dei file",
    "La posta: né quante mail, né testo, oggetto o destinatari",
    "Indirizzi dei siti, cronologia, registro eventi",
    "Programmi fuori dall'elenco del CED"]


def iniziali(nome: str) -> str:
    p = [x for x in (nome or "").replace("(", " ").split() if x[:1].isalpha() and x.upper() != "ESEMPIO)"
         and x.upper() != "ESEMPIO"]
    return ((p[0][0] + (p[1][0] if len(p) > 1 else "")) if p else "?").upper()


def _env_senza_percorsi_app() -> dict:
    """PATH senza cartelle dell'app/_internal/_MEIPASS (B7 ALFA2: Acrobat caricava VCRUNTIME da lì)."""
    env = dict(os.environ)
    togli = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        togli.extend([exe_dir, os.path.join(exe_dir, "_internal")])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            togli.append(meipass)
    norm = {os.path.normcase(os.path.abspath(p)) for p in togli if p}
    parti = []
    for p in (env.get("PATH") or "").split(os.pathsep):
        if not p:
            continue
        try:
            ap = os.path.normcase(os.path.abspath(p))
        except (OSError, ValueError):
            parti.append(p)
            continue
        if ap in norm:
            continue
        if any(ap == n or ap.startswith(n + os.sep) for n in norm):
            continue
        parti.append(p)
    env["PATH"] = os.pathsep.join(parti)
    for k in list(env):
        ku = k.upper()
        if ku.startswith("_PYI") or ku in ("_MEIPASS", "PYTHONPATH", "PYTHONHOME"):
            env.pop(k, None)
    return env


def apri_file(path: str, cartella: bool = False):
    try:
        if sys.platform == "win32":
            if cartella:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                # B7 ALFA2: os.startfile(cwd=cartella PDF) non bastava — Acrobat caricava ancora
                # VCRUNTIME140.dll da …\RendicontoSW\_internal. Si apre tramite explorer.exe
                # (genitore ≠ nostra app) con PATH ripulito dalle cartelle di installazione.
                path = os.path.abspath(path)
                pdf_dir = os.path.dirname(path)
                env = _env_senza_percorsi_app()
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetDllDirectoryW("")
                except (AttributeError, OSError):
                    pass
                subprocess.Popen(  # noqa: S603 - explorer apre il file con l'associazione di sistema
                    ["explorer.exe", os.path.normpath(path)],
                    cwd=pdf_dir,
                    env=env,
                    close_fds=True,
                )
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) if cartella else path])
    except OSError:
        pass


def _icona_doc(master):
    bg = master.cget("bg")
    cv = tk.Canvas(master, width=px(18), height=px(22), bg=bg, highlightthickness=0)
    cv.create_polygon(px(2), px(1), px(12), px(1), px(17), px(6), px(17), px(21), px(2), px(21), fill="white",
                      outline=C["primary"], width=px(1.6))
    cv.create_line(px(12), px(1), px(12), px(6), px(17), px(6), fill=C["primary"], width=px(1.4))
    for y in (10, 13, 16):
        cv.create_line(px(5), px(y), px(14), px(y), fill=C["primary"])
    return cv


def _fasce(n: int) -> str:
    return "1 fascia" if n == 1 else f"{n} fasce"


class App(tk.Tk):
    def __init__(self, servizio: Servizio, dimensione=(1160, 780), scala_test=None):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:   # noqa: BLE001
                pass
        super().__init__()
        self.s = servizio
        tema.carica_font(self)
        if scala_test is not None:
            tema.SCALA = float(scala_test)
        self.movimento = Movimento(self, servizio.imp.get("riduci_animazioni", "sistema"))
        self.title(TITOLO)
        self.configure(bg=C["bg"])
        self.geometry(f"{min(px(dimensione[0]), self.winfo_screenwidth()-40)}x{min(px(dimensione[1]), self.winfo_screenheight()-100)}")
        self.minsize(min(px(1024), self.winfo_screenwidth()-40), min(px(700), self.winfo_screenheight()-100))
        self._icone()
        self.q: queue.Queue = queue.Queue()
        self.after(100, self._coda)
        self.velo = None
        self._occupato = False
        self._verificato_per = None
        self._voce_in_modifica = None
        self.ho_verificato = tk.BooleanVar(value=False)
        self.usa_ai = tk.BooleanVar(value=False)
        self.bind_all("<FocusIn>", lambda e: tema.rendi_visibile(e.widget), add="+")
        self.bind("<Escape>", lambda e: self.chiudi_velo())
        self.bind("<Tab>", self._tab_modale)
        self.bind("<Shift-Tab>", lambda e: self._tab_modale(e, indietro=True))
        self.bind_class("AppModal", "<Tab>", self._tab_modale)
        self.bind_class("AppModal", "<Shift-Tab>", lambda e: self._tab_modale(e, indietro=True))
        self._testata()
        self.piede = tk.Frame(self, bg=C["bg"])
        self.piede.pack(fill="x", side="bottom")
        Bottone(self.piede, "Cosa viene registrato", self.mostra_cosa, "link", dim=12).pack(side="left", padx=px(20))
        pw = tk.Frame(self.piede, bg=C["bg"]); pw.pack(side="right", padx=px(10), pady=(0, px(3)))
        etichetta(pw, identita()["etichetta"] + " · dati locali", 11, colore=C["muted"]).pack(side="left")
        self.corpo = tk.Frame(self, bg=C["bg"])
        self.corpo.pack(fill="both", expand=True)
        self.vai_oggi()
        # Attende il mapping della finestra: after_idle può precederlo su Windows.
        self.after(100, self.mostra_splash)

    def mostra_splash(self):
        if self.movimento.ridotto or self.s.serve_informativa() or not self.winfo_viewable():
            return
        from PIL import Image, ImageTk
        popup = tk.Toplevel(self); popup.movimento=self.movimento; self.splash=popup; popup.overrideredirect(True); popup.configure(bg="white")
        popup.geometry(f"{px(340)}x{px(270)}+{self.winfo_x()+px(360)}+{self.winfo_y()+px(150)}")
        logo = tk.Label(popup, bg="white"); logo.pack(pady=(px(22),px(12)))
        im = Image.open(_ENTE["logo"]).convert("RGBA") if _ENTE["logo"] else None
        etichetta(popup, NOME_ENTE, 17, "bold", colore=C["dark"]).pack()
        etichetta(popup, "Preparazione dell’applicazione…", 13).pack(pady=8)
        bar=progresso(popup,C["primary"],"white");bar.pack_forget()
        def draw(n):
            try:
                popup.attributes("-alpha", min(1,.05+n*1.8))
                if n>.55 and not bar.winfo_manager():bar.pack(fill="x",padx=20,pady=6)
                if im:
                    size=px(76+6*n); thumb=im.copy();thumb.thumbnail((size,size))
                    logo.image=ImageTk.PhotoImage(thumb,master=popup);logo.configure(image=logo.image)
                if n>=1:popup.destroy()
            except tk.TclError:pass
        self.movimento.effetto(popup,draw,.54)

    def destroy(self):
        owners={}
        def collect(w):
            for cmd in getattr(w,"_tclCommands",[]) or []:owners[cmd]=w
            for child in w.winfo_children():collect(child)
        collect(self)
        for callback in self.tk.call("after", "info"):
            script=str(self.tk.call("after","info",callback)[0]).split()[0]
            if script in owners:owners[script].after_cancel(callback)
        self.movimento.timer=None
        super().destroy()

    # ------------------------------------------------------------------------------------- struttura
    def _icone(self):
        self.img_stemma = self.img_stemma_g = None
        try:
            from PIL import Image, ImageTk
            if _ENTE["logo"]:   # logo dell'Ente (config/ente.json): senza logo non si disegna nulla
                im = Image.open(_ENTE["logo"]).convert("RGBA")
                self.img_stemma = ImageTk.PhotoImage(im.resize((px(72), px(72)), Image.LANCZOS), master=self)
                self.img_stemma_g = ImageTk.PhotoImage(im.resize((px(54), px(54)), Image.LANCZOS), master=self)
                self._ico = ImageTk.PhotoImage(im.resize((32, 32), Image.LANCZOS), master=self)
                self.iconphoto(True, self._ico)
        except Exception:   # noqa: BLE001
            pass
        if sys.platform == "win32":
            try:
                self.iconbitmap(default=os.path.join(tema.ASSETS, "rendiconto.ico"))
            except tk.TclError:
                pass

    def _stemma(self, master, grande=False):
        bg = master.cget("bg")
        if not self.img_stemma:
            return tk.Frame(master, bg=bg, width=1, height=1)
        r = px(56 if grande else 48)
        cv = tk.Canvas(master, width=r, height=r, bg=bg, highlightthickness=0)
        cv.create_oval(1, 1, r - 1, r - 1, fill="white", outline=C["line"] if grande else "white")
        img = self.img_stemma_g if grande else self.img_stemma
        if img:
            cv.create_image(r // 2, r // 2, image=img)
        return cv

    def _testata(self):
        t = tk.Frame(self, bg=C["primary"], height=px(112))
        t.pack(fill="x"); t.pack_propagate(False)
        tk.Frame(self, bg=C["gold"], height=px(3)).pack(fill="x")
        self._stemma(t).pack(side="left", padx=(px(28), px(12)))
        tt = tk.Frame(t, bg=C["primary"]); tt.pack(side="left")
        etichetta(tt, NOME_ENTE, 18, colore=C["tint"]).pack(anchor="w")
        etichetta(tt, "Resoconto lavoro agile", 27, "bold", colore="white").pack(anchor="w")
        self.schede = {}
        nav = tk.Frame(self, bg=C["primary"], height=px(42)); nav.pack(fill="x"); nav.pack_propagate(False)
        for k, testo, cmd in (("oggi", "Oggi", self.vai_oggi), ("salvati", "Resoconti salvati", self.vai_salvati),
                              ("aiuto", "Aiuto", self.vai_aiuto), ("impostazioni", "Impostazioni", self.vai_impostazioni)):
            f = tk.Frame(nav, bg=C["primary"]); f.pack(side="left", fill="y", padx=px(10))
            lin = tk.Frame(f, bg=C["primary"], height=px(3)); lin.pack(fill="x", side="bottom")
            lab = tk.Label(f, text=testo, font=F(14, "semi"), fg="white", bg=C["primary"], padx=px(7), cursor="hand2", takefocus=1, highlightthickness=2, highlightbackground=C["primary"], highlightcolor="white")
            lab.pack(fill="y", expand=True)
            lab.bind("<Button-1>", lambda e, c=cmd: self._se_libero(c))
            lab.bind("<Return>", lambda e, c=cmd: self._se_libero(c))
            lab.bind("<space>", lambda e, c=cmd: self._se_libero(c))
            self.schede[k] = lin
        u = tk.Frame(t, bg=C["primary"]); u.pack(side="right", padx=px(28))
        self.av = tk.Canvas(u, width=px(36), height=px(36), bg=C["primary"], highlightthickness=0)
        self.av.pack(side="right")
        nu = tk.Frame(u, bg=C["primary"]); nu.pack(side="right", padx=px(10))
        self.lab_nome = etichetta(nu, "", 14, "semi", colore="white"); self.lab_nome.pack(anchor="e")
        self.lab_uff = etichetta(nu, "", 12.5, colore=C["tint"]); self.lab_uff.pack(anchor="e")
        Bottone(nav, "Informazioni", self.mostra_informazioni, "secondario", dim=12, pady=3).pack(side="right", padx=px(20), pady=px(5))
        self._aggiorna_utente()
        shine=tk.Canvas(t,bg=C["primary"],height=px(4),highlightthickness=0)
        shine.place(relx=0,rely=1,relwidth=1,y=-px(4))
        strip=shine.create_rectangle(0,0,40,px(4),fill=mescola(C["primary"],"#ffffff",.08),outline="")
        self.movimento.effetto(shine,lambda n:shine.coords(strip,n*(shine.winfo_width()+80)-80,0,n*(shine.winfo_width()+80),px(4)),6,continuo=True)

    def _aggiorna_utente(self):
        d = self.s.dipendente()
        self.lab_nome.configure(text=d.get("nome") or "")
        self.lab_uff.configure(text=d.get("ufficio") or "")
        self.av.delete("all")
        if d.get("nome"):
            self.av.create_oval(2, 2, px(34), px(34), fill=C["dark"], outline="#7f9fc0", width=px(2))
            self.av.create_text(px(18), px(18.5), text=iniziali(d["nome"]), fill="white", font=F(13, "bold"))

    def _scheda_attiva(self, k):
        for kk, lin in self.schede.items():
            lin.configure(bg="white" if kk == k else C["primary"])

    def _se_libero(self, cmd):
        if not self._occupato:
            cmd()

    def _tab_modale(self, event, indietro=False):
        if self.velo is None:
            return None
        controls = []
        def visit(w):
            try:
                if str(w.cget("takefocus")) == "1" or isinstance(w, (tk.Entry, tk.Text)):
                    controls.append(w)
            except tk.TclError:
                pass
            for child in w.winfo_children():
                visit(child)
        visit(self.velo)
        if controls:
            current = self.focus_get()
            i = controls.index(current) if current in controls else (-1 if not indietro else 0)
            controls[(i + (-1 if indietro else 1)) % len(controls)].focus_set()
        return "break"

    def vai_impostazioni(self):
        self._scheda_attiva("impostazioni")
        self._pulisci()
        scroll = Scorrevole(self.corpo); scroll.pack(fill="both", expand=True)
        w = scroll.dentro
        q = tk.Frame(w, bg=C["bg"]); q.pack(fill="x", padx=px(48), pady=px(24))
        etichetta(q, "Impostazioni", 24, "bold", colore=C["dark"]).pack(anchor="w")
        etichetta(q, "Profilo personale e destinazione dei PDF", 17, "bold").pack(anchor="w", pady=px(12))
        values = []
        for label, initial in (("Nome e cognome", self.s.dipendente().get("nome", "")),
                               ("Ufficio", self.s.dipendente().get("ufficio", "")),
                               ("Cartella PDF locale", self.s.imp["cartella_pdf"])):
            etichetta(q, label).pack(anchor="w")
            e = tk.Entry(q, font=F(15), relief="flat", highlightthickness=2,
                         highlightcolor=C["primary"], highlightbackground=C["bordo"])
            e.insert(0, initial); e.pack(fill="x", pady=(0,px(12))); values.append(e)
        def save():
            try:
                self.s.salva_preferenze(*(v.get() for v in values))
                self._aggiorna_utente()
                self.vai_impostazioni()
            except (ErroreApp, OSError) as e:
                self.errore(str(e))
        etichetta(q,"Riduci animazioni",14,"semi").pack(anchor="w")
        motion = tk.StringVar(value=self.s.imp.get("riduci_animazioni","sistema"))
        tk.OptionMenu(q,motion,"sistema","ridotte","complete").pack(anchor="w",pady=px(6))
        def motion_changed(*_):
            self.s.salva_movimento(motion.get()); self.movimento.abilita(motion.get())
        motion.trace_add("write",motion_changed)
        etichetta(q,"Sistema: segue Windows se leggibile, altrimenti ridotte. Movimento fermo dopo 5 s senza interazione.",12,colore=C["muted"],wrap=740).pack(anchor="w")
        Bottone(q, "Salva impostazioni", save).pack(anchor="w")
        etichetta(q, "Policy dei Sistemi Informativi · sola lettura", 17, "bold").pack(anchor="w", pady=(px(28),px(12)))
        from aggregatore.configurazione import FASCIA_MIN, carica
        policy = carica()
        for text in (f"Fasce di {FASCIA_MIN} minuti. Elenco delle applicazioni gestito dal CED.",
                     "Rete e Halley: disabilitati. AI facoltativa, richiesta dalla revisione.",
                     f"Retention raw: {policy.get('retention_raw_giorni') or 'da validare dall’Ente'}.",
                     "Le modifiche alla policy richiedono il riavvio dei processi."):
            etichetta(q, text, wrap=820, adatta=True).pack(anchor="w", pady=px(4))

    def _pulisci(self):
        self.chiudi_velo()
        self._chip_index=0
        for w in self.corpo.winfo_children():
            w.destroy()
        gc.collect()
        self.after_idle(self._transizione)

    def _transizione(self):
        if not self.corpo.winfo_children():return
        w=self.corpo.winfo_children()[0]
        if w.winfo_manager() != "pack":return
        info=w.pack_info(); raw=info.get("pady",0); margins=raw if isinstance(raw,(list,tuple)) else self.tk.splitlist(str(raw));top=int(margins[0]);bottom=int(margins[-1])
        self.movimento.effetto(w,lambda n:w.pack_configure(pady=(top+px(6*(1-n)),bottom)),.18,chiave="schermata")

    def _contenitore(self, alto=24):
        scroll = Scorrevole(self.corpo, bg=C["bg"])
        scroll.pack(fill="both", expand=True, padx=px(36), pady=(px(alto), px(4)))
        return scroll.dentro

    # --------------------------------------------------------------------------------- velo/modali
    def apri_velo(self, larghezza=720):
        self.chiudi_velo()
        self.update_idletasks()
        self.velo = tk.Frame(self.corpo, bg=C["velo"])
        self.velo.place(x=0, y=0, relwidth=1, relheight=1)
        sc = Scheda(self.velo, bordo="#cfd8e3")
        sc.place(relx=0.5, rely=0.5, anchor="center", width=min(px(larghezza), self.winfo_width()-px(32)), relheight=.94)
        scroll = Scorrevole(sc, bg="white"); scroll.pack(fill="both", expand=True)
        def focus_modal():
            if not scroll.cv.winfo_exists(): return
            def tags(w):
                w.bindtags(("AppModal",) + tuple(x for x in w.bindtags() if x != "AppModal"))
                for child in w.winfo_children(): tags(child)
            tags(scroll)
            scroll.cv.focus_set()
        self.after_idle(focus_modal)
        return scroll.dentro

    def chiudi_velo(self):
        if self.velo is not None:
            self.velo.destroy()
            self.velo = None

    def errore(self, testo: str, titolo="Non è stato possibile completare l'operazione"):
        sc = self.apri_velo(560)
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", padx=px(28), pady=px(24))
        etichetta(p, titolo, 18, "bold", colore=C["dark"], wrap=500).pack(anchor="w")
        etichetta(p, testo, 14.5, colore=C["muted"], wrap=500).pack(anchor="w", pady=(px(8), px(18)))
        Bottone(p, "Ho capito", self.chiudi_velo).pack(anchor="e")

    def _testata_modale(self, sc, sopra, titolo, sotto="", icona=None, chiudi=None, wrap=560):
        h = tk.Frame(sc, bg="white"); h.pack(fill="x", padx=px(28), pady=(px(18), px(12)))
        if icona == "stemma":
            self._stemma(h, True).pack(side="left", anchor="n", padx=(0, px(16)))
        elif icona:
            cv = tk.Canvas(h, width=px(46), height=px(46), bg="white", highlightthickness=0)
            cv.create_oval(1, 1, px(45), px(45), fill="#fdf0d5", outline="#fdf0d5")
            cv.create_text(px(23), px(24), text=icona, font=F(20, "bold"), fill=C["warn_txt"])
            cv.pack(side="left", anchor="n", padx=(0, px(16)))
        if chiudi:
            Bottone(h, "Chiudi", chiudi, "link", dim=13).pack(side="right", anchor="n")
        tx = tk.Frame(h, bg="white"); tx.pack(side="left", fill="x", expand=True)
        etichetta(tx, sopra.upper(), 12, "bold", colore=C["primary"]).pack(anchor="w")
        etichetta(tx, titolo, 22, "bold", colore=C["dark"], wrap=wrap).pack(anchor="w")
        if sotto:
            etichetta(tx, sotto, 14.5, colore=C["muted"], wrap=wrap).pack(anchor="w")
        tk.Frame(sc, bg=C["line"], height=1).pack(fill="x")

    # ----------------------------------------------------------------------------------------- coda
    def esegui(self, lavoro, fatto, errore=None):
        """Esegue lavoro() in un thread; fatto(risultato) o errore(eccezione) nel thread dell'interfaccia."""
        self._occupato = True
        gc.collect()        # le variabili Tk delle schermate chiuse vanno liberate qui, non nel thread di lavoro

        def corri():
            try:
                self.q.put((fatto, lavoro(), True))
            except Exception as e:   # noqa: BLE001
                self.q.put((errore or self._errore_lavoro, e, True))
        threading.Thread(target=corri, daemon=True).start()

    def _errore_lavoro(self, e):
        self.vai_oggi()
        self.errore(str(e) if isinstance(e, ErroreApp) else f"Errore imprevisto ({type(e).__name__}): {e}")

    def _coda(self):
        try:
            while True:
                fn, val, fine = self.q.get_nowait()
                if fine:
                    self._occupato = False
                fn(val)
        except queue.Empty:
            pass
        self.after(100, self._coda)

    # ============================================================================================ OGGI
    def vai_oggi(self):
        self._scheda_attiva("oggi")
        self._pulisci()
        st = self.s.stato()
        self._home(st)
        if self.s.serve_informativa():
            self.mostra_informativa()
        elif st["precedente_aperto"] and st["fase"] == "da_avviare":
            # Oltre mezzanotte con giornata ancora in corso: Pausa/Chiudi restano sulla home (stato in_corso).
            self.mostra_precedente()

    def _saluto(self):
        nome = (self.s.dipendente().get("nome") or "").replace("(ESEMPIO)", "").split()
        h = self.s.adesso().hour
        s = "Buonasera" if h >= 18 else "Buon pomeriggio" if h >= 14 else "Buongiorno"
        return s + (f", {nome[-1] if len(nome) > 1 else nome[0]}" if nome else "")

    def _home(self, st):
        w = self._contenitore()
        consuntivo = st["modalita"] == "consuntivo"
        oggi = data_lunga(st["giorno"]).capitalize()
        sc = Scheda(w, bg=C["dark"]); sc.pack(fill="x")
        p = tk.Frame(sc, bg=C["dark"]); p.pack(fill="x", padx=px(26), pady=px(24))
        dx = tk.Frame(p, bg=C["dark"]); dx.pack(side="right", padx=(px(20), 0))
        sx = tk.Frame(p, bg=C["dark"]); sx.pack(side="left", fill="both", expand=True)
        fase = st["fase"]
        if fase == "chiusura_da_completare":
            sc.configure(bg="white");p.configure(bg="white");sx.configure(bg="white");dx.configure(bg="white")
            self._home_da_completare(w, sc, sx, dx, st)
            return
        if st["oggi_concluso"] and fase == "da_avviare":
            b = badge(sx, "●  Resoconto di oggi salvato", "ok", 13)
        elif fase == "da_avviare":
            b = badge(sx, "●  Giornata non ancora avviata", "grigio", 13)
        elif fase == "in_corso":
            b = badge(sx, "●  Giornata in corso", "ok", 13)
        else:
            b = badge(sx, "❚❚  Giornata in pausa", "warn", 13)
        b.configure(padx=px(12), pady=px(4)); b.pack(anchor="w")
        if fase == "in_corso":
            status=tk.Frame(sx,bg=C["dark"]);status.pack(anchor="w",pady=px(4))
            dot=tk.Canvas(status,width=px(16),height=px(16),bg=C["dark"],highlightthickness=0);dot.pack(side="left")
            item=dot.create_oval(4,4,12,12,fill=C["ok"],outline="")
            etichetta(status,"Raccolta in corso" if not consuntivo else "Giornata in corso · consuntivo",12,colore=C["tint"]).pack(side="left")
            self.movimento.effetto(dot,lambda n:dot.coords(item,4-math.sin(n*math.pi*2)*.5,4-math.sin(n*math.pi*2)*.5,12+math.sin(n*math.pi*2)*.5,12+math.sin(n*math.pi*2)*.5),2,continuo=True)
        etichetta(sx, self._saluto(), 26, "bold", colore="white").pack(anchor="w", pady=(px(10), px(2)))
        if fase == "da_avviare":
            if st["oggi_concluso"]:
                testo = f"{oggi}. Il resoconto di oggi è già confermato e salvato: lo trovi in «Resoconti salvati»."
            elif consuntivo:
                testo = (f"{oggi}. Quando inizi a lavorare premi «Avvia giornata». Alla chiusura conto solo gli orari "
                         "dei tuoi pulsanti, solo per l'orario della giornata.")
            else:
                testo = (f"{oggi}. Quando inizi a lavorare premi «Avvia giornata»: da lì fino alla pausa o alla "
                         "chiusura registro, per fasce configurate, lo stato del computer e i programmi dell'elenco "
                         "del CED.")
            etichetta(sx, testo, 15, colore=C["tint"], wrap=520).pack(anchor="w")
            if not st["oggi_concluso"]:
                Bottone(dx, "▶   Avvia giornata", self.azione_avvia, dim=17, padx=70, pady=13).pack(fill="x")
                etichetta(dx, "Si parte solo quando premi il pulsante:\nnessun avvio automatico all'accesso.", 12.5,
                          colore=C["tint"], justify="center", anchor="center").pack(fill="x", pady=(px(8), 0))
        else:
            avvio = (st.get("avvio") or "")[11:16]
            if fase == "in_corso":
                testo = (f"{oggi} · giornata avviata da te alle {avvio}. Con «Pausa» sospendi la giornata quando vuoi. "
                         "Quando hai finito, chiudi la giornata: preparerò il resoconto e potrai rivederlo prima di salvarlo.")
            else:
                testo = (f"{oggi} · giornata in pausa dalle {(st.get('pausa_dalle') or '')[11:16]}. Durante la pausa "
                         "non viene contato nulla. Premi «Riprendi» quando torni al lavoro.")
            etichetta(sx, testo, 15, colore=C["tint"], wrap=500).pack(anchor="w")
            Bottone(dx, "■   Chiudi e rivedi", lambda: self.azione_chiudi(genera=False), dim=16, padx=26, pady=12).pack(fill="x")
            rr = tk.Frame(dx, bg=C["dark"]); rr.pack(fill="x", pady=(px(10), 0))
            if fase == "in_corso":
                Bottone(rr, "❚❚  Pausa", self.azione_pausa, "secondario").pack(side="left", fill="x", expand=True)
            else:
                Bottone(rr, "▶  Riprendi", self.azione_riprendi, "secondario").pack(side="left", fill="x", expand=True)
            Bottone(rr, "+  Aggiungi attività", lambda: self.mostra_aggiungi(st["giorno"]), "secondario").pack(
                side="left", fill="x", expand=True, padx=(px(10), 0))
        da_conf = [g for g in st["da_confermare"] if g != st["giorno"] or fase == "da_avviare"]
        if da_conf:
            bz = Scheda(w, bg=C["warn_bg"], bordo="#f0d9a8"); bz.pack(fill="x", pady=(px(14), 0))
            q = tk.Frame(bz, bg=C["warn_bg"]); q.pack(fill="x", padx=px(22), pady=px(10))
            g0 = da_conf[-1]
            etichetta(q, f"Il resoconto di {data_lunga(g0)} è chiuso ma non ancora confermato.", 15, "semi",
                      colore=C["warn_txt"]).pack(side="left")
            Bottone(q, "Rivedi e conferma", lambda: self.vai_revisione(g0), "secondario", pady=5).pack(side="right")
        if fase == "da_avviare":
            self._ultimi(w)
        else:
            self._finora(w, st)
        pv = Scheda(w, bg=C["tint2"], bordo="#d6e4f0"); pv.pack(fill="x", pady=(px(14), 0))
        q = tk.Frame(pv, bg=C["tint2"]); q.pack(fill="x", padx=px(22), pady=px(10))
        Bottone(q, "Cosa viene registrato", self.mostra_cosa, "link", dim=14).pack(side="right")
        etichetta(q, ("Conto solo gli orari dei tuoi pulsanti. " if consuntivo else
                      "Solo a giornata avviata: blocco e sblocco del computer, attività sì/no e programmi dell'elenco "
                      "del CED per fasce configurate. Rete disabilitata. ")
                  + "Mai tasti, mouse, schermate, titoli, nomi dei file, posta o indirizzi dei siti.", 14,
                  wrap=760).pack(side="left")

    def _home_da_completare(self, w, sc, sx, dx, st):
        """Collaudo ALFA3 N2: la chiusura non è andata a buon fine. La giornata non è «chiusa» e non si perde:
        «Riprova la chiusura» rifà la lettura e il riepilogo alla stessa ora di chiusura."""
        b = badge(sx, "⚠  Chiusura non completata", "warn", 13)
        b.configure(padx=px(12), pady=px(4)); b.pack(anchor="w")
        etichetta(sx, self._saluto(), 26, "bold", colore=C["dark"]).pack(anchor="w", pady=(px(10), px(2)))
        ora = (st.get("chiusura") or "")[11:16]
        etichetta(sx, f"La giornata di {data_lunga(st['giorno'])} è stata fermata alle {ora}, ma il resoconto non è "
                      "stato preparato. Nessun dato è perso: premi «Riprova la chiusura».", 15, colore=C["muted"],
                  wrap=520).pack(anchor="w")
        etichetta(sx, f"Dettaglio: {st.get('errore') or '—'}", 12.5, colore=C["err"], wrap=520).pack(
            anchor="w", pady=(px(6), 0))
        Bottone(dx, "↻   Riprova la chiusura", self.azione_riprova, dim=16, padx=40, pady=12).pack(fill="x")
        etichetta(dx, "Se l'errore si ripete, avvisa i Sistemi Informativi\n" + ASSISTENZA, 12.5,
                  colore=C["muted"], justify="center", anchor="center").pack(fill="x", pady=(px(8), 0))
        self._ultimi(w)

    def _ultimi(self, w):
        sc = Scheda(w); sc.pack(fill="x", pady=(px(14), 0))
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(24), pady=(px(16), px(12)))
        h = tk.Frame(p, bg="white"); h.pack(fill="x")
        etichetta(h, "Ultimi resoconti", 17, "bold", colore=C["dark"]).pack(side="left")
        Bottone(h, "Vedi tutti", self.vai_salvati, "link", dim=13.5).pack(side="right")
        el = self.s.resoconti_salvati()[:3]
        if not el:
            etichetta(p, "Non ci sono ancora resoconti salvati su questo computer.", 14.5, colore=C["muted"]).pack(
                anchor="w", pady=(px(14), px(6)))
        for r in el:
            self._riga_resoconto(p, r)

    def _riga_resoconto(self, p, r):
        tk.Frame(p, bg=C["line"], height=1).pack(fill="x", pady=(px(10), 0))
        rr = tk.Frame(p, bg="white"); rr.pack(fill="x", pady=(px(8), 0))
        _icona_doc(rr).pack(side="left", padx=(0, px(12)))
        tx = tk.Frame(rr, bg="white"); tx.pack(side="left")
        etichetta(tx, data_lunga(r["giorno"]).capitalize(), 15, "semi").pack(anchor="w")
        det = f"{_fasce(r.get('fasce') or 0)} con attività al computer · {r.get('dichiarate') or 0} attività dichiarate"
        etichetta(tx, det, 12.5, colore=C["muted"]).pack(anchor="w")
        if r["pdf"]:
            Bottone(rr, "Apri PDF", lambda x=r["pdf"]: apri_file(x), "link", dim=13.5).pack(side="right")
            badge(rr, "✓ Salvato", "ok").pack(side="right")
        else:
            Bottone(rr, "Ricrea PDF", lambda g=r["giorno"]: self._ricrea(g), "link", dim=13.5).pack(side="right")
            badge(rr, "PDF mancante", "err").pack(side="right")
        cod = tk.Frame(rr, bg="white"); cod.pack(side="right", padx=px(20))
        etichetta(cod, "codice ", 12.5, colore=C["muted"]).pack(side="left")
        etichetta(cod, r["codice"] or "—", 13, "bold").pack(side="left")

    def _ricrea(self, g):
        try:
            apri_file(self.s.rigenera_pdf(g))
        except ErroreApp as e:
            return self.errore(str(e))
        self.vai_salvati()

    def _finora(self, w, st):
        sc = Scheda(w); sc.pack(fill="x", pady=(px(14), 0))
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(22), pady=px(16))
        h = tk.Frame(p, bg="white"); h.pack(fill="x")
        etichetta(h, "Timeline · segnali e dichiarazioni", 19, "bold", colore=C["dark"]).pack(side="left")
        rev = self.s.revisione(st["giorno"])
        signals=self.s.segnali_correnti(st["giorno"])
        for slot in signals:
            row=tk.Frame(p,bg="white");row.pack(fill="x",pady=px(3))
            etichetta(row,slot["ora"]+"–"+slot["fine"],12,"semi",width=12).pack(side="left")
            for cat in slot["categorie"]:
                badge(row,"Rilevato · "+self.s.mappa().categorie.get(cat,cat),"info",11.5).pack(side="left",padx=px(3))
        if not signals:
            etichetta(p,"I segnali automatici disponibili verranno organizzati alla chiusura. Nessun segnale aggiunto dalla schermata.",12,colore=C["muted"],wrap=900).pack(anchor="w",pady=px(6))
        for manual in rev["manuali"][:3]:
            row=tk.Frame(p,bg="white");row.pack(fill="x",pady=px(3))
            etichetta(row,manual["dalle"]+"–"+manual["alle"],12,"semi",width=12).pack(side="left")
            badge(row,"Dichiarato · "+MANUALI.get(manual["categoria"],manual["categoria"]),"decl",11.5).pack(side="left")
        ora = self.s.adesso().strftime("%H:%M")
        etichetta(h, f"aggiornata alle {ora} · fasce di 15 minuti", 12.5, colore=C["muted"]).pack(side="right")
        fasce = self.s.fasce_finora()
        cv = barra_giornata(p, fasce, larghezza=960, ora_corrente=ora, manuali=rev["manuali"])
        cv.pack(anchor="w", pady=(px(12), px(4)))
        etichetta(p, "In modalità «a consuntivo» non si legge nessun registro del computer: qui vedi l'orario della "
                     "giornata, le pause e le attività che hai dichiarato." if st["modalita"] == "consuntivo" else
                     "Qui vedi l'orario della giornata, le pause e le attività che hai dichiarato; le fasce rilevate "
                     "(attività al computer e programmi) compaiono nel resoconto quando chiudi la giornata.",
                  12.5, colore=C["muted"], wrap=960).pack(anchor="w")
        legenda(p, [(COLORI_STATO["nessuna_attivita_informatica_rilevata"], "Giornata avviata"),
                    ("#e9dfc6", "In pausa"), (COLORI_STATO["sessione_chiusa"], "Fuori dalla giornata"),
                    (C["decl"], "Attività dichiarate da te")]).pack(anchor="w", pady=(px(6), 0))
        r3 = tk.Frame(w, bg=C["bg"]); r3.pack(fill="x", pady=(px(14), 0))
        for i in range(3):
            r3.columnconfigure(i, weight=1, uniform="a")
        b1 = Scheda(r3); b1.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
        q = tk.Frame(b1, bg="white"); q.pack(fill="both", padx=px(18), pady=px(14))
        etichetta(q, "Giornata avviata alle", 13.5, "semi", colore=C["muted"]).pack(anchor="w")
        etichetta(q, (st.get("avvio") or "")[11:16] or "—", 26, "bold", colore=C["dark"]).pack(anchor="w")
        b2 = Scheda(r3); b2.grid(row=0, column=1, sticky="nsew", padx=px(8))
        q = tk.Frame(b2, bg="white"); q.pack(fill="both", padx=px(18), pady=px(14))
        hh = tk.Frame(q, bg="white"); hh.pack(anchor="w")
        etichetta(hh, "Attività fuori dal computer  ", 13.5, "semi", colore=C["muted"]).pack(side="left")
        badge(hh, "dichiarata", "decl").pack(side="left")
        etichetta(q, str(len(rev["manuali"])), 26, "bold", colore=C["dark"]).pack(anchor="w")   # B4: numero, non tempo
        b3 = Scheda(r3); b3.grid(row=0, column=2, sticky="nsew", padx=(px(8), 0))
        q = tk.Frame(b3, bg="white"); q.pack(fill="both", padx=px(18), pady=px(14))
        etichetta(q, "Ultima attività che hai aggiunto", 13.5, "semi", colore=C["muted"]).pack(anchor="w")
        if rev["manuali"]:
            m = rev["manuali"][-1]
            box = tk.Frame(q, bg=C["decl_bg"]); box.pack(fill="x", pady=(px(6), 0))
            tk.Frame(box, bg=C["decl"], width=px(3)).pack(side="left", fill="y")
            bx = tk.Frame(box, bg=C["decl_bg"]); bx.pack(side="left", fill="x", padx=px(10), pady=px(6))
            etichetta(bx, f"{MANUALI[m['categoria']]} · {m['dalle']}–{m['alle']}", 14, "semi", bg=C["decl_bg"]).pack(anchor="w")
            etichetta(bx, (m["descrizione"] or "—")[:44], 13, colore=C["muted"], bg=C["decl_bg"]).pack(anchor="w")
        else:
            etichetta(q, "Nessuna: usa «Aggiungi attività» per riunioni, telefonate, lavoro su carta…", 13,
                      colore=C["muted"], wrap=270).pack(anchor="w", pady=(px(6), 0))

    # ------------------------------------------------------------------------------ azioni della home
    def _azione(self, fn):
        try:
            fn()
        except ErroreApp as e:
            return self.errore(str(e))
        self.vai_oggi()

    def azione_avvia(self):
        self._azione(self.s.avvia)

    def azione_pausa(self):
        self._azione(self.s.pausa)

    def azione_riprendi(self):
        self._azione(self.s.riprendi)

    def azione_chiudi(self, quando=None, genera=False, riprova=False):
        st = self.s.stato()
        if riprova:
            giorno, ora = st["giorno"], (st.get("chiusura") or "")[11:16]
        else:
            giorno = st["precedente_aperto"]["giorno"] if quando else st["giorno"]
            ora = (quando or self.s.adesso()).strftime("%H:%M")
        self.mostra_generazione(giorno, ora, genera)

        def avanzamento(n, info):
            self.q.put((lambda _v: self._passo(n, info), None, False))

        # stessa funzione del collaudo senza finestra (--smoke-giornata): Servizio.chiudi_e_genera
        self.esegui(lambda: self.s.chiudi_e_genera(quando, genera, riprova=riprova, avanzamento=avanzamento),
                    lambda v: self._fine_generazione(giorno, v))

    def azione_riprova(self):
        """«Riprova la chiusura» (collaudo ALFA3 N2)."""
        self.azione_chiudi(None, True, riprova=True)

    # ===================================================================================== informativa
    def mostra_informativa(self):
        sc = self.apri_velo(800)
        self._testata_modale(sc, "Primo avvio · informativa", "Prima di iniziare: cosa fa questa applicazione",
                             "Ti aiuta a preparare il resoconto della tua giornata di lavoro agile. Ecco in breve cosa "
                             "registra e cosa no.", icona="stemma", wrap=640)
        cons = self.s.imp["modalita"] == "consuntivo"
        tre = tk.Frame(sc, bg="white"); tre.pack(fill="x", padx=px(28), pady=(px(16), px(10)))
        col = [("Cosa registra", C["primary"], C["tint2"],
                (["Solo gli orari dei tuoi pulsanti: Avvia, Pausa e Chiudi giornata",
                  "Solo quando chiudi la giornata: nessun programma resta attivo"] if cons else
                 INFORMATIVA_COLLECTOR + ([INFORMATIVA_HALLEY] if self.s.imp.get("estensione_browser") is True
                                          else [INFORMATIVA_WEB]))),
               ("Cosa non registra mai", "#7d8b96", "#f4f6f8", INFORMATIVA_MAI),
               ("Cosa resta a te", C["decl"], C["decl_bg"],
                ["Rivedi il resoconto prima di salvarlo", "Aggiungi le attività fuori dal computer: telefonate, "
                 "riunioni, sopralluoghi", "Puoi segnalare un dato che ti sembra sbagliato",
                 "Un momento senza attività al computer non significa che non stavi lavorando"])]
        for i, (tit, cbar, cbg, voci) in enumerate(col):
            tre.columnconfigure(i, weight=1, uniform="c")
            f = tk.Frame(tre, bg=cbg)
            f.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(7), 0 if i == 2 else px(7)))
            tk.Frame(f, bg=cbar, height=px(3)).pack(fill="x")
            q = tk.Frame(f, bg=cbg); q.pack(fill="both", padx=px(14), pady=px(12))
            etichetta(q, tit, 15.5, "bold", colore=C["dark"], bg=cbg).pack(anchor="w", pady=(0, px(6)))
            for v in voci:
                etichetta(q, "•  " + v, 13.5, bg=cbg, wrap=205).pack(anchor="w", pady=px(1))
        dati = tk.Frame(sc, bg="white"); dati.pack(fill="x", padx=px(28), pady=(px(4), px(2)))
        dati.columnconfigure(0, weight=1); dati.columnconfigure(1, weight=1)
        etichetta(dati, "Nome e cognome (comparirà nel resoconto)", 13, "semi", colore=C["muted"]).grid(row=0, column=0, sticky="w")
        etichetta(dati, "Ufficio", 13, "semi", colore=C["muted"]).grid(row=0, column=1, sticky="w", padx=(px(14), 0))
        d = self.s.dipendente()
        mk = lambda: tk.Entry(dati, font=F(15), relief="flat", highlightthickness=1, highlightbackground="#b8c4cf",  # noqa: E731
                              highlightcolor=C["primary"])
        self.e_nome, self.e_uff = mk(), mk()
        self.e_nome.insert(0, d.get("nome", "")); self.e_uff.insert(0, d.get("ufficio", ""))
        self.e_nome.grid(row=1, column=0, sticky="we", ipady=px(5))
        self.e_uff.grid(row=1, column=1, sticky="we", ipady=px(5), padx=(px(14), 0))
        etichetta(sc, f"Informativa completa: versione {VERSIONE_INFORMATIVA} (la trovi anche in «Aiuto»).", 13,
                  colore=C["muted"]).pack(anchor="w", padx=px(28), pady=(px(8), 0))
        basso = tk.Frame(sc, bg="white"); basso.pack(fill="x", padx=px(28), pady=(px(10), px(22)))
        self.pv = tk.BooleanVar(value=False)
        bt = Bottone(basso, "Conferma e continua  ›", None)
        bt.pack(side="right")
        Bottone(basso, "Chiudi", self.destroy, "secondario").pack(side="right", padx=px(12))
        sx = tk.Frame(basso, bg="white"); sx.pack(side="left", fill="x", expand=True)
        Casella(sx, "Ho letto l'informativa e ne prendo visione.", self.pv, lambda: bt.attiva(self.pv.get())).pack(anchor="w")
        etichetta(sx, "È una presa visione, non un consenso. La data e la versione saranno riportate nei tuoi "
                      "resoconti.", 12.5, colore=C["muted"], wrap=420).pack(anchor="w", padx=(px(29), 0))

        def ok():
            try:
                self.s.registra_informativa(self.e_nome.get(), self.e_uff.get())
            except ErroreApp:
                self.e_nome.configure(highlightbackground=C["err"], highlightthickness=2)
                return
            self._aggiorna_utente()
            self.vai_oggi()
        bt.comando = ok
        bt.attiva(False)

    def mostra_cosa(self):
        sc = self.apri_velo(700)
        self._testata_modale(sc, "Trasparenza", "Cosa viene registrato", chiudi=self.chiudi_velo)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(28), pady=px(18))
        cons = self.s.imp["modalita"] == "consuntivo"
        righe = [("Giornata", "orari dei tuoi pulsanti Avvia, Pausa e Chiudi giornata")] if cons else \
                [("Quando", "solo tra «Avvia giornata» e «Chiudi giornata», escluse le pause"),
                 ("Sessione di Windows", "accesso, blocco, sblocco, disconnessione, riconnessione, sospensione, ripresa "
                                         "e chiusura della sessione, con l'ora"),
                 ("Attività", "per ogni fascia di 15 minuti solo sì/no: se hai usato tastiera o mouse (mai quali tasti, "
                              "mai dove)"),
                 ("Programmi", "nome dei soli programmi dell'elenco del CED in primo piano nella fascia (es. «Microsoft "
                               "Word»); degli altri programmi non resta traccia"),
                 ("Rete", "disabilitata in questa edizione"),
                 ("Web", "il browser solo come «Web»; il gestionale Halley solo come nome"
                         if self.s.imp.get("estensione_browser") is True else
                         "il browser solo come «Web», senza siti né indirizzi")]
        for a, b in righe:
            r = tk.Frame(p, bg="white"); r.pack(fill="x", pady=px(4))
            etichetta(r, a, 14.5, "semi", width=18).pack(side="left", anchor="n")
            etichetta(r, b, 14, colore=C["muted"], wrap=440).pack(side="left")
        etichetta(p, "Mai: tasti, mouse, schermate, titoli delle finestre, nomi dei file, numero, testo, oggetto o "
                     "destinatari delle mail, cronologia del browser e indirizzi dei siti, registro eventi di Windows. "
                     "Tutto resta su questo computer finché non decidi tu di consegnare il PDF.", 14, "semi", colore=C["dark"], wrap=620).pack(anchor="w", pady=(px(12), px(14)))
        Bottone(p, "Chiudi", self.chiudi_velo).pack(anchor="e")

    # ======================================================================= aggiungi attività
    def mostra_aggiungi(self, giorno):
        sc = self.apri_velo(640)
        self._testata_modale(sc, "Attività fuori dal computer", "Aggiungi un'attività",
                             "Riunioni, telefonate, lavoro su carta, sopralluoghi… Comparirà come «dichiarata da te».",
                             chiudi=self.chiudi_velo)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(28), pady=px(18))
        self._form_attivita(p, giorno, self.vai_oggi, None, larga=True)

    def _form_attivita(self, p, giorno, dopo, voce=None, larga=False):
        bgp = p.cget("bg")
        cat = tk.StringVar(value=(voce or {}).get("categoria", "riunione"))
        chips = tk.Frame(p, bg=bgp); chips.pack(fill="x")
        bott = {}

        def scegli(k):
            cat.set(k)
            for kk, b in bott.items():
                on = kk == k
                b.configure(text=("✓ " if on else "") + MANUALI[kk], bg=C["decl_bg"] if on else "white", fg=C["decl_txt"] if on else C["text"],
                            highlightbackground=C["decl"] if on else "#c7d0d9")
        for i, (k, v) in enumerate(MANUALI.items()):
            chips.columnconfigure(i % 2, weight=1)
            b = tk.Label(chips, text=v, font=F(13.5, "semi"), padx=px(5), pady=px(3),
                         wraplength=px(230 if larga else 125), takefocus=1, highlightthickness=2,
                         highlightcolor=C["dark"], cursor="hand2")
            b.grid(row=i//2, column=i%2, sticky="nsew", padx=px(3), pady=px(3))
            for key in ("<Button-1>", "<Return>", "<space>"):
                b.bind(key, lambda e, kk=k: (scegli(kk), "break")[1])
            bott[k] = b
        scegli(cat.get())
        g = tk.Frame(p, bg=bgp); g.pack(fill="x", pady=(px(6), 0))
        for i, t in enumerate(("Dalle", "Alle", "Breve descrizione")):
            etichetta(g, t, 13, "semi").grid(row=0, column=i, sticky="w", padx=(0 if i == 0 else px(8), 0))
        mk = lambda: tk.Entry(g, font=F(15), width=6, relief="flat", highlightthickness=1,   # noqa: E731
                              highlightbackground="#b8c4cf", highlightcolor=C["primary"], justify="center")
        e1, e2 = mk(), mk()
        e1.grid(row=1, column=0, ipady=px(6)); e2.grid(row=1, column=1, ipady=px(6), padx=(px(8), 0))
        e1.insert(0, (voce or {}).get("dalle", "")); e2.insert(0, (voce or {}).get("alle", ""))
        desc = tk.Entry(g, font=F(15), relief="flat", highlightthickness=1, highlightbackground="#b8c4cf",
                        highlightcolor=C["primary"])
        desc.grid(row=1, column=2, sticky="we", ipady=px(6), padx=(px(8), 0))
        g.columnconfigure(2, weight=1)
        desc.insert(0, (voce or {}).get("descrizione", ""))
        basso = tk.Frame(p, bg=bgp); basso.pack(fill="x", pady=(px(6), 0))
        cont = etichetta(basso, "", 12, colore=C["muted"]); cont.pack(side="left", anchor="n")
        msg = etichetta(p, "", 13, colore=C["err"], wrap=520 if larga else 330)

        def conta(*_):
            if len(desc.get()) > MAX_DESCRIZIONE:
                desc.delete(MAX_DESCRIZIONE, "end")
            cont.configure(text=f"{len(desc.get())} / {MAX_DESCRIZIONE} caratteri")
        desc.bind("<KeyRelease>", conta); conta()

        def aggiungi():
            try:
                if voce:
                    self.s.rimuovi_manuale(giorno, voce["id"])
                self.s.aggiungi_manuale(giorno, cat.get(), e1.get().strip(), e2.get().strip(), desc.get())
            except ErroreApp as e:
                if voce:
                    self.s.aggiungi_manuale(giorno, voce["categoria"], voce["dalle"], voce["alle"], voce["descrizione"])
                msg.configure(text=str(e)); msg.pack(anchor="w", pady=(px(6), 0))
                return
            dopo()
        Bottone(basso, "+  " + ("Salva la modifica" if voce else "Aggiungi"), aggiungi, "secondario", pady=7).pack(side="right")
        self._campi_attivita = (e1, e2, desc)

    # ================================================================================ generazione
    def mostra_generazione(self, giorno, ora_chiusura, genera=True):
        self._generazione_sintesi = genera
        self._scheda_attiva("oggi")
        self._pulisci()
        w = tk.Frame(self.corpo, bg=C["bg"]); w.pack(fill="both", expand=True)
        sc = Scheda(w); sc.place(relx=0.5, rely=0.48, anchor="center", width=px(620))
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", padx=px(34), pady=px(28))
        etichetta(p, f"CHIUSURA DELLA GIORNATA · {data_lunga(giorno).upper()}", 12, "bold", colore=C["primary"]).pack(anchor="w")
        etichetta(p, "Sto preparando il tuo resoconto", 25, "bold", colore=C["dark"]).pack(anchor="w", pady=(px(4), 0))
        etichetta(p, f"Giornata chiusa alle {ora_chiusura}. Ci vorrà circa un minuto.", 15, colore=C["muted"]).pack(anchor="w")
        self.passi = []
        voci = [("Raccolta dei dati della giornata", "Orari della giornata"),
                ("Riepilogo per fasce configurate", ""),
                ("Scrittura della sintesi della giornata", "L'assistente mette in parole i dati raccolti…"),
                ("Pronto per la tua revisione", "")]
        if not genera:
            voci[2] = ("Sintesi della giornata", "La genererai dalla revisione, dopo aver controllato i dati")
        box = tk.Frame(p, bg="white"); box.pack(fill="x", pady=(px(20), px(10)))
        for i, (t, s) in enumerate(voci):
            r = tk.Frame(box, bg="white"); r.pack(fill="x", pady=px(7))
            cv = tk.Canvas(r, width=px(28), height=px(28), bg="white", highlightthickness=0)
            cv.pack(side="left", anchor="n")
            tx = tk.Frame(r, bg="white"); tx.pack(side="left", padx=px(12), fill="x", expand=True)
            l1 = etichetta(tx, t, 15.5, "semi"); l1.pack(anchor="w")
            l2 = etichetta(tx, s, 13, colore=C["muted"], wrap=480); l2.pack(anchor="w")
            barra = tk.Canvas(tx, width=px(340), height=px(6), bg="white", highlightthickness=0)
            self.passi.append({"cv": cv, "t": l1, "s": l2, "barra": barra, "n": i + 1})
        self.t_passo3 = None
        self._passo(1, None)
        inf = tk.Frame(p, bg="white"); inf.pack(fill="x", pady=(px(8), 0))
        for i, testo in enumerate(("L'assistente lavora solo su questo computer: nessun dato esce dalla postazione.",
                                   "Riformula i dati, non aggiunge fatti. Potrai correggere ogni frase.")):
            inf.columnconfigure(i, weight=1, uniform="i")
            f = tk.Frame(inf, bg=C["tint2"])
            f.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(6), px(6) if i == 0 else 0))
            etichetta(f, testo, 13, bg=C["tint2"], wrap=235).pack(padx=px(12), pady=px(10), anchor="w")

    def _passo(self, n, info):
        if not getattr(self, "passi", None) or not self.passi[0]["cv"].winfo_exists():
            return
        for ps in self.passi:
            cv, k = ps["cv"], ps["n"]
            cv.delete("all")
            s = px(28)
            if k < n:
                cv.create_oval(1, 1, s - 1, s - 1, fill=C["ok"], outline=C["ok"])
                cv.create_line(px(8), px(14), px(12), px(18), px(20), px(10), fill="white", width=px(2.4))
                ps["t"].configure(fg=C["text"])
            elif k == n:
                cv.create_oval(2, 2, s - 2, s - 2, fill=C["primary"], outline="#cfe0ee", width=px(3))
                cv.create_text(s / 2, s / 2, text=str(k), fill="white", font=F(12, "bold"))
                ps["t"].configure(fg=C["text"])
            else:
                cv.create_oval(2, 2, s - 2, s - 2, fill="white", outline="#b8c4cf", width=px(1.5))
                cv.create_text(s / 2, s / 2, text=str(k), fill=C["muted"], font=F(12, "semi"))
                ps["t"].configure(fg=C["muted"])
        if n == 2 and info:
            try:
                g = Giornata(self.s.tecnico(info["giorno"]))
                att = [f for f in g.fasce if f["stato"] == "attivita_rilevata"]
                txt = (f"{len(att)} fasce con attività al computer"
                       + (f", tra le {att[0]['ora']} e le {g._fine(att[-1]['n'])}" if att else "")
                       + f" · dati letti in {info.get('secondi', 0):.1f} s")
                self.passi[1]["s"].configure(text=txt)
            except Exception:   # noqa: BLE001
                pass
        if n == 3:
            self.passi[2]["barra"].pack(anchor="w", pady=(px(6), 0))
            self.t_passo3 = time.monotonic()
            self._anima()

    def _anima(self):
        if not self.passi or not self.passi[2]["barra"].winfo_exists():return
        b=self.passi[2]["barra"]
        b.delete("all")
        b.create_rectangle(0,0,px(340),px(6),fill=C["tint"],outline="")
        indicator=b.create_rectangle(0,0,px(65),px(6),fill=C["primary"],outline="")
        self.passi[2]["s"].configure(text="Preparazione in corso. La sintesi dovrà essere verificata." if self._generazione_sintesi
                                    else "Preparazione del PDF e dei sigilli in corso.")
        self.movimento.effetto(b,lambda n:b.coords(indicator,n*px(405)-px(65),0,n*px(405),px(6)),1.4,continuo=True,chiave="generazione")
        progresso(b.master,C["primary"],"white",shimmer=True)

    def _fine_generazione(self, giorno, v):
        self.t_passo3 = None
        self._passo(5, None)
        s = (v or {}).get("sintesi")
        if s and self.passi[2]["barra"].winfo_exists():
            self.passi[2]["barra"].pack_forget()
            perf = s.get("prestazioni") or {}
            self.passi[2]["s"].configure(text=("scritta dall'assistente locale" if s["origine_testo"] == "ai" else
                                                "testo standard") + (f" · {perf['secondi_totali']:.0f} s"
                                                                     if perf.get("secondi_totali") else ""))
        self.after_idle(lambda: self.vai_revisione(giorno))

    # ================================================================================== revisione
    def vai_revisione(self, giorno):
        self._scheda_attiva("oggi")
        self._pulisci()
        try:
            doc = self.s.documento(giorno)
        except ErroreApp as e:
            self.vai_oggi()
            return self.errore(str(e))
        rev = self.s.revisione(giorno)
        g = Giornata(doc)
        s = doc.get("sintesi_ai")
        self.ho_verificato.set(bool(s) and self._verificato_per == (giorno, s.get("testo")))
        fondo = tk.Frame(self.corpo, bg="white", highlightthickness=1, highlightbackground=C["bordo"])
        fondo.pack(side="bottom", fill="x")
        fq = tk.Frame(fondo, bg="white"); fq.pack(fill="x", padx=px(48), pady=px(11))
        self.bt_conferma = Bottone(fq, "Conferma e crea il PDF", lambda: self.azione_conferma(giorno), dim=16,
                                   padx=24, pady=11)
        self.bt_conferma.pack(side="right")
        Bottone(fq, "Salva e continua dopo", self.vai_oggi, "link", dim=15).pack(side="right", padx=px(26))
        etichetta(fq, "Rilevato · Dichiarato · Osservazioni · Sintesi", 12, colore=C["muted"]).pack(side="left")
        w = tk.Frame(self.corpo, bg=C["bg"]); w.pack(fill="both", expand=True, padx=px(48), pady=(px(14), px(10)))
        top = tk.Frame(w, bg=C["bg"]); top.pack(fill="x")
        etichetta(top, f"REVISIONE · {data_lunga(giorno).upper()}", 12, "bold", colore=C["primary"]).pack(anchor="w")
        etichetta(top, "Controlla la tua giornata prima di salvarla", 22, "bold", colore=C["dark"]).pack(anchor="w")
        cols = tk.Frame(w, bg=C["bg"]); cols.pack(fill="both", expand=True, pady=(px(10), 0))
        cols.columnconfigure(0, weight=11, uniform="r"); cols.columnconfigure(1, weight=7, uniform="r")
        cols.rowconfigure(0, weight=1)
        sc = Scheda(cols); sc.grid(row=0, column=0, sticky="nsew", padx=(0, px(16)))
        h = tk.Frame(sc, bg="white"); h.pack(fill="x", padx=px(18), pady=(px(14), px(6)))
        etichetta(h, "A · Dati rilevati (sola lettura)", 16, "bold", colore=C["dark"]).pack(side="left")
        etichetta(h, "I dati automatici non si modificano: puoi segnalarli", 12.5, colore=C["muted"]).pack(side="right")
        sl = Scorrevole(sc, bg="white"); sl.pack(fill="both", expand=True, padx=(px(10), px(2)), pady=(0, px(8)))
        self._righe(sl.dentro, giorno, doc, rev, g)
        dx = Scorrevole(cols, bg=C["bg"]); dx.grid(row=0, column=1, sticky="nsew")
        d = dx.dentro
        barra_giornata(d, g, larghezza=360, altezza=20, compatta=True).pack(anchor="w", pady=(0, px(8)))
        self._box_sintesi(d, giorno, doc)
        ag = Scheda(d); ag.pack(fill="x", pady=(px(12), 0), padx=(0, px(4)))
        q = tk.Frame(ag, bg="white"); q.pack(fill="x", padx=px(16), pady=px(14))
        voce = self._voce_in_modifica
        self._voce_in_modifica = None
        etichetta(q, ("✎  Modifica l'attività dichiarata" if voce else "B · Aggiungi attività dichiarata"),
                  15.5, "bold", colore=C["dark"]).pack(anchor="w", pady=(0, px(8)))
        self._form_attivita(q, giorno, lambda: self.vai_revisione(giorno), voce=voce)
        osv = Scheda(d); osv.pack(fill="x", pady=(px(12), px(4)), padx=(0, px(4)))
        q = tk.Frame(osv, bg="white"); q.pack(fill="x", padx=px(16), pady=px(14))
        hh = tk.Frame(q, bg="white"); hh.pack(fill="x")
        etichetta(hh, "C · Osservazioni", 15.5, "bold", colore=C["dark"]).pack(side="left")
        etichetta(hh, " (facoltative)", 13, colore=C["muted"]).pack(side="left")
        self.oss = TestoLimitato(q, MAX_OSSERVAZIONI, righe=3, testo=rev["osservazioni"])
        self.oss.pack(fill="x", pady=(px(6), 0))
        Bottone(q, "Salva osservazioni", lambda: self._salva_oss(giorno), "secondario", dim=13.5, pady=5).pack(
            anchor="e", pady=(px(4), 0))
        self._aggiorna_conferma(doc)

    def _salva_oss(self, giorno):
        try:
            self.s.imposta_osservazioni(giorno, self.oss.valore())
        except ErroreApp as e:
            return self.errore(str(e))
        self.vai_revisione(giorno)

    def _righe(self, p, giorno, doc, rev, g):
        """Righe della giornata: fasce automatiche raggruppate (sola lettura, «Segnala») e attività dichiarate (oro)."""
        segn = {(x.get("dalle"), x.get("alle")): x for x in rev["segnalazioni"]}
        voci = []
        ev = [e for e in doc.get("sessione", {}).get("eventi", []) if not e.get("implicito")]
        ini = next((e for e in ev if e["evento"] in ("avvio_raccolta", "accesso", "sblocco")), None)
        if ini:
            voci.append((ini["ora"] + "!", "evento_inizio", ini))
        for n0, n1, stato, app, siti in g.righe_revisione():
            voci.append((g.fasce[n0]["ora"] + "#", "fasce", (n0, n1, stato, app, siti)))
        for m in rev["manuali"]:
            voci.append((m["dalle"] + "~", "manuale", m))
        fine = [e for e in ev if e["evento"] in ("fine_raccolta", "chiusura", "spegnimento")]
        if fine:
            voci.append((fine[-1]["ora"] + "~~", "evento_fine", fine[-1]))
        voci.sort(key=lambda v: v[0])
        nomi_ev = {"accesso": "Accesso al computer", "avvio_raccolta": "Giornata avviata da te", "sblocco": "Sblocco del computer",
                   "fine_raccolta": "Giornata chiusa da te", "chiusura": "Chiusura della sessione",
                   "spegnimento": "Spegnimento del computer"}
        for _k, tipo, x in voci:
            r = tk.Frame(p, bg="white"); r.pack(fill="x")
            tk.Frame(p, bg=C["line"], height=1).pack(fill="x")
            if tipo.startswith("evento"):
                self._riga(r, x["ora"], "#7d8b96", "Inizio della giornata" if tipo == "evento_inizio" else "Fine della giornata",
                           nomi_ev.get(x["evento"], x["evento"]), tratt=True)
            elif tipo == "fasce":
                n0, n1, stato, app, siti = x
                dalle, alle = g.fasce[n0]["ora"], g._fine(n1)
                sotto = " · ".join([g.app(a) for a in app] + [g.sito(si) + " (sito)" for si in siti])
                if stato == "nessuna_attivita_informatica_rilevata":
                    sotto = sotto or "Non indica assenza di lavoro. Puoi aggiungere un’attività dichiarata."
                elif stato == "raccolta_sospesa":
                    sotto = f"Pausa dalle {dalle} alle {alle}: in questa fascia non è stato registrato nulla"
                elif stato == "sessione_bloccata":
                    sotto = sotto or "Nessuna attività informatica rilevata"
                elif stato == "attivita_rilevata" and not sotto:
                    sotto = "Computer in uso (sessione attiva)"
                sg = segn.get((dalle, alle))
                self._riga(r, f"{dalle} – {alle}", COLORI_STATO.get(stato, "#ccc"), ST_LAB.get(stato, stato), sotto,
                           auto=True, segnalata=sg,
                           al_segnala=lambda a=dalle, b=alle: self.mostra_segnala(giorno, a, b),
                           al_togli=(lambda sid=sg["id"]: self._togli_segn(giorno, sid)) if sg else None,
                           tratt=stato == "raccolta_sospesa")
            else:
                r.configure(bg=C["decl_bg"])
                self._riga(r, f"{x['dalle']} – {x['alle']}", C["decl"], MANUALI[x["categoria"]], x["descrizione"] or "—",
                           dichiarata=True, al_modifica=lambda v=x: self._modifica_voce(giorno, v),
                           al_elimina=lambda v=x: self._elimina_voce(giorno, v))

    def _riga(self, r, ora, colore, titolo, sotto="", auto=False, dichiarata=False, segnalata=None, al_segnala=None,
              al_togli=None, al_modifica=None, al_elimina=None, tratt=False):
        bg = r.cget("bg")
        q = tk.Frame(r, bg=bg); q.pack(fill="x", padx=px(8), pady=px(6))
        etichetta(q, ora, 14, "semi", bg=bg, width=12).pack(side="left", anchor="n")
        bar = tk.Canvas(q, width=px(4), height=px(36), bg=bg, highlightthickness=0)
        if tratt:
            for y in range(0, px(36), px(5)):
                bar.create_line(2, y, 2, y + px(2.5), fill=colore, width=px(3))
        else:
            bar.create_rectangle(0, 0, px(4), px(36), fill=colore, outline=colore)
        bar.pack(side="left", padx=(0, px(10)))
        az = tk.Frame(q, bg=bg); az.pack(side="right", anchor="n")
        tx = tk.Frame(q, bg=bg); tx.pack(side="left", fill="x", expand=True)
        etichetta(tx, titolo, 14.5, "semi", colore=C["decl_txt"] if dichiarata else C["text"], bg=bg).pack(anchor="w")
        if sotto:
            etichetta(tx, sotto, 13, colore=C["muted"], bg=bg, wrap=330, adatta=True).pack(anchor="w")
        if auto:
            if segnalata:
                Bottone(az, "⚑ Segnalato", al_togli, "oro", dim=12.5, padx=9, pady=2).pack(side="right")
            else:
                Bottone(az, "⚑ Segnala", al_segnala, "secondario", dim=12.5, padx=9, pady=2).pack(side="right")
            etichetta(az, "automatico", 12, colore=C["muted"], bg=bg).pack(side="right", padx=px(8))
        elif dichiarata:
            Bottone(az, "Elimina", al_elimina, "pericolo", dim=12.5, padx=8, pady=2).pack(side="right")
            Bottone(az, "Modifica", al_modifica, "secondario", dim=12.5, padx=8, pady=2).pack(side="right", padx=px(6))
            badge(az, "dichiarata", "decl", 11.5).pack(side="right", padx=px(4))
        if segnalata:
            nb = tk.Frame(r, bg=C["warn_bg"], highlightthickness=1, highlightbackground="#efd29b")
            nb.pack(fill="x", padx=(px(118), px(10)), pady=(0, px(8)))
            etichetta(nb, f"⚑ La tua segnalazione ({CAMPI_SEGNALAZIONE.get(segnalata['campo'], '')}) · il dato resta "
                          "com'è, la nota comparirà nel resoconto", 12.5, "semi", colore=C["warn_txt"], bg=C["warn_bg"],
                      wrap=420, adatta=True).pack(anchor="w", padx=px(10), pady=(px(6), 0))
            etichetta(nb, f"«{segnalata['nota']}»", 13, bg=C["warn_bg"], wrap=420, adatta=True).pack(anchor="w", padx=px(10), pady=(0, px(6)))

    def _togli_segn(self, giorno, sid):
        self.s.rimuovi_segnalazione(giorno, sid)
        self.vai_revisione(giorno)

    def _modifica_voce(self, giorno, v):
        self._voce_in_modifica = v
        self.vai_revisione(giorno)

    def _elimina_voce(self, giorno, v):
        sc = self.apri_velo(480)
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", padx=px(26), pady=px(22))
        etichetta(p, "Eliminare l'attività dichiarata?", 18, "bold", colore=C["dark"]).pack(anchor="w")
        etichetta(p, f"{MANUALI[v['categoria']]} {v['dalle']}–{v['alle']}: {v['descrizione'] or '—'}", 14,
                  colore=C["muted"], wrap=420).pack(anchor="w", pady=(px(6), px(16)))
        b = tk.Frame(p, bg="white"); b.pack(fill="x")

        def ok():
            self.s.rimuovi_manuale(giorno, v["id"])
            self.vai_revisione(giorno)
        Bottone(b, "Elimina", ok, "pericolo").pack(side="right")
        Bottone(b, "Annulla", self.chiudi_velo, "secondario").pack(side="right", padx=px(10))

    def mostra_segnala(self, giorno, dalle, alle):
        sc = self.apri_velo(580)
        self._testata_modale(sc, f"Segnala un dato · {dalle}–{alle}", "Questo dato non ti torna?",
                             "Il dato automatico resta com'è: la tua nota comparirà accanto, nel resoconto.",
                             chiudi=self.chiudi_velo, wrap=480)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(28), pady=px(16))
        campo = tk.StringVar(value="stato")
        etichetta(p, "Che cosa non torna", 13.5, "semi").pack(anchor="w")
        for k, t in (("stato", "lo stato della fascia (es. «computer bloccato»)"),
                     ("applicazioni", "i programmi o i siti indicati"), ("altro", "altro")):
            tk.Radiobutton(p, text=t, value=k, variable=campo, font=F(14), bg="white", activebackground="white",
                           anchor="w", highlightthickness=0).pack(anchor="w")
        etichetta(p, "La tua nota", 13.5, "semi").pack(anchor="w", pady=(px(8), px(2)))
        nota = TestoLimitato(p, MAX_NOTA, righe=3)
        nota.pack(fill="x")
        msg = etichetta(p, "", 13, colore=C["err"])

        def ok():
            try:
                self.s.segnala(giorno, campo.get(), dalle, alle, nota.valore())
            except (ErroreApp, ValueError) as e:
                msg.configure(text=str(e)); msg.pack(anchor="w")
                return
            self.vai_revisione(giorno)
        b = tk.Frame(p, bg="white"); b.pack(fill="x", pady=(px(8), 0))
        Bottone(b, "⚑  Segnala", ok).pack(side="right")
        Bottone(b, "Annulla", self.chiudi_velo, "secondario").pack(side="right", padx=px(10))
        self._nota_segnala = nota

    # ------------------------------------------------------------------------------------- sintesi
    def _scelta_ai(self, q, doc):
        info = self.s.disponibilita_ai(doc)
        if info["disponibile"]:
            Casella(q, "Usa AI locale (facoltativa)", self.usa_ai, dim=13, wrap=280).pack(anchor="w", pady=px(6))
        else:
            self.usa_ai.set(False)
        etichetta(q, info["messaggio"], 12, colore=C["muted"], wrap=290, adatta=True).pack(anchor="w")

    def _box_sintesi(self, d, giorno, doc):
        s = doc.get("sintesi_ai")
        o = (s or {}).get("origine_testo")
        sc = Scheda(d, bordo="#c9c3ee" if o == "ai" else None); sc.pack(fill="x", padx=(0, px(4)))
        tk.Frame(sc, bg=C["ai"] if o == "ai" else C["decl"] if o == "dichiarata" else C["primary"], height=px(3)).pack(fill="x")
        q = tk.Frame(sc, bg="white"); q.pack(fill="x", padx=px(16), pady=px(14))
        h = tk.Frame(q, bg="white"); h.pack(fill="x")
        etichetta(h, "D · Sintesi da verificare", 16, "bold", colore=C["dark"]).pack(side="left")
        if not s:
            etichetta(q, "La sintesi non c'è ancora, oppure i dati sono cambiati dopo l'ultima versione (attività, "
                         "segnalazioni o osservazioni): va generata di nuovo.", 14, colore=C["muted"], wrap=330, adatta=True).pack(
                anchor="w", pady=(px(8), px(10)))
            self._scelta_ai(q, doc)
            Bottone(q, "Prepara sintesi", lambda: self.azione_genera(giorno)).pack(anchor="w")
            return
        badge(h, {"ai": "scritta dall'assistente", "testo_standard": "testo standard",
                  "dichiarata": "modificata da te"}.get(o, o), {"ai": "ai", "dichiarata": "decl"}.get(o, "grigio")).pack(side="right")
        if o != "dichiarata" and s.get("frasi"):
            facts = {f["id"]: f for f in s.get("fatti", [])}
            labels = {"automatico": "Rilevato", "dichiarato": "Dichiarato", "osservazione": "Osservazione"}
            for phrase in s["frasi"]:
                origins = sorted({facts[i]["origine"] for i in phrase.get("fatti", []) if i in facts and facts[i].get("tipo") != "giorno"})
                etichetta(q, " / ".join(labels.get(x,x) for x in origins) or "Contesto", 12, "semi", colore=C["primary"]).pack(anchor="w", pady=(px(8),0))
                etichetta(q, phrase["testo"], 14.5, wrap=330, adatta=True).pack(anchor="w")
        else:
            etichetta(q, s["testo"], 14.5, wrap=330, adatta=True).pack(anchor="w", pady=(px(8),px(6)))
        if o == "testo_standard":
            mot = (s.get("scelta_profilo") or {}).get("motivo") or ""
            ragione = ("hai richiesto il testo standard" if mot == "Testo standard richiesto" else
                       "la versione dell'assistente non ha superato il controllo sui dati" if s.get("motore", {}).get("tipo") != "testo_standard" else
                       "è stato usato il fallback deterministico; puoi verificare la disponibilità dell'AI qui sotto")
            etichetta(q, f"Testo standard: {ragione}. Contiene solo i dati della giornata.", 12.5, colore=C["muted"],
                      wrap=330, adatta=True).pack(anchor="w")
        cm = s.get("controllo_modifica") or {}
        if o == "dichiarata" and cm.get("accettata_con_avvisi"):
            av = tk.Frame(q, bg=C["warn_bg"]); av.pack(fill="x", pady=(px(4), px(4)))
            etichetta(av, "Avvisi che hai confermato (compariranno nel PDF):", 12.5, "semi", colore=C["warn_txt"],
                      bg=C["warn_bg"]).pack(anchor="w", padx=px(8), pady=(px(5), 0))
            for pr in cm.get("problemi", [])[:4]:
                etichetta(av, "• " + avviso_leggibile(pr), 12, colore=C["warn_txt"], bg=C["warn_bg"], wrap=310, adatta=True).pack(anchor="w", padx=px(8))
            tk.Frame(av, bg=C["warn_bg"], height=px(4)).pack()
        az = tk.Frame(q, bg="white"); az.pack(fill="x", pady=(px(6), px(8)))
        self._scelta_ai(q, doc)
        rim = self.s.riscritture_rimaste(giorno)
        rs = Bottone(az, f"↻  Riscrivi ({rim})", lambda: self.azione_riscrivi(giorno), "secondario", dim=13.5, padx=10, pady=4)
        rs.pack(side="right")
        if rim <= 0:
            rs.attiva(False)
        Bottone(az, "✎  Modifica", lambda: self.mostra_modifica(giorno, s["testo"]), "secondario", dim=13.5, padx=10,
                pady=4).pack(side="right", padx=px(8))

        ver = tk.Frame(q, bg="white"); ver.pack(fill="x")

        def cambia():
            self._verificato_per = (giorno, s["testo"]) if self.ho_verificato.get() else None
            self._aggiorna_conferma(doc)
        Casella(ver, "Ho verificato la sintesi: corrisponde alla mia giornata", self.ho_verificato, cambia, dim=14,
                wrap=290).pack(anchor="w")
        badge(ver, "obbligatorio", "err", 11.5).pack(anchor="w", padx=(px(29), 0), pady=(px(3), 0))

    def _aggiorna_conferma(self, doc):
        ok = bool(doc.get("sintesi_ai")) and self.ho_verificato.get()
        if getattr(self, "bt_conferma", None) is not None and self.bt_conferma.winfo_exists():
            self.bt_conferma.attiva(ok)

    def azione_genera(self, giorno):
        self.mostra_generazione(giorno, "—")
        self.passi[0]["s"].configure(text="già fatta alla chiusura della giornata")
        self._passo(3, None)
        usa_ai = self.usa_ai.get()
        self.esegui(lambda: {"sintesi": self.s.genera(giorno, usa_ai=usa_ai)}, lambda v: self._fine_generazione(giorno, v))

    def azione_riscrivi(self, giorno):
        sc = self.apri_velo(500)
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", padx=px(26), pady=px(24))
        etichetta(p, "Sto riscrivendo la sintesi…", 19, "bold", colore=C["dark"]).pack(anchor="w")
        etichetta(p, "Stessi dati, nuova formulazione, stesso controllo. Circa un minuto.", 14, colore=C["muted"]).pack(anchor="w")

        def fatto(_v):
            self._verificato_per = None
            self.vai_revisione(giorno)

        def errore(e):
            self.vai_revisione(giorno)
            self.errore(str(e))
        usa_ai = self.usa_ai.get()
        self.esegui(lambda: self.s.riscrivi(giorno, usa_ai=usa_ai), fatto, errore)

    def mostra_modifica(self, giorno, testo, avvisi=None):
        sc = self.apri_velo(720)
        self._testata_modale(sc, "Modifica della sintesi", "Scrivi la sintesi con parole tue",
                             "Il testo diventa «dichiarato da te». Lo controllo con le stesse regole: numeri, orari e "
                             "nomi devono corrispondere ai dati della giornata.", chiudi=self.chiudi_velo, wrap=600)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(28), pady=px(16))
        ed = TestoLimitato(p, 3000, righe=6 if avvisi else 8, testo=testo); ed.pack(fill="x")
        if avvisi:
            av = tk.Frame(p, bg=C["warn_bg"], highlightthickness=1, highlightbackground="#efd29b")
            av.pack(fill="x", pady=(px(10), 0))
            etichetta(av, "⚠  Il controllo ha trovato dati che non corrispondono alla giornata:", 14, "semi",
                      colore=C["warn_txt"], bg=C["warn_bg"]).pack(anchor="w", padx=px(12), pady=(px(8), px(2)))
            for pr in avvisi[:6]:
                etichetta(av, "• " + avviso_leggibile(pr), 13, colore=C["warn_txt"], bg=C["warn_bg"], wrap=620).pack(anchor="w", padx=px(12))
            etichetta(av, "Puoi correggere il testo, oppure confermarlo così: gli avvisi resteranno nel JSON e nel PDF.",
                      13, bg=C["warn_bg"], wrap=620).pack(anchor="w", padx=px(12), pady=(px(4), px(8)))
        b = tk.Frame(p, bg="white"); b.pack(fill="x", pady=(px(12), 0))

        def salva(accetta=False):
            try:
                self.s.modifica(giorno, ed.valore(), accetta_avvisi=accetta)
            except ErroreApp as e:
                return self.errore(str(e))
            except ValueError as e:
                if hasattr(e, "problemi"):
                    return self.mostra_modifica(giorno, ed.valore(), e.problemi)
                return self.errore(str(e))
            self._verificato_per = None
            self.vai_revisione(giorno)
        Bottone(b, "Controlla e salva", salva).pack(side="right")
        if avvisi:
            Bottone(b, "Confermo il testo con questi avvisi", lambda: salva(True), "oro").pack(side="right", padx=px(10))
        Bottone(b, "Annulla", self.chiudi_velo, "secondario").pack(side="left")

    # ================================================================================== conferma
    def azione_conferma(self, giorno):
        if not self.ho_verificato.get():
            return self.errore("Spunta «Ho verificato la sintesi» prima di confermare.")
        sc = self.apri_velo(460)
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", padx=px(26), pady=px(24))
        etichetta(p, "Sto sigillando e creando il PDF…", 18, "bold", colore=C["dark"]).pack(anchor="w")

        def errore(e):
            self.vai_revisione(giorno)
            self.errore(str(e))
        self.mostra_generazione(giorno,"—",genera=False)
        self._anima()
        self.esegui(lambda: self.s.conferma(giorno, True), lambda r: self.mostra_conferma(giorno, r), errore)

    def mostra_conferma(self, giorno, r):
        self._verificato_per = None
        self._pulisci()
        w = tk.Frame(self.corpo, bg=C["bg"]); w.pack(fill="both", expand=True)
        sc = Scheda(w); sc.place(relx=0.5, rely=0.48, anchor="center", width=px(860))
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", padx=px(32), pady=px(26))
        self._anteprima(p, r).pack(side="right", anchor="n", padx=(px(26), 0))
        sx = tk.Frame(p, bg="white"); sx.pack(side="left", fill="both", expand=True)
        cv = tk.Canvas(sx, width=px(60), height=px(60), bg="white", highlightthickness=0)
        cv.create_oval(3, 3, px(57), px(57), fill=C["ok"], outline="#cfe8dc", width=px(4))
        cv.create_line(px(18), px(31), px(26), px(39), px(42), px(22), fill="white", width=px(4))
        cv.pack(anchor="w")
        etichetta(sx, "Resoconto salvato", 25, "bold", colore=C["dark"]).pack(anchor="w", pady=(px(10), px(2)))
        etichetta(sx, f"Il resoconto di {data_lunga(giorno)} è pronto e sigillato. Resta su questo computer: non viene "
                      "inviato a nessuno in automatico.", 15, colore=C["muted"], wrap=480).pack(anchor="w")
        fb = Scheda(sx); fb.pack(fill="x", pady=(px(14), px(10)))
        q = tk.Frame(fb, bg="white"); q.pack(fill="x", padx=px(12), pady=px(10))
        tk.Label(q, text="PDF", font=F(11, "bold"), fg="white", bg="#b3261e", padx=px(8), pady=px(10)).pack(side="left")
        tx = tk.Frame(q, bg="white"); tx.pack(side="left", padx=px(12))
        etichetta(tx, os.path.basename(r["pdf"]), 14.5, "semi").pack(anchor="w")
        kb = os.path.getsize(r["pdf"]) // 1024 if os.path.exists(r["pdf"]) else 0
        etichetta(tx, f"{percorso_breve(os.path.dirname(r['pdf']))} · PDF sigillato · {kb} KB", 12, colore=C["muted"], wrap=400).pack(anchor="w")
        cb = tk.Frame(sx, bg=C["tint2"]); cb.pack(fill="x")
        q = tk.Frame(cb, bg=C["tint2"]); q.pack(fill="x", padx=px(16), pady=px(12))
        etichetta(q, "Codice di verifica", 13, colore=C["muted"], bg=C["tint2"]).pack(anchor="w")
        etichetta(q, r["codice"], 22, "bold", colore=C["dark"], bg=C["tint2"]).pack(anchor="w")
        etichetta(q, "Permette a chi riceve il resoconto di controllare che non sia stato modificato.", 12.5,
                  colore=C["muted"], bg=C["tint2"]).pack(anchor="w")
        try:
            g = Giornata(self.s.finale(giorno))
            st = tk.Frame(sx, bg="white"); st.pack(fill="x", pady=(px(14), 0))
            for v, t in ((_fasce(g.t["fasce_per_stato"]["attivita_rilevata"]), "al computer · rilevato"),
                         (str(len(g.d.get("manuali", []))), "attività fuori dal computer · dichiarate"),
                         (str(len(g.d.get("segnalazioni_dipendente", []))), "segnalazioni")):
                c = tk.Frame(st, bg="white"); c.pack(side="left", padx=(0, px(34)))
                etichetta(c, v, 18, "bold").pack(anchor="w")
                etichetta(c, t, 12.5, colore=C["muted"]).pack(anchor="w")
        except Exception:   # noqa: BLE001
            pass
        bb = tk.Frame(sx, bg="white"); bb.pack(fill="x", pady=(px(18), 0))
        Bottone(bb, "Apri il PDF", lambda: apri_file(r["pdf"])).pack(side="left")
        Bottone(bb, "Mostra nella cartella", lambda: apri_file(r["pdf"], True), "secondario").pack(side="left", padx=px(12))
        Bottone(bb, "Torna alla pagina iniziale", self.vai_oggi, "link").pack(side="left", padx=px(8))

    def _anteprima(self, master, r):
        """Anteprima schematica della prima pagina del PDF (il PDF vero si apre con «Apri il PDF»)."""
        W, H = px(236), px(334)
        cv = tk.Canvas(master, width=W, height=H, bg="white", highlightthickness=1, highlightbackground=C["bordo"])
        cv.create_rectangle(0, 0, W, px(34), fill=C["primary"], outline="")
        cv.create_rectangle(0, px(34), W, px(36), fill=C["gold"], outline="")
        cv.create_text(px(12), px(17), text=NOME_ENTE.upper(), anchor="w", fill="white", font=F(10, "bold"))
        cv.create_text(W / 2, px(54), text="Resoconto attività in lavoro agile", fill=C["dark"], font=F(10.5, "bold"))
        cv.create_text(W / 2, px(68), text=r["codice"], fill=C["muted"], font=F(8.5))
        for i in range(3):
            cv.create_rectangle(px(12 + i * 72), px(82), px(78 + i * 72), px(112), fill=C["tint2"], outline=C["line"])
        cv.create_rectangle(px(12), px(124), W - px(12), px(136), fill=COLORI_STATO["attivita_rilevata"], outline="")
        for y in range(150, 310, 12):
            cv.create_rectangle(px(12), px(y), W - px(12 + (y * 7) % 50), px(y + 5), fill="#e3e8ee", outline="")
        return cv

    # ================================================================== giornata precedente non chiusa
    def mostra_precedente(self):
        try:
            pr = self.s.proposta_chiusura_precedente()
        except ErroreApp:
            return
        g = pr["giorno"]
        gs = data_lunga(g).split(" ")
        sc = self.apri_velo(640)
        self._testata_modale(sc, self._saluto(), f"La giornata di {gs[0]} {gs[1]} {gs[2]} non è stata chiusa",
                             "Vuoi chiuderla adesso? Preparerò il resoconto di quella giornata e potrai rivederlo come "
                             "al solito, prima di salvarlo.", icona="◷", wrap=500)
        tre = tk.Frame(sc, bg="white"); tre.pack(fill="x", padx=px(28), pady=(px(18), px(8)))
        for i, (t, v) in enumerate((("Giornata avviata da te", pr["avvio"][11:16]),
                                    ("Ultima attività registrata", (pr["ultima_attivita"] or "")[11:16] or "non rilevata"),
                                    ("Fine giornata proposta", pr["fine_proposta"][11:16]))):
            tre.columnconfigure(i, weight=1, uniform="p")
            f = tk.Frame(tre, bg=C["tint2"])
            f.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(6), 0 if i == 2 else px(6)))
            tk.Frame(f, bg=C["primary"], height=px(3)).pack(fill="x")
            q = tk.Frame(f, bg=C["tint2"]); q.pack(fill="x", padx=px(14), pady=px(10))
            etichetta(q, t, 13, colore=C["muted"], bg=C["tint2"]).pack(anchor="w")
            if i == 2:
                self.e_fine = tk.Entry(q, font=F(18, "bold"), width=6, relief="flat", highlightthickness=1,
                                       highlightbackground="#b8c4cf", highlightcolor=C["primary"], fg=C["dark"])
                self.e_fine.insert(0, v); self.e_fine.pack(anchor="w")
            else:
                etichetta(q, v, 18, "bold", colore=C["dark"], bg=C["tint2"]).pack(anchor="w")
        etichetta(sc, "ⓘ  Nulla viene chiuso in automatico. Dopo l'ora di fine scelta quella giornata risulterà "
                      "«sessione chiusa»: le fasce successive non sono contate. Puoi cambiare l'ora proposta.", 13.5,
                  wrap=580).pack(anchor="w", padx=px(28))
        msg = etichetta(sc, "", 13, colore=C["err"])
        b = tk.Frame(sc, bg="white"); b.pack(fill="x", padx=px(28), pady=(px(16), px(6)))
        tz = dt.datetime.fromisoformat(pr["avvio"]).tzinfo

        def chiudi(genera):
            try:
                q = dt.datetime.combine(dt.date.fromisoformat(g), dt.time.fromisoformat(self.e_fine.get().strip()), tz)
            except ValueError:
                msg.configure(text="Ora non valida: usa il formato hh:mm."); msg.pack(anchor="w", padx=px(28))
                return
            if q < dt.datetime.fromisoformat(pr["avvio"]):
                msg.configure(text="L'ora di fine non può essere prima dell'avvio."); msg.pack(anchor="w", padx=px(28))
                return
            self.azione_chiudi(q, genera)
        Bottone(b, f"■  Chiudi la giornata di {gs[0]}", lambda: chiudi(True)).pack(side="right")
        Bottone(b, "Rivedi prima i dati", lambda: chiudi(False), "secondario").pack(side="right", padx=px(12))
        Bottone(b, "Più tardi", self.chiudi_velo, "link").pack(side="left")
        etichetta(sc, "La giornata di oggi la avvii tu con «Avvia giornata», come sempre.", 12.5,
                  colore=C["muted"]).pack(anchor="w", padx=px(28), pady=(px(4), px(18)))

    # ============================================================================== informazioni
    def mostra_informazioni(self):
        sc = self.apri_velo(760)
        self._testata_modale(sc, "Informazioni", "Rendiconto SW", f"Versione {VERSIONE_APP} · resoconto della giornata "
                             "di lavoro agile", icona="stemma", chiudi=self.chiudi_velo)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(28), pady=px(16))
        dx = tk.Frame(p, bg="white"); dx.pack(side="right", fill="both", padx=(px(22), 0), anchor="n")
        sx = tk.Frame(p, bg="white"); sx.pack(side="left", fill="both", expand=True, anchor="n")
        etichetta(sx, "Sviluppato da Luca Accorsi", 14, "semi").pack(anchor="w")
        etichetta(sx, "© 2026 Luca Accorsi", 14).pack(anchor="w")
        etichetta(sx, "LICENZA", 12, "bold", colore=C["primary"]).pack(anchor="w", pady=(px(14), px(4)))
        lb = tk.Frame(sx, bg=C["tint2"]); lb.pack(fill="x")
        etichetta(lb, "Software libero e open source, distribuito con licenza EUPL-1.2 (European Union Public "
                      "Licence 1.2). Il programma è fornito «così com'è», senza garanzie di alcun tipo, esplicite o "
                      "implicite, nei limiti consentiti dalla legge.", 13, bg=C["tint2"], wrap=300).pack(padx=px(12), pady=px(10))
        etichetta(sx, "CONTATTI", 12, "bold", colore=C["primary"]).pack(anchor="w", pady=(px(14), px(4)))
        etichetta(sx, f"Sistemi Informativi – {NOME_ENTE}", 13.5).pack(anchor="w")
        etichetta(sx, ASSISTENZA, 13.5, "semi", colore=C["primary"]).pack(anchor="w")
        etichetta(dx, "COMPONENTI DI TERZE PARTI", 12, "bold", colore=C["primary"]).pack(anchor="w", pady=(0, px(4)))
        for a, b in TERZE_PARTI:
            r = tk.Frame(dx, bg="white"); r.pack(fill="x")
            tk.Frame(dx, bg=C["line"], height=1).pack(fill="x")
            etichetta(r, b, 12.5, colore=C["muted"]).pack(side="right")
            etichetta(r, a, 12.5).pack(side="left", padx=(0, px(14)))
        try:
            from aggregatore import __version__ as va
            mv = self.s.mappa().versione
        except Exception:   # noqa: BLE001
            va, mv = "?", "?"
        etichetta(dx, f"Aggregatore {va} · mappatura {mv} · informativa {VERSIONE_INFORMATIVA} · modalità "
                      f"«{self.s.imp['modalita']}». Nome e logo dell'Ente sono dell'Ente.", 12,
                  colore=C["muted"], wrap=360).pack(anchor="w", pady=(px(8), 0))
        b = tk.Frame(sc, bg="white"); b.pack(fill="x", padx=px(28), pady=(0, px(20)))
        Bottone(b, "Chiudi", self.chiudi_velo).pack(side="right")

        def copia():
            self.clipboard_clear()
            self.clipboard_append(f"Rendiconto SW {VERSIONE_APP} · aggregatore {va} · mappatura {mv} · informativa "
                                  f"{VERSIONE_INFORMATIVA} · modalità {self.s.imp['modalita']}")
        Bottone(b, "Copia le informazioni", copia, "secondario", dim=13.5).pack(side="left")

    # ========================================================================= salvati / aiuto
    def vai_salvati(self):
        self._scheda_attiva("salvati")
        self._pulisci()
        w = self._contenitore()
        sc = Scheda(w); sc.pack(fill="both", expand=True)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(24), pady=px(18))
        etichetta(p, "Resoconti salvati", 20, "bold", colore=C["dark"]).pack(anchor="w")
        etichetta(p, f"Cartella dei PDF: {percorso_breve(self.s.imp['cartella_pdf'])}", 13, colore=C["muted"]).pack(anchor="w")
        da = self.s.giorni_da_confermare()
        st = self.s.stato()
        if st["fase"] == "chiusura_da_completare":
            tk.Frame(p, bg=C["line"], height=1).pack(fill="x", pady=(px(10), 0))
            r = tk.Frame(p, bg="white"); r.pack(fill="x", pady=(px(8), 0))
            etichetta(r, data_lunga(st["giorno"]).capitalize(), 15, "semi").pack(side="left")
            badge(r, "chiusura non completata", "err").pack(side="left", padx=px(12))
            Bottone(r, "Riprova la chiusura", self.azione_riprova, "link", dim=13.5).pack(side="right")
        for g in da:
            tk.Frame(p, bg=C["line"], height=1).pack(fill="x", pady=(px(10), 0))
            r = tk.Frame(p, bg="white"); r.pack(fill="x", pady=(px(8), 0))
            etichetta(r, data_lunga(g).capitalize(), 15, "semi").pack(side="left")
            badge(r, "da confermare", "warn").pack(side="left", padx=px(12))
            Bottone(r, "Rivedi e conferma", lambda x=g: self.vai_revisione(x), "link", dim=13.5).pack(side="right")
        el = self.s.resoconti_salvati()
        if not el and not da:
            etichetta(p, "Non ci sono ancora resoconti salvati su questo computer.", 14.5, colore=C["muted"]).pack(
                anchor="w", pady=px(14))
        for r in el[:30]:
            self._riga_resoconto(p, r)

    def vai_aiuto(self):
        self._scheda_attiva("aiuto")
        self._pulisci()
        w = self._contenitore()
        sc = Scheda(w); sc.pack(fill="both", expand=True)
        p = tk.Frame(sc, bg="white"); p.pack(fill="x", padx=px(26), pady=px(20))
        etichetta(p, "Aiuto", 20, "bold", colore=C["dark"]).pack(anchor="w", pady=(0, px(8)))
        passi = [("1. Avvia giornata", "quando inizi a lavorare. Nessun avvio automatico."),
                 ("2. Pausa / Riprendi", "durante la pausa non viene contato nulla."),
                 ("3. Aggiungi attività", "riunioni, telefonate, lavoro su carta, sopralluoghi, formazione "
                                          f"(descrizione fino a {MAX_DESCRIZIONE} caratteri)."),
                 ("4. Chiudi giornata", "leggo i dati della giornata e preparo la sintesi con l'assistente locale."),
                 ("5. Revisione", "i dati automatici non si modificano: se uno non torna, «Segnala» e scrivi una nota. "
                                  f"Puoi riscrivere la sintesi fino a {MAX_RISCRITTURE} volte o modificarla a mano; "
                                  f"osservazioni fino a {MAX_OSSERVAZIONI} caratteri."),
                 ("6. Ho verificato la sintesi", "obbligatorio. Poi «Conferma e crea il PDF»: il resoconto viene sigillato.")]
        for a, b in passi:
            r = tk.Frame(p, bg="white"); r.pack(fill="x", pady=px(4))
            etichetta(r, a, 14.5, "semi", width=24).pack(side="left", anchor="n")
            etichetta(r, b, 14, colore=C["muted"], wrap=640).pack(side="left")
        bb = tk.Frame(p, bg="white"); bb.pack(fill="x", pady=(px(18), 0))
        Bottone(bb, "Verifica un resoconto…", self.apri_verificatore, "secondario").pack(side="left")
        Bottone(bb, "Cosa viene registrato", self.mostra_cosa, "secondario").pack(side="left", padx=px(12))
        etichetta(p, f"Assistenza: {ASSISTENZA}", 14, "semi", colore=C["primary"]).pack(anchor="w", pady=(px(18), 0))

    def apri_verificatore(self):
        from verificatore.gui import Verificatore
        return Verificatore(self, chiavi=[os.path.join(self.s.p.base, "chiave")])


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="RendicontoSW")
    ap.add_argument("--base", help="cartella dei dati (predefinita %%LOCALAPPDATA%%\\RendicontoSW)")
    ap.add_argument("--smoke-giornata", metavar="CARTELLA",
                    help="collaudo senza intervento in CARTELLA (nuova): avvia → attività → chiudi → PDF, con i "
                         "pulsanti veri della finestra nascosta; registri finti")
    ap.add_argument("--esito", help="file JSON con l'esito del collaudo (--smoke-giornata)")
    ap.add_argument("--senza-finestra", action="store_true", help="collaudo con le funzioni dei pulsanti, senza Tk")
    ap.add_argument("--testo-standard", action="store_true", help="collaudo senza assistente locale")
    ap.add_argument("--diagnostica-ai", metavar="FILE", help="scrive la sola diagnostica locale AI, senza avviare il motore")
    ns = ap.parse_args(argv)
    if ns.diagnostica_ai:
        import json
        with open(ns.diagnostica_ai, "w", encoding="utf-8") as f:
            json.dump(Servizio(ns.base).disponibilita_ai(), f, ensure_ascii=False, indent=2)
        return 0
    if ns.smoke_giornata:
        from .smoke import esegui
        return esegui(ns.smoke_giornata, ns.esito, finestra=not ns.senza_finestra, testo_standard=ns.testo_standard)
    App(Servizio(ns.base)).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
