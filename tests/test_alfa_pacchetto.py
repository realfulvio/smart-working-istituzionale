"""Collaudo ALFA 05/10/2026: PyInstaller non vedeva i moduli di reportlab.graphics.barcode (caricati per nome) e
RendicontoSW.exe falliva alla creazione del PDF, VerificaRendiconto.exe non partiva."""
import os

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_build_app_raccoglie_i_sottomoduli_barcode_di_reportlab():
    with open(os.path.join(RADICE, "tools", "pacchetto", "build_app.ps1"), encoding="utf-8") as f:
        testo = f.read()
    assert '"--collect-submodules", "reportlab.graphics.barcode"' in testo


def test_i_moduli_barcode_usati_per_nome_esistono():
    from reportlab.graphics import barcode
    assert barcode.getCodes()          # importa code128, code39, qr, … come fa reportlab a runtime
    import reportlab.graphics.barcode.code128  # noqa: F401  (il modulo che mancava nel pacchetto ALFA)


def test_apri_pdf_via_explorer_con_cwd_e_path_pulito(monkeypatch, tmp_path):
    """Collaudo ALFA2 B7: os.startfile non bastava (Acrobat caricava VCRUNTIME da _internal).
    Si apre con explorer.exe, cwd = cartella del PDF, PATH senza cartelle dell'app."""
    import subprocess
    from applicazione import gui
    chiamate = []

    def fake_popen(args, **kw):
        chiamate.append((list(args), kw))
        class P:
            pid = 1
        return P()

    monkeypatch.setattr(gui.sys, "platform", "win32")
    monkeypatch.setattr(gui.sys, "frozen", True, raising=False)
    monkeypatch.setattr(gui.sys, "executable", str(tmp_path / "install" / "RendicontoSW.exe"), raising=False)
    monkeypatch.setattr(gui.subprocess, "Popen", fake_popen)
    pdf = tmp_path / "Rendiconti" / "Resoconto_2026-10-05_AAAA.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF")
    # PATH contiene la cartella app: deve essere rimossa dall'env passato a explorer
    monkeypatch.setenv("PATH", str(tmp_path / "install" / "_internal") + ";C:\\Windows\\System32")
    gui.apri_file(str(pdf))
    assert chiamate, "explorer non avviato"
    args, kw = chiamate[0]
    assert args[0].lower().endswith("explorer.exe") or args[0] == "explorer.exe"
    assert args[-1] == str(pdf) or args[-1].endswith("Resoconto_2026-10-05_AAAA.pdf")
    assert kw.get("cwd") == str(pdf.parent)
    env = kw.get("env") or {}
    path_env = (env.get("PATH") or "").lower()
    assert "_internal" not in path_env
    assert "system32" in path_env


def test_tutti_i_moduli_reportlab_usati_dal_pdf_si_importano():
    """Ogni import di reportlab usato da resoconto/pdf.py e dal barcode dinamico deve essere disponibile."""
    import importlib
    moduli = [
        "reportlab",
        "reportlab.graphics.renderPDF",
        "reportlab.graphics.barcode",
        "reportlab.graphics.barcode.code128",
        "reportlab.graphics.barcode.qr",
        "reportlab.graphics.shapes",
        "reportlab.lib.colors",
        "reportlab.lib.pagesizes",
        "reportlab.lib.styles",
        "reportlab.lib.units",
        "reportlab.lib.fonts",
        "reportlab.pdfbase",
        "reportlab.pdfbase.pdfmetrics",
        "reportlab.pdfbase.ttfonts",
        "reportlab.pdfgen",
        "reportlab.pdfgen.canvas",
        "reportlab.platypus",
    ]
    for m in moduli:
        importlib.import_module(m)
    from reportlab.graphics import barcode
    assert "QR" in barcode.getCodes() and "Code128" in barcode.getCodes()


def test_prepara_alfa_copia_solo_llama_server():
    with open(os.path.join(RADICE, "tools", "pacchetto", "prepara_alfa.ps1"), encoding="utf-8") as f:
        t = f.read()
    assert "llama-server.exe" in t
    assert "altriExe" in t or "non ammessi" in t
    assert "Solo llama-server" in t or "solo llama-server" in t.lower() or "Solo llama-server.exe" in t


def test_disinstalla_ferma_processi_propri_e_non_forza_terzi():
    with open(os.path.join(RADICE, "tools", "pacchetto", "disinstalla.ps1"), encoding="utf-8") as f:
        t = f.read()
    assert "Stop-ProcessiPropri" in t
    assert "ExecutablePath" in t
    assert "DISINSTALLAZIONE INCOMPLETA" in t or "Disinstallazione incompleta" in t
    assert "terzi" in t or "Acrobat" in t
    # collegamenti solo dopo rimozione/rinomina riuscita
    assert "Rimuovi-CollegamentiPerBersaglio" in t or "Resoconto lavoro agile.lnk" in t
    corpo = t.split("# --- inizio ---", 1)[-1]
    assert corpo.index("Rename-Item") < corpo.index("Rimuovi-CollegamentiPerBersaglio")


def test_smoke_frozen_script_presente():
    p = os.path.join(RADICE, "tools", "pacchetto", "smoke_frozen.ps1")
    assert os.path.isfile(p)
    t = open(p, encoding="utf-8").read()
    assert "VerificaRendiconto" in t and ("code128" in t.lower() or "barcode" in t.lower() or "Resoconto_" in t)
