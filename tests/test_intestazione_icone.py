"""5.0.2 – logo nell'intestazione (ritaglio solo d'interfaccia, mai ingrandito), icona della finestra e motore AI
(template Qwen3.5 e rimozione del ragionamento). Solo dati e immagini sintetici."""
import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from redattore import motore

RADICE = Path(__file__).resolve().parents[1]


def _ente_con_logo(tmp_path, ritaglio=None, lato=300):
    logo = tmp_path / "logo.png"
    im = Image.new("RGBA", (lato, lato), (255, 255, 255, 255))
    for x in range(lato // 3, 2 * lato // 3):                  # «simbolo» in alto, «scritta» in basso
        for y in range(lato // 10, lato // 2):
            im.putpixel((x, y), (0, 90, 160, 255))
    im.save(logo)
    cfg = {"nome": "Ente di prova", "logo": "logo.png"}
    if ritaglio is not None:
        cfg["ritaglio_logo_interfaccia"] = ritaglio
    (tmp_path / "ente.json").write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path / "ente.json", logo


@pytest.fixture
def ente_finto(monkeypatch):
    from resoconto import ente

    def usa(percorso):
        monkeypatch.setattr(ente, "_cache", ente.carica(str(percorso)))
    yield usa


def test_ritaglio_letto_solo_se_valido(tmp_path):
    from resoconto import ente
    for valore, atteso in (([10, 20, 110, 220], [10, 20, 110, 220]), ([10, 20, 5, 220], None), ([1, 2, 3], None),
                           (["a", 0, 1, 1], None), (None, None)):
        p, _ = _ente_con_logo(tmp_path, valore)
        assert ente.carica(str(p))["ritaglio_logo_interfaccia"] == atteso, valore


def test_logo_interfaccia_ritaglia_e_non_ingrandisce(tmp_path, ente_finto):
    from applicazione import tema
    p, logo = _ente_con_logo(tmp_path, [80, 20, 220, 160])
    prima = hashlib.sha256(logo.read_bytes()).hexdigest()
    ente_finto(p)
    im = tema.logo_interfaccia(70)
    assert im.size == (70, 70)                                     # 140×140 ritagliato → 70 px, proporzioni intatte
    assert tema.logo_interfaccia(500).size == (140, 140)          # mai oltre l'originale
    assert hashlib.sha256(logo.read_bytes()).hexdigest() == prima  # il file (sigillato nei PDF) non cambia


def test_logo_interfaccia_senza_ritaglio_e_senza_logo(tmp_path, ente_finto):
    from applicazione import tema
    p, _ = _ente_con_logo(tmp_path)
    ente_finto(p)
    assert tema.logo_interfaccia(80).size == (80, 80)
    (tmp_path / "ente.json").write_text(json.dumps({"nome": "Ente"}), encoding="utf-8")
    ente_finto(tmp_path / "ente.json")
    assert tema.logo_interfaccia(80) is None


def test_icona_finestra_con_tutti_i_formati():
    import tkinter as tk
    from applicazione import tema
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk non disponibile")
    try:
        ico = str(RADICE / "applicazione/assets/icone/rendiconto.ico")
        tema.icone_finestra(root, ico)
        root.update()
        assert len(getattr(root, "_icone_finestra", [])) == 8      # applicate alla comparsa della finestra
        assert [f.width() for f in root._icone_finestra] == [256, 64, 48, 40, 32, 24, 20, 16]
    finally:
        root.destroy()


def test_app_e_verificatore_usano_lo_stesso_ingresso_per_le_icone():
    gui = (RADICE / "applicazione/gui.py").read_text(encoding="utf-8")
    ver = (RADICE / "verificatore/gui.py").read_text(encoding="utf-8")
    assert 'tema.icone_finestra(self, str(icona_edizione("rendiconto.ico")))' in gui
    assert 'tema.icone_finestra(self.win, str(icona("verifica.ico")))' in ver
    assert "iconphoto(True, self._ico)" not in gui                 # niente più logo ridotto come icona
    iss = (RADICE / "tools/pacchetto/setup/RendicontoSW.iss").read_text(encoding="utf-8-sig")
    assert "icone\\rendiconto.ico" in iss and "setup.ico" not in iss


# ------------------------------------------------------------------------------------------------ motore AI
def test_famiglia_dal_nome_del_file():
    assert motore.famiglia_qwen("Qwen3.5-2B-Q4_K_M.gguf") == "qwen35"
    assert motore.famiglia_qwen("Qwen_Qwen3.5-2B-Q4_K_M.gguf") == "qwen35"
    assert motore.famiglia_qwen("Qwen3-1.7B-Q4_K_M.gguf") == "qwen3"
    assert motore.famiglia_qwen("altro.gguf") is None


def test_template_qwen35_ufficiale_e_qwen3_invariato():
    p35 = motore.prompt_chatml("S", "U", True, ("D", "R"), qwen35=True)
    assert p35.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert "<|im_start|>assistant\nR<|im_end|>" in p35              # turno d'esempio senza blocco <think>
    p3 = motore.prompt_chatml("S", "U", True, ("D", "R"))
    assert "<|im_start|>assistant\n<think>\n\n</think>\n\nR<|im_end|>" in p3   # Qwen3: come nelle versioni 5.0.x


@pytest.mark.parametrize("uscita", ['<think>\nragiono\n</think>\n\n{"frasi": []}', '<think>senza fine {"frasi": []}',
                                    '</think>{"frasi": []}', '{"frasi": []}'])
def test_ragionamento_mai_nell_uscita(uscita):
    assert motore.togli_ragionamento(uscita) == '{"frasi": []}'


def test_llamacpp_riconosce_la_famiglia(tmp_path):
    m = motore.LlamaCpp("srv", str(tmp_path / "Qwen3.5-2B-Q4_K_M.gguf"))
    assert m.qwen3 and m.qwen35
    m = motore.LlamaCpp("srv", str(tmp_path / "Qwen3-1.7B-Q4_K_M.gguf"))
    assert m.qwen3 and not m.qwen35


def test_modello_ai_resta_qwen3_1_7b():
    """Decisione 5.0.2 (docs/verifiche/CONFRONTO_QWEN35_2B.md): Qwen3.5-2B non adottato."""
    from redattore import profilo
    assert profilo.MODELLI["AI-LIGHT"] == "Qwen3-1.7B-Q4_K_M.gguf"
