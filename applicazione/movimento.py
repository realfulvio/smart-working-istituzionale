"""Decorazioni Tk: un solo clock <=30 fps, niente dati o numeri animati."""
import ctypes
import math
import sys
import time
import tkinter as tk

FPS = 30
INATTIVITA_S = 5

def windows_ridotto():
    if sys.platform != "win32":
        return True
    attivo = ctypes.c_int()
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(attivo), 0)
        return not bool(attivo.value) if ok else True
    except (AttributeError, OSError):
        return True

def mescola(a, b, n):
    a={"white":"#ffffff","black":"#000000"}.get(a,a)
    b={"white":"#ffffff","black":"#000000"}.get(b,b)
    n = min(1, max(0, n))
    return "#" + "".join(f"{round(int(a[i:i+2],16)*(1-n)+int(b[i:i+2],16)*n):02x}" for i in (1,3,5))

class Movimento:
    def __init__(self, root, preferenza="sistema", clock=time.monotonic):
        self.root, self.clock = root, clock
        self.preferenza = preferenza
        self.jobs = {}
        self.ultimo_input = clock()
        self.ultimo_frame = clock()
        self.timer = None
        self.frame = 0
        root.movimento = self
        for evento in ("<Motion>", "<KeyPress>", "<ButtonPress>", "<FocusIn>"):
            root.bind(evento, self.interazione, add="+")
        root.bind("<Destroy>", self._destroy, add="+")

    @property
    def ridotto(self):
        return self.preferenza == "ridotte" or (self.preferenza != "complete" and windows_ridotto())

    def interazione(self, _e=None):
        self.ultimo_input = self.clock()
        self._programma()

    def primo_piano(self):
        try:
            if not self.root.winfo_viewable():
                return False
            if sys.platform == "win32":
                u = ctypes.windll.user32
                nostro = u.GetAncestor(self.root.winfo_id(), 2)
                corrente = u.GetForegroundWindow()
                return corrente == nostro or u.GetWindow(corrente, 4) == nostro
            return self.root.focus_displayof() is not None
        except (tk.TclError, AttributeError, OSError):
            return False

    def abilita(self, preferenza):
        self.preferenza = preferenza
        for j in list(self.jobs.values()):
            if self.ridotto:
                self._applica(j, 1)
        if self.ridotto:
            self.jobs = {k:j for k,j in self.jobs.items() if j["continuo"]}
        self.interazione()

    def effetto(self, widget, aggiorna, durata=.18, continuo=False, ritardo=0, chiave=None):
        j = {"widget":widget,"fn":aggiorna,"durata":max(.034,durata),"continuo":continuo,"tempo":-ritardo}
        if self.ridotto:
            self._applica(j, 1)
            return
        self.jobs[chiave or (str(widget), id(aggiorna))] = j
        self._programma()

    def _applica(self, j, n):
        try:
            if j["widget"].winfo_exists():
                j["fn"](n)
                return True
        except tk.TclError:
            pass
        return False

    def _programma(self):
        if self.timer is None and self.jobs:
            self.ultimo_frame = self.clock()
            self.timer = self.root.after(34, self._tick)

    def _tick(self):
        self.timer = None
        now = self.clock()
        dt = min(.1, now-self.ultimo_frame)
        self.ultimo_frame = now
        actif = not self.ridotto and self.primo_piano() and now-self.ultimo_input < INATTIVITA_S
        for k,j in list(self.jobs.items()):
            if not j["widget"].winfo_exists():
                self.jobs.pop(k, None)
                continue
            if not actif:
                continue
            j["tempo"] += dt
            if j["tempo"] < 0:
                continue
            n = (j["tempo"] % j["durata"]) / j["durata"] if j["continuo"] else min(1,j["tempo"]/j["durata"])
            if not self._applica(j,n) or (not j["continuo"] and n >= 1):
                self.jobs.pop(k, None)
        if actif:
            self.frame += 1
        if self.jobs:
            self.timer = self.root.after(34 if actif else 250, self._tick)

    def _destroy(self, e):
        if e.widget == self.root and self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
            self.jobs.clear()

def gestore(widget):
    return getattr(widget.winfo_toplevel(), "movimento", None)

def progresso(master, colore, sfondo, shimmer=False):
    cv = tk.Canvas(master, height=14 if shimmer else 8, bg=sfondo, highlightthickness=0)
    cv.pack(fill="x", pady=6)
    fondo = cv.create_rectangle(0,2,300,6,fill=mescola(sfondo,colore,.1),outline="")
    luce = cv.create_rectangle(0,2,40,6,fill=mescola(sfondo,colore,.25 if shimmer else 1),outline="")
    def draw(n):
        w=max(80,cv.winfo_width());x=n*(w+80)-80
        cv.coords(fondo,0,2,w,10 if shimmer else 6)
        cv.coords(luce,x,2,x+80,10 if shimmer else 6)
    g=gestore(master)
    if g:g.effetto(cv,draw,1.4,continuo=True)
    else:draw(.5)
    return cv

def sigillo(cv, valido, colore):
    cv.delete("all")
    w=int(cv.cget("width"));h=int(cv.cget("height"))
    if valido:
        line=cv.create_line(w*.22,h*.5,w*.4,h*.7,w*.78,h*.28,fill=colore,width=4,capstyle="round",joinstyle="round")
        def draw(n):
            a=(w*.22,h*.5);b=(w*.4,h*.7);c=(w*.78,h*.28)
            if n < .4:cv.coords(line,*a,a[0]+(b[0]-a[0])*n/.4,a[1]+(b[1]-a[1])*n/.4)
            else:cv.coords(line,*a,*b,b[0]+(c[0]-b[0])*(n-.4)/.6,b[1]+(c[1]-b[1])*(n-.4)/.6)
        g=gestore(cv)
        if g:g.effetto(cv,draw,.4)
    else:
        text=cv.create_text(w/2,h/2,text="!",fill=colore,font=("Segoe UI",-30,"bold"))
        g=gestore(cv)
        if g:g.effetto(cv,lambda n:cv.coords(text,w/2+math.sin(n*math.pi*4)*3*(1-n),h/2),.22)
