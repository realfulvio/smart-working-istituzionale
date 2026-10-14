"""Icona nell'area di notifica di Windows (accanto all'orologio) e istanza unica dell'interfaccia.

Con una giornata avviata, chiudere la finestra non chiude il programma: resta qui l'icona, con lo stato (attiva, in
pausa, nessuna giornata) e il menu Apri · Pausa/Riprendi · Chiudi giornata · Esci. L'icona NON raccoglie nulla:
la raccolta resta quella del processo avviato da «Avvia giornata»; l'icona la rende soltanto visibile e governabile.

Win32 con ctypes (nessuna dipendenza nuova), in un thread con la propria coda dei messaggi; i comandi del menu
arrivano all'interfaccia tramite la funzione ``al_comando`` (che li mette nella coda Tk, mai chiamate Tk da qui).
Le funzioni pure (stato dell'icona, suggerimento, voci del menu) sono separate e collaudabili senza Windows.
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading

CLASSE = "RendicontoSWAreaNotifica"
TITOLO_PROGRAMMA = "Resoconto lavoro agile"
ICONE = {"attiva": "tray_attiva.ico", "pausa": "tray_pausa.ico", "nessuna": "tray_nessuna.ico"}
AVVISO_CHIUSURA = ("La raccolta continua", "Hai chiuso la finestra, ma la giornata è in corso: la raccolta continua. "
                   "Riapri da qui, oppure usa il menu per Pausa o Chiudi giornata.")
AVVISO_CHIUSURA_PAUSA = ("La giornata è in pausa", "Hai chiuso la finestra: la giornata resta in pausa e non si "
                         "raccoglie nulla. Riapri da qui quando riprendi.")
AVVISO_RIAGGANCIO = ("Giornata ripresa", "La giornata avviata alle {ora} era ancora in corso: dopo il riavvio di "
                     "Windows la raccolta riprende da adesso. Pausa o Chiudi giornata dal menu di questa icona.")


# ------------------------------------------------------------------------------------------------ logica pura
def stato_icona(fase: str | None) -> str:
    return {"in_corso": "attiva", "in_pausa": "pausa"}.get(fase or "", "nessuna")


def suggerimento(st: dict) -> str:
    """Testo al passaggio del mouse (massimo 127 caratteri, limite di Windows)."""
    fase = st.get("fase")
    if fase == "in_corso":
        ora = (st.get("avvio") or "")[11:16]
        t = f"{TITOLO_PROGRAMMA} · giornata in corso" + (f" dalle {ora}" if ora else "")
        if st.get("modalita") == "collector" and not st.get("raccolta_attiva"):
            t += " · raccolta non attiva"
    elif fase == "in_pausa":
        ora = (st.get("pausa_dalle") or "")[11:16]
        t = f"{TITOLO_PROGRAMMA} · giornata in pausa" + (f" dalle {ora}" if ora else "")
    else:
        t = f"{TITOLO_PROGRAMMA} · nessuna giornata avviata"
    return t[:127]


def voci_menu(fase: str | None) -> list:
    """[(comando, testo, attiva, predefinita) | None per il separatore]."""
    aperta = fase in ("in_corso", "in_pausa")
    pausa = ("riprendi", "Riprendi") if fase == "in_pausa" else ("pausa", "Pausa")
    return [("apri", f"Apri {TITOLO_PROGRAMMA}", True, True),
            None,
            (pausa[0], pausa[1], aperta, False),
            ("chiudi_giornata", "Chiudi giornata…", aperta, False),
            None,
            ("esci", "Esci…", True, False)]


def nome_mutex(base: str) -> str:
    h = hashlib.sha1(os.path.normcase(os.path.abspath(base)).encode("utf-8")).hexdigest()[:16]
    return f"Local\\RendicontoSW_Interfaccia_{h}"


# ------------------------------------------------------------------------------------------------ Win32
WM_DESTROY, WM_CLOSE, WM_NULL, WM_COMMAND = 0x0002, 0x0010, 0x0000, 0x0111
WM_CONTEXTMENU, WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x007B, 0x0202, 0x0203, 0x0205
WM_APP = 0x8000
WM_ICONA = WM_APP + 1          # richiamo dell'icona (Shell_NotifyIcon)
WM_RICHIESTA = WM_APP + 2      # da un'altra istanza: «apri»
WM_APPLICA = WM_APP + 3        # dal thread Tk: applica stato/avviso in attesa
NIN_SELECT, NIN_KEYSELECT, NIN_BALLOONUSERCLICK = 0x0400, 0x0401, 0x0405
NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x01, 0x02, 0x04, 0x10, 0x80
NIIF_INFO, NIIF_NOSOUND = 0x01, 0x10
NOTIFYICON_VERSION_4 = 4
MF_STRING, MF_SEPARATOR, MF_GRAYED = 0x0000, 0x0800, 0x0001
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x0002, 0x0100, 0x0080
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
SM_CXSMICON, SM_CYSMICON = 49, 50
ERROR_ALREADY_EXISTS = 183


def _win32():
    import ctypes
    import ctypes.wintypes as wt
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                    ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                    ("lpszClassName", wt.LPCWSTR)]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
                    ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                    ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                    ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                    ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]

    user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wt.ATOM
    user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
    user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
    user32.CreateWindowExW.restype = wt.HWND
    user32.DestroyWindow.argtypes = [wt.HWND]
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wt.UINT
    user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.LoadImageW.restype = wt.HANDLE
    user32.DestroyIcon.argtypes = [wt.HICON]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.CreatePopupMenu.restype = wt.HMENU
    user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
    user32.SetMenuDefaultItem.argtypes = [wt.HMENU, wt.UINT, wt.UINT]
    user32.TrackPopupMenuEx.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID]
    user32.TrackPopupMenuEx.restype = wt.BOOL
    user32.DestroyMenu.argtypes = [wt.HMENU]
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
    user32.FindWindowW.restype = wt.HWND
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.AllowSetForegroundWindow.argtypes = [wt.DWORD]
    shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wt.BOOL
    kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wt.HMODULE
    kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE
    return {"ctypes": ctypes, "wt": wt, "user32": user32, "shell32": shell32, "kernel32": kernel32,
            "WNDPROC": WNDPROC, "WNDCLASSW": WNDCLASSW, "NID": NOTIFYICONDATAW}


_MUTEX = None


def prima_istanza(base: str) -> bool:
    """True se questa è l'unica interfaccia aperta per la cartella dati ``base`` (mutex di sessione)."""
    global _MUTEX
    if sys.platform != "win32":
        return True
    w = _win32()
    h = w["kernel32"].CreateMutexW(None, False, nome_mutex(base))
    gia = w["ctypes"].get_last_error() == ERROR_ALREADY_EXISTS
    if h and not gia:
        _MUTEX = h                                   # resta aperto fino all'uscita del processo
    return bool(h) and not gia


def chiedi_apertura() -> bool:
    """Chiede all'interfaccia già aperta di mostrare la finestra. True se l'ha trovata."""
    if sys.platform != "win32":
        return False
    w = _win32()
    hwnd = w["user32"].FindWindowW(CLASSE, None)
    if not hwnd:
        return False
    pid = w["wt"].DWORD(0)
    w["user32"].GetWindowThreadProcessId(hwnd, w["ctypes"].byref(pid))
    if pid.value:
        w["user32"].AllowSetForegroundWindow(pid.value)    # la finestra riaperta può passare in primo piano
    return bool(w["user32"].PostMessageW(hwnd, WM_RICHIESTA, 1, 0))


class AreaNotifica:
    """Icona nell'area di notifica. ``al_comando(nome)`` riceve 'apri', 'pausa', 'riprendi', 'chiudi_giornata',
    'esci' dal thread dell'icona: deve solo accodare (es. nella coda Tk)."""

    def __init__(self, al_comando, icone: dict[str, str]):
        self.al_comando = al_comando
        self.icone = icone
        self._stato = {"fase": None}
        self._avviso = None
        self._lock = threading.Lock()
        self._pronta = threading.Event()
        self.hwnd = None
        self.visibile = False                        # icona effettivamente aggiunta all'area di notifica
        self._thread = None
        self._hicon = {}

    # ---------------------------------------------------------------- API (thread dell'interfaccia)
    def avvia(self, st: dict | None = None, attesa_s: float = 3.0) -> bool:
        if sys.platform != "win32":
            return False
        if st:
            self._stato = dict(st)
        self._thread = threading.Thread(target=self._ciclo, name="area-notifica", daemon=True)
        self._thread.start()
        self._pronta.wait(attesa_s)
        return self.visibile

    def aggiorna(self, st: dict) -> None:
        with self._lock:
            self._stato = dict(st)
        self._posta(WM_APPLICA)

    def avviso(self, titolo: str, testo: str) -> None:
        with self._lock:
            self._avviso = (titolo[:63], testo[:255])
        self._posta(WM_APPLICA)

    def chiudi(self) -> None:
        self._posta(WM_CLOSE)
        if self._thread is not None:
            self._thread.join(2.0)

    def _posta(self, msg):
        if self.hwnd:
            self._w["user32"].PostMessageW(self.hwnd, msg, 0, 0)

    # ---------------------------------------------------------------- thread dell'icona
    def _ciclo(self):
        try:
            self._w = w = _win32()
            u = w["user32"]
            self._proc = w["WNDPROC"](self._wndproc)     # riferimento tenuto vivo
            hinst = w["kernel32"].GetModuleHandleW(None)
            wc = w["WNDCLASSW"]()
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = CLASSE
            u.RegisterClassW(w["ctypes"].byref(wc))
            self._msg_taskbar = u.RegisterWindowMessageW("TaskbarCreated")
            # finestra di primo livello mai mostrata (non «message-only»: deve ricevere TaskbarCreated)
            self.hwnd = u.CreateWindowExW(0, CLASSE, TITOLO_PROGRAMMA, 0, 0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                return
            self._aggiungi()
        finally:
            self._pronta.set()
        msg = w["wt"].MSG()
        while u.GetMessageW(w["ctypes"].byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(w["ctypes"].byref(msg))
            u.DispatchMessageW(w["ctypes"].byref(msg))
        for h in self._hicon.values():
            u.DestroyIcon(h)
        u.UnregisterClassW(CLASSE, hinst)

    def _icona(self, stato):
        if stato not in self._hicon:
            u = self._w["user32"]
            cx, cy = u.GetSystemMetrics(SM_CXSMICON), u.GetSystemMetrics(SM_CYSMICON)
            self._hicon[stato] = u.LoadImageW(None, str(self.icone[stato]), IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
        return self._hicon[stato]

    def _dati(self, flags):
        w = self._w
        d = w["NID"]()
        d.cbSize = w["ctypes"].sizeof(d)
        d.hWnd = self.hwnd
        d.uID = 1
        d.uFlags = flags
        return d

    def _aggiungi(self):
        with self._lock:
            st = dict(self._stato)
        d = self._dati(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        d.uCallbackMessage = WM_ICONA
        d.hIcon = self._icona(stato_icona(st.get("fase")))
        d.szTip = suggerimento(st)
        sh = self._w["shell32"]
        self.visibile = bool(sh.Shell_NotifyIconW(NIM_ADD, self._w["ctypes"].byref(d)))
        if self.visibile:
            d.uVersion = NOTIFYICON_VERSION_4
            sh.Shell_NotifyIconW(NIM_SETVERSION, self._w["ctypes"].byref(d))

    def _applica(self):
        with self._lock:
            st, avv, self._avviso = dict(self._stato), self._avviso, None
        if not self.visibile:
            self._aggiungi()
            if not self.visibile:
                return
        d = self._dati(NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        d.hIcon = self._icona(stato_icona(st.get("fase")))
        d.szTip = suggerimento(st)
        if avv:
            d.uFlags |= NIF_INFO
            d.szInfoTitle, d.szInfo = avv
            d.dwInfoFlags = NIIF_INFO | NIIF_NOSOUND
        self._w["shell32"].Shell_NotifyIconW(NIM_MODIFY, self._w["ctypes"].byref(d))

    def _menu(self):
        w, u = self._w, self._w["user32"]
        with self._lock:
            fase = self._stato.get("fase")
        voci = voci_menu(fase)
        m = u.CreatePopupMenu()
        ids = {}
        for i, v in enumerate(voci, start=1):
            if v is None:
                u.AppendMenuW(m, MF_SEPARATOR, 0, None)
                continue
            cmd, testo, attiva, predefinita = v
            ids[i] = cmd
            u.AppendMenuW(m, MF_STRING | (0 if attiva else MF_GRAYED), i, testo)
            if predefinita:
                u.SetMenuDefaultItem(m, i, 0)
        pt = w["wt"].POINT()
        u.GetCursorPos(w["ctypes"].byref(pt))
        u.SetForegroundWindow(self.hwnd)             # senza, il menu non si chiude cliccando altrove
        scelta = u.TrackPopupMenuEx(m, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, self.hwnd, None)
        u.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        u.DestroyMenu(m)
        if scelta in ids:
            self.al_comando(ids[scelta])

    def _wndproc(self, hwnd, msg, wparam, lparam):
        u = self._w["user32"]
        try:
            if msg == WM_ICONA:
                evento = lparam & 0xFFFF
                if evento in (WM_CONTEXTMENU, WM_RBUTTONUP):
                    self._menu()
                elif evento in (NIN_SELECT, NIN_KEYSELECT, WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_BALLOONUSERCLICK):
                    self.al_comando("apri")
                return 0
            if msg == WM_RICHIESTA:
                self.al_comando("apri")
                return 0
            if msg == WM_APPLICA:
                self._applica()
                return 0
            if msg == self._msg_taskbar:              # Esplora risorse riavviato: l'icona va aggiunta di nuovo
                self.visibile = False
                self._aggiungi()
                return 0
            if msg == WM_CLOSE:
                u.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                d = self._dati(0)
                self._w["shell32"].Shell_NotifyIconW(NIM_DELETE, self._w["ctypes"].byref(d))
                self.visibile = False
                self.hwnd = None
                u.PostQuitMessage(0)
                return 0
        except Exception:   # noqa: BLE001 - mai far cadere la coda dei messaggi
            return 0
        return u.DefWindowProcW(hwnd, msg, wparam, lparam)
