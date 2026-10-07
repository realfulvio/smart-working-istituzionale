"""Accesso alle API di Windows con ctypes (nessun privilegio di amministratore richiesto).

- GetLastInputInfo: istante dell'ultimo input della sessione (solo il contatore, nessun dato sull'input);
- GetForegroundWindow → processo → QueryFullProcessImageNameW: si tiene **solo** il nome dell'eseguibile;
  il titolo della finestra non viene mai letto;
- WTSRegisterSessionNotification + WM_POWERBROADCAST + WM_TIMECHANGE su una finestra nascosta;
- PDH, contatori «SMB Client Shares(*)» per condivisione (richieste di dati e di metadati, valori grezzi cumulativi),
  filtrati sulle sole unità di rete della sessione dell'utente (WNetGetConnection) – vedi collector/smb.py;
- GetProcessTimes / GetProcessMemoryInfo per misurare il consumo del collector stesso.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys

if sys.platform != "win32":  # pragma: no cover - modulo solo Windows
    raise ImportError("collector.win richiede Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
WM_TIMER, WM_CLOSE, WM_DESTROY = 0x0113, 0x0010, 0x0002
WM_QUERYENDSESSION, WM_ENDSESSION = 0x0011, 0x0016
WM_POWERBROADCAST, WM_TIMECHANGE, WM_WTSSESSION_CHANGE = 0x0218, 0x001E, 0x02B1
NOTIFY_FOR_THIS_SESSION = 0
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, wt.LPVOID]
user32.SetTimer.restype = ctypes.c_size_t
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.DestroyWindow.argtypes = [wt.HWND]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
wtsapi32.WTSRegisterSessionNotification.argtypes = [wt.HWND, wt.DWORD]
wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wt.HWND]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GetCurrentProcess.restype = wt.HANDLE
kernel32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
kernel32.GetModuleHandleW.restype = wt.HMODULE
psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), wt.DWORD]


# ------------------------------------------------------------------------------------------- letture
def ultimo_input() -> int | None:
    lii = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    return int(lii.dwTime) if user32.GetLastInputInfo(ctypes.byref(lii)) else None


def exe_primo_piano() -> str:
    """Solo il nome dell'eseguibile in primo piano (es. WINWORD.EXE); "" se non leggibile."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return ""
        return os.path.basename(buf.value).upper()     # il percorso viene scartato subito
    finally:
        kernel32.CloseHandle(h)


def ram_gb() -> float | None:
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    return round(m.ullTotalPhys / 1024 ** 3, 1) if kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None


def consumo_processo() -> dict:
    """CPU (secondi utente+kernel) e memoria del processo corrente."""
    c, e, k, u = (wt.FILETIME() for _ in range(4))
    kernel32.GetProcessTimes(kernel32.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(k),
                             ctypes.byref(u))
    ft = lambda f: ((f.dwHighDateTime << 32) | f.dwLowDateTime) / 1e7
    pmc = PROCESS_MEMORY_COUNTERS_EX()
    pmc.cb = ctypes.sizeof(pmc)
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return {"cpu_s": round(ft(k) + ft(u), 3), "ws_mb": round(pmc.WorkingSetSize / 2 ** 20, 1),
            "picco_ws_mb": round(pmc.PeakWorkingSetSize / 2 ** 20, 1),
            "privata_mb": round(pmc.PrivateUsage / 2 ** 20, 1)}


def tipo_postazione() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Volatile Environment") as k:
            i = 0
            while True:
                name = winreg.EnumValue(k, i)[0]
                if name.startswith("ViewClient_"):
                    return "vdi"                         # Omnissa/VMware Horizon
                i += 1
    except OSError:
        pass
    if os.environ.get("SESSIONNAME", "").upper().startswith("RDP"):
        return "vdi"
    try:                                                 # macchina virtuale (es. VMware, Hyper-V, KVM)
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
            prodotto = str(winreg.QueryValueEx(k, "SystemProductName")[0]).lower()
        if any(x in prodotto for x in ("acloud", "vmware", "virtual machine", "kvm", "qemu", "virtualbox", "hvm")):
            return "vdi"
    except OSError:
        pass
    return "fisica"


class ContatoreSMB:
    """Operazioni SMB della sola sessione dell'utente (M8): istanze PDH per condivisione filtrate sulle unità di rete
    dell'utente; ``leggi()`` restituisce un totale cumulativo o ``None`` (dato non disponibile, es. più sessioni).
    I nomi delle condivisioni restano in memoria: nel registro finisce solo il numero di operazioni per fascia."""

    CONTATORI = (r"\SMB Client Shares(*)\Data Requests/sec", r"\SMB Client Shares(*)\Metadata Requests/sec")

    class _RAW(ctypes.Structure):
        _fields_ = [("CStatus", wt.DWORD), ("TimeStamp", wt.FILETIME), ("FirstValue", ctypes.c_longlong),
                    ("SecondValue", ctypes.c_longlong), ("MultiCount", wt.DWORD)]

    class _ITEM(ctypes.Structure):
        pass

    _ITEM._fields_ = [("szName", wt.LPWSTR), ("RawValue", _RAW)]

    class _SESS(ctypes.Structure):
        _fields_ = [("SessionId", wt.DWORD), ("pWinStationName", wt.LPWSTR), ("State", ctypes.c_int)]

    def __init__(self):
        from .smb import Accumulatore
        self.ok, self.acc, self.c = False, Accumulatore(), []
        try:
            self.pdh = ctypes.WinDLL("pdh")
            self.mpr = ctypes.WinDLL("mpr")
            self.q = wt.HANDLE()
            if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.q)) != 0:
                return
            for percorso in self.CONTATORI:
                c = wt.HANDLE()
                if self.pdh.PdhAddEnglishCounterW(self.q, percorso, 0, ctypes.byref(c)) != 0:
                    return
                self.c.append(c)
            self.ok = self.leggi() is not None
        except OSError:
            self.ok = False

    def _valori(self) -> dict[str, int] | None:
        if self.pdh.PdhCollectQueryData(self.q) != 0:
            return None
        tot: dict[str, int] = {}
        for c in self.c:
            size, n = wt.DWORD(0), wt.DWORD(0)
            self.pdh.PdhGetRawCounterArrayW(c, ctypes.byref(size), ctypes.byref(n), None)
            if not size.value:
                continue
            buf = (ctypes.c_byte * size.value)()
            if self.pdh.PdhGetRawCounterArrayW(c, ctypes.byref(size), ctypes.byref(n), buf) != 0:
                return None
            arr = ctypes.cast(buf, ctypes.POINTER(self._ITEM))
            for i in range(n.value):
                it = arr[i]
                if it.szName and it.RawValue.CStatus in (0, 1):
                    tot[it.szName] = tot.get(it.szName, 0) + int(it.RawValue.FirstValue)
        return tot

    def _connessioni(self) -> list[str]:
        out = []
        for lettera in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            buf, n = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
            if self.mpr.WNetGetConnectionW(f"{lettera}:", buf, ctypes.byref(n)) == 0:
                out.append(buf.value)
        return out

    def _sessioni(self) -> list[tuple[int, int]]:
        p, n = ctypes.POINTER(self._SESS)(), wt.DWORD()
        if not wtsapi32.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(p), ctypes.byref(n)):
            return []
        try:
            return [(p[i].SessionId, p[i].State) for i in range(n.value)]
        finally:
            wtsapi32.WTSFreeMemory(p)

    def leggi(self) -> int | None:
        valori = self._valori()
        if valori is None:
            return None
        return self.acc.aggiorna(valori, self._connessioni(), self._sessioni())


# ---------------------------------------------------------------------------------- finestra nascosta
class Finestra:
    """Finestra di primo livello mai mostrata: riceve notifiche WTS, alimentazione, cambio ora e il timer."""

    def __init__(self, on_timer, on_wts, on_power, on_timechange, on_fine, intervallo_ms: int):
        self._cb = (on_timer, on_wts, on_power, on_timechange, on_fine)
        self._proc = WNDPROC(self._wndproc)          # riferimento tenuto vivo
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = "RendicontoSWCollector"
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "Rendiconto SW collector", 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        if not self.hwnd:
            raise OSError(ctypes.get_last_error(), "CreateWindowExW")
        self.wts_ok = bool(wtsapi32.WTSRegisterSessionNotification(self.hwnd, NOTIFY_FOR_THIS_SESSION))
        user32.SetTimer(self.hwnd, 1, intervallo_ms, None)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        on_timer, on_wts, on_power, on_timechange, on_fine = self._cb
        try:
            if msg == WM_TIMER:
                on_timer()
            elif msg == WM_WTSSESSION_CHANGE:
                on_wts(int(wparam))
            elif msg == WM_POWERBROADCAST:
                on_power(int(wparam))
                return 1
            elif msg == WM_TIMECHANGE:
                on_timechange()
            elif msg == WM_QUERYENDSESSION:
                return 1
            elif msg == WM_ENDSESSION:
                if wparam:
                    on_fine("spegnimento")
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception as e:  # mai far cadere il ciclo dei messaggi
            on_fine("errore:" + type(e).__name__)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def ciclo(self):
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self.wts_ok:
            wtsapi32.WTSUnRegisterSessionNotification(self.hwnd)

    def chiudi(self):
        user32.DestroyWindow(self.hwnd)
