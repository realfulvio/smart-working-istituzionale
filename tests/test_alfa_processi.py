"""Collaudo ALFA: terminando l'app durante la generazione restava un llama-server orfano (1,4 GB)."""
import subprocess
import sys
import time

import pytest

from redattore import motore


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object di Windows")
def test_il_figlio_muore_se_il_padre_viene_terminato(tmp_path):
    codice = (
        "import subprocess, sys, time\n"
        "from redattore import motore\n"
        "f = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "assert motore.muori_con_il_padre(f) is not None\n"
        "print(f.pid, flush=True)\n"
        "time.sleep(120)\n")
    padre = subprocess.Popen([sys.executable, "-c", codice], stdout=subprocess.PIPE, text=True,
                             cwd=str(__import__("os").path.dirname(__import__("os").path.dirname(__file__))))
    try:
        pid_figlio = int(padre.stdout.readline().strip())
        assert _vivo(pid_figlio)
        padre.kill()                                   # TerminateProcess: nessun codice di chiusura dell'app può girare
        padre.wait(10)
        for _ in range(30):
            if not _vivo(pid_figlio):
                break
            time.sleep(0.2)
        assert not _vivo(pid_figlio), "il figlio è rimasto orfano"
    finally:
        padre.kill()


def _vivo(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def test_muori_con_il_padre_non_fa_nulla_fuori_da_windows(monkeypatch):
    monkeypatch.setattr(motore.sys, "platform", "linux")
    assert motore.muori_con_il_padre(object()) is None
