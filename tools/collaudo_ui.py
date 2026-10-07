"""Collaudo sintetico di tastiera e scale applicative; non cambia il DPI di Windows."""
from pathlib import Path
import json
import sys
import tempfile
import tkinter as tk
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.schermate_documentazione import servizio, Orologio, T
from tools.cattura_finestra import cattura
from applicazione.gui import App
from applicazione.tema import Bottone, Casella
from collector import giornata as cg
from argparse import Namespace

def main():
    from resoconto.edizione import identita
    ed = identita()["id"]
    output = Path("output/ui/scaling") / ed; output.mkdir(parents=True, exist_ok=True)
    results = []
    for scale in (1, 1.25, 1.5):
        with tempfile.TemporaryDirectory(prefix="rsw_ui_") as temp:
            clock = Orologio(); cg._adesso = clock
            s = servizio(str(Path(temp)/"base"),str(Path(temp)/"PDF-ESEMPIO"),clock,Namespace(server=None,modelli=None))
            app = App(s, scala_test=scale)
            try:
                app.update(); cattura(app,str(output/f"{scale}-informativa.png"))
                app.focus_force(); app.after(100); app.update()
                app._tab_modale(None); app.after(100); app.update()
                assert str(app.focus_get()).startswith(str(app.velo))
                s.registra_informativa("Rossi Maria (ESEMPIO)","Ufficio dimostrativo")
                app.vai_oggi(); app.update(); cattura(app,str(output/f"{scale}-home.png"))
                clock.t=T("08:00"); s.avvia(); clock.t=T("14:00"); s.chiudi()
                s.genera("2026-10-05", usa_ai=False)
                app.vai_revisione("2026-10-05"); app.update()
                cattura(app,str(output/f"{scale}-revisione.png"))
                app.mostra_aggiungi("2026-10-05"); app.update()
                cattura(app,str(output/f"{scale}-attivita.png"))
                controls=[]
                def visit(w):
                    try:
                        if str(w.cget("takefocus"))=="1": controls.append(w)
                    except tk.TclError: pass
                    for child in w.winfo_children(): visit(child)
                visit(app.velo)
                for control in controls:
                    control.focus_force(); app.after(50); app.update()
                    assert app.focus_get() == control
                app.chiudi_velo(); app.vai_impostazioni(); app.update()
                cattura(app,str(output/f"{scale}-impostazioni.png"))
                count=[]; b=Bottone(app.corpo,"Test",lambda:count.append(1)); b.pack(); app.update()
                b.focus_force(); b.event_generate("<Return>"); app.update(); assert count==[1]
                b.attiva(False); b.event_generate("<space>"); app.update(); assert count==[1]
                variable=tk.BooleanVar(value=False); c=Casella(app.corpo,"Conferma",variable); c.pack(); app.update()
                c.focus_force(); c.event_generate("<space>"); app.update(); assert variable.get()
                results.append({"scala_applicativa":scale,"finestra":[app.winfo_width(),app.winfo_height()],
                                "focus_modale":True,"invio_spazio_disabilitato":True,"controlli_modale":len(controls)})
            finally: app.destroy()
    Path(f"docs/verifiche/V5-tastiera-scaling-{ed}.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(json.dumps(results))

if __name__ == "__main__": main()
