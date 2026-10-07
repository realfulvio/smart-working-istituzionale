from copy import deepcopy
from tools.simula_edizione import genera
from aggregatore.cli import validate
from aggregatore import sigillo
from redattore.fatti import estrai

def test_identita_obbligatoria_sigillata_ma_non_ai(tmp_path):
    _, d = genera()
    assert d["schema"].endswith("/5") and validate(d) == []
    vecchio = deepcopy(d); vecchio.pop("identita_documento")
    assert validate(vecchio)
    key = sigillo.load_or_create_key(str(tmp_path))
    sealed = sigillo.seal_technical(d, key)
    facts = estrai(sealed)
    sealed["identita_documento"]["nome"] = "Ente esempio diverso"
    assert estrai(sealed) == facts
    assert sigillo.verify(sealed, check_final=False)["esito"] == "ALTERATO"
