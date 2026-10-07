"""Demo delle vere finestre Tk, con dati inventati; non cattura il desktop.

PrintWindow non registra l'alpha DWM dello splash: il PNG mostra un istante,
il GIF documenta movimento di schermate, chip e indicatore di preparazione.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--edizione", default="neutra")
    ap.add_argument("--uscita", default="docs/screenshots"); ns = ap.parse_args()
    os.environ["RENDICONTO_EDIZIONE"] = ns.edizione
    from PIL import Image
    from tools.schermate_documentazione import servizio, Orologio, T
    from tools.demo_documentazione import cattura_demo, installa_guardia_testi
    installa_guardia_testi()
    from collector import giornata, postazione
    from applicazione.gui import App
    postazione.rileva = lambda: {"nome_macchina":"PC-ESEMPIO", "tipo":"VDI", "sistema_operativo":"Windows 11 (ESEMPIO)", "processore":"CPU di esempio", "ram_gb":8}
    out=Path(ns.uscita); out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rsw_gif_") as tmp:
        oro=Orologio(); giornata._adesso=oro
        s=servizio(tmp,str(Path(tmp)/"pdf"),oro,argparse.Namespace(server=None,modelli=None))
        s.registra_informativa("Rossi Maria (ESEMPIO)","Ufficio dimostrativo")
        s.imp["riduci_animazioni"]="complete"
        oro.t=T("08:00"); s.avvia(); oro.t=T("14:00"); s.chiudi(); g="2026-10-05"; s.genera(g,usa_ai=False)
        app=App(s); app.update(); app.focus_force()
        t=time.monotonic(); snapped=False
        while time.monotonic()-t<.8:
            app.update()
            if not snapped and time.monotonic()-t>.38 and getattr(app,"splash",None) and app.splash.winfo_exists():
                cattura_demo(app.splash,str(out/"00_splash.png")); snapped=True
            time.sleep(.015)
        if not snapped: raise RuntimeError("Splash non catturato")
        frames=[]; stage=-1; start=time.monotonic(); framepath=Path(tmp)/"frame.png"
        while time.monotonic()-start<6:
            elapsed=time.monotonic()-start; n=int(elapsed/1.5)
            if n!=stage:
                if n==0: app.vai_oggi()
                elif n==1: app.vai_revisione(g)
                elif n==2: app.mostra_generazione(g,"14:00"); app._anima()
                else: app.vai_revisione(g)
                stage=n
            app.event_generate("<Motion>", x=20, y=20); app.update()
            cattura_demo(app,str(framepath))
            with Image.open(framepath) as im: frames.append(im.resize((812,546)).convert("P",palette=Image.Palette.ADAPTIVE,colors=128))
            deadline=start+len(frames)/15
            while time.monotonic()<deadline: app.update(); time.sleep(.008)
        frames[0].save(out/"flusso.gif",save_all=True,append_images=frames[1:],duration=67,loop=0,optimize=True)
        app.destroy()
    print("Demo reale Tk: PNG splash, GIF a circa 15 fps; dati esclusivamente inventati.")

if __name__=="__main__":main()
