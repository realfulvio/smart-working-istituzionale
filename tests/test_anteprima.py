import json
from pathlib import Path
from applicazione.servizio import Servizio
from tools.simula_edizione import righe, mappa_sintetica

def test_anteprima_legge_solo_raw_e_non_scrive(tmp_path):
    from datetime import datetime
    s=Servizio(str(tmp_path),impostazioni={"modalita":"collector"},mappa=mappa_sintetica(),adesso=lambda:datetime.fromisoformat("2026-10-07T14:00:00+02:00"))
    path=Path(s.p.raw_giorno("2026-10-07"))
    path.write_text("\n".join(json.dumps(x) for x in righe())+"\n{",encoding="utf-8")
    before=path.read_bytes();rows=s.segnali_correnti("2026-10-07")
    assert rows and len(rows)<=6
    assert all(set(r)=={"ora","fine","categorie"} for r in rows)
    assert not Path(s.p.json_giorno("2026-10-07")).exists()
    assert path.read_bytes()==before
    s.imp["modalita"]="consuntivo"
    assert s.segnali_correnti("2026-10-07")==[]
