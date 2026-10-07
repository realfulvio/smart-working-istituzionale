"""Materializza solo l'overlay scelto nel pacchetto; non copia gli altri overlay."""
import json
import shutil
from pathlib import Path
from resoconto import edizione

def prepara(dest):
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("La cartella di configurazione deve essere nuova o vuota: evita residui di altre edizioni.")
    dest.mkdir(parents=True, exist_ok=True)
    for source in (edizione.RADICE / "config").glob("*.json"):
        if source.name == "edizione.json":
            continue
        shutil.copyfile(edizione.percorso(source.name), dest / source.name)
    for name in ("ente.json", "design_tokens.json", "identita.json"):
        shutil.copyfile(edizione.percorso(name), dest / name)
    cfg = json.loads((dest / "ente.json").read_text(encoding="utf-8-sig"))
    from resoconto import ente
    cfg["colori"]=ente.carica()["colori"]
    logo = (edizione.percorso("ente.json").parent / cfg.get("logo", "")).resolve()
    if logo.is_file():
        shutil.copyfile(logo, dest / "identita.png")
        cfg["logo"] = "identita.png"
    (dest / "ente.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    overlay=edizione.cartella()
    if overlay and (overlay / "storico").is_dir():
        shutil.copytree(overlay / "storico",dest / "storico",dirs_exist_ok=True)
        for meta in (dest / "storico").glob("ente_*.json"):
            cfg_old=json.loads(meta.read_text(encoding="utf-8"))
            origin=overlay / "storico" / meta.name
            image=(origin.parent / cfg_old.get("logo","")).resolve()
            if image.is_file():
                asset="logo_"+meta.stem+image.suffix
                shutil.copyfile(image,meta.parent / asset);cfg_old["logo"]=asset
                meta.write_text(json.dumps(cfg_old,ensure_ascii=False,indent=2),encoding="utf-8")
    (dest / "edizione.json").write_text('{"overlay": null}', encoding="utf-8")

if __name__ == "__main__":
    import sys
    prepara(sys.argv[1])
