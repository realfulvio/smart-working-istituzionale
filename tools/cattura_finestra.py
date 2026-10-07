"""Cattura di una finestra Tk per le schermate di documentazione (solo quella finestra, mai lo schermo intero).

Linux/display virtuale: ImageGrab sull'area della finestra. Windows: PrintWindow sulla finestra stessa, così la
cattura funziona anche con la sessione bloccata (lo schermo mostra la schermata di blocco, la finestra no) e non
può includere altre finestre aperte sopra.
"""
from __future__ import annotations

import sys


def cattura(win, path: str) -> None:
    win.update(); win.after(200); win.update_idletasks(); win.update()
    if sys.platform == "win32":
        _printwindow(int(win.wm_frame(), 16), path)
        return
    from PIL import ImageGrab
    x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)


def _printwindow(hwnd: int, path: str) -> None:
    import ctypes
    import ctypes.wintypes as wt

    from PIL import Image
    u, g = ctypes.windll.user32, ctypes.windll.gdi32

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]
    r = wt.RECT(); u.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    hdc = u.GetDC(hwnd); mem = g.CreateCompatibleDC(hdc); bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mem, bmp)
    try:
        # Il bitmap compatibile non inizializzato può contenere pixel precedenti.
        # Azzera sempre la superficie prima di far disegnare i controlli.
        g.PatBlt(mem, 0, 0, w, h, 0x00FF0062)  # WHITENESS
        if not u.PrintWindow(hwnd, mem, 1 | 2):          # PW_CLIENTONLY | PW_RENDERFULLCONTENT
            raise OSError("PrintWindow non riuscito")
        bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
        Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(path)
    finally:
        g.DeleteObject(bmp); g.DeleteDC(mem); u.ReleaseDC(hwnd, hdc)
