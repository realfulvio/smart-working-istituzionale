from pathlib import Path
from resoconto import tokens, ente


def test_coppie_token_contrastate_e_oro_con_testo_scuro():
    assert all(r["valido"] for r in tokens.verifica_contrasti())
    t = tokens.carica()
    assert tokens.contrasto(t["surface"], t["stemma-gold"]) < 4.5
    assert t["stemma-blue"].startswith("#")
    assert tokens.contrasto(t["primary-action"], t["surface"]) >= 3


def test_ente_font_locali_e_licenze():
    root = Path(__file__).resolve().parents[1]
    e = ente.carica()
    assert e["nome"] and e["nome"] != "Ente"
    assert e["colori"]["primario"] == tokens.carica()["primary"].lower()
    assert Path(e["logo"]).is_file()
    from PIL import Image
    assert Image.open(e["logo"]).width == Image.open(e["logo"]).height
    font = root / "applicazione" / "assets" / "fonts"
    assert (font / "TitilliumWeb-Regular.ttf").exists()
    assert (font / "OFL-TitilliumWeb.txt").exists()
    assert (font / "LICENSE-RobotoMono.txt").exists()


def test_contrasti_effettivi_stati_e_pulsanti():
    from resoconto.formati import COLORI_STATO, TESTO_SU_STATO
    from applicazione.tema import Bottone, C
    for stato, fondo in COLORI_STATO.items():
        assert tokens.contrasto(TESTO_SU_STATO[stato], fondo) >= 4.5
    for stile, (bg, fg, bordo, hover) in Bottone.STILI.items():
        assert tokens.contrasto(fg, bg or C["white"]) >= 4.5
        if hover:
            assert tokens.contrasto(fg, hover) >= 4.5
