"""Motori di generazione locali, caricati solo per il tempo della richiesta («Genera resoconto») e poi scaricati.

  LlamaCpp – avvia llama-server (llama.cpp, MIT) su 127.0.0.1 con chiave API casuale per ogni avvio, invia le richieste
             a /completion con uscita vincolata da JSON Schema (GBNF), poi termina il processo.
  Ollama   – alternativa: usa un servizio Ollama già installato (/api/chat, format = JSON Schema, keep_alive 0).

Nessuna connessione verso l'esterno: solo 127.0.0.1. Temperatura 0, top_k 1, seme fisso.
"""
from __future__ import annotations

import hashlib
import secrets
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import urllib.parse


class ErroreMotore(RuntimeError):
    pass


def _valida_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != "http" or p.hostname != "127.0.0.1" or p.username or p.password or p.fragment:
        raise ErroreMotore("Il motore AI deve usare HTTP su 127.0.0.1")
    try:
        p.port
    except ValueError as e:
        raise ErroreMotore("Porta del motore AI non valida") from e


class _SenzaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErroreMotore("Reindirizzamento del motore AI rifiutato")


def _apri(req, timeout):
    _valida_url(req.full_url)
    # Nessun proxy d'ambiente e nessun redirect possono portare i fatti fuori dal PC.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SenzaRedirect())
    return opener.open(req, timeout=timeout)


def _post(url: str, body: dict, timeout: float, api_key: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with _apri(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url: str, timeout: float, api_key: str | None = None):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)
    return _apri(req, timeout=timeout)


def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def prompt_chatml(sistema: str, utente: str, qwen3: bool, esempio: tuple[str, str] | None = None) -> str:
    """Modello di chat dei Qwen (ChatML). Con Qwen3 il blocco <think> vuoto equivale a enable_thinking=False.
    esempio = (domanda, risposta): un turno di esempio prima della richiesta vera."""
    vuoto = "<think>\n\n</think>\n\n" if qwen3 else ""
    p = f"<|im_start|>system\n{sistema}<|im_end|>\n"
    if esempio:
        p += f"<|im_start|>user\n{esempio[0]}<|im_end|>\n<|im_start|>assistant\n{vuoto}{esempio[1]}<|im_end|>\n"
    return p + f"<|im_start|>user\n{utente}<|im_end|>\n<|im_start|>assistant\n{vuoto}"


def _picco_memoria_mb(proc: subprocess.Popen) -> dict:
    """Picco di memoria del processo del motore (Linux: VmHWM; Windows: PeakWorkingSetSize e picco privato)."""
    try:
        if sys.platform.startswith("linux"):
            out = {}
            with open(f"/proc/{proc.pid}/status") as f:
                for r in f:
                    if r.startswith(("VmHWM:", "VmRSS:")):
                        out[r.split(":")[0]] = int(r.split()[1]) / 1024
            return {"picco_mb": round(out.get("VmHWM", 0)), "attuale_mb": round(out.get("VmRSS", 0))}
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            c = PMC(); c.cb = ctypes.sizeof(PMC)
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(proc._handle)), ctypes.byref(c), c.cb):
                return {"picco_mb": round(c.PeakWorkingSetSize / 2**20), "attuale_mb": round(c.WorkingSetSize / 2**20),
                        "picco_privato_mb": round(c.PeakPagefileUsage / 2**20)}
    except Exception:   # noqa: BLE001 - la misura è solo informativa
        pass
    return {}


# Memoria: senza --no-repack il backend CPU crea una seconda copia «riordinata» dei pesi accanto al file mappato
# (picco misurato 2,7 GB invece di 1,4 GB, a parità di velocità). Cache KV in q8_0 con flash attention; nessuna cache
# dei prompt tra richieste diverse (--cache-ram 0).
OPZIONI_MEMORIA = ["--no-repack", "-ctk", "q8_0", "-ctv", "q8_0", "-fa", "on", "--cache-ram", "0"]


def _norm_path(p: str) -> str:
    return os.path.normcase(os.path.abspath(p)) if p else ""


def processi_con_eseguibile(percorso: str) -> list[int]:
    """PID dei processi il cui eseguibile è esattamente «percorso» (solo i nostri, mai altri llama-server)."""
    voluto = _norm_path(percorso)
    if not voluto or not os.path.isfile(voluto):
        return []
    out = []
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            TH32CS_SNAPPROCESS = 0x00000002
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

            class PE32(ctypes.Structure):
                _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wintypes.DWORD),
                            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                            ("szExeFile", wintypes.WCHAR * 260)]

            snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snap == wintypes.HANDLE(-1).value:
                return []
            try:
                pe = PE32(); pe.dwSize = ctypes.sizeof(PE32)
                if not k.Process32FirstW(snap, ctypes.byref(pe)):
                    return []
                while True:
                    nome = (pe.szExeFile or "").lower()
                    if "llama-server" in nome:
                        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pe.th32ProcessID)
                        if h:
                            try:
                                buf = ctypes.create_unicode_buffer(32768)
                                n = wintypes.DWORD(len(buf))
                                # QueryFullProcessImageNameW
                                q = getattr(k, "QueryFullProcessImageNameW")
                                if q(h, 0, buf, ctypes.byref(n)) and _norm_path(buf.value) == voluto:
                                    out.append(int(pe.th32ProcessID))
                            finally:
                                k.CloseHandle(h)
                    if not k.Process32NextW(snap, ctypes.byref(pe)):
                        break
            finally:
                k.CloseHandle(snap)
        except Exception:  # noqa: BLE001
            return []
    else:
        try:
            for nome in os.listdir("/proc"):
                if not nome.isdigit():
                    continue
                try:
                    exe = os.readlink(f"/proc/{nome}/exe")
                except OSError:
                    continue
                if _norm_path(exe) == voluto:
                    out.append(int(nome))
        except OSError:
            return []
    return out


def termina_llama_orfani(server: str, esclusi: set[int] | None = None) -> list[int]:
    """Termina i llama-server avviati dal NOSTRO percorso (orfani da un kill precedente). Non tocca altri."""
    morti = []
    esclusi = esclusi or set()
    for pid in processi_con_eseguibile(server):
        if pid in esclusi or pid == os.getpid():
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
            else:
                os.kill(pid, 15)
                for _ in range(20):
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        break
                    time.sleep(0.1)
                else:
                    os.kill(pid, 9)
            morti.append(pid)
        except OSError:
            pass
    return morti


def muori_con_il_padre(proc):
    """Windows: assegna il processo figlio a un Job Object con JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. L'handle del job
    appartiene al processo corrente: se l'app viene terminata (o va in crash) Windows termina anche il figlio.
    Collaudo ALFA: dopo la chiusura brusca durante la generazione restava un llama-server da 1,4 GB, che si sommava
    a quello della generazione successiva e bloccava la disinstallazione. Ritorna l'handle del job (da tenere vivo) o None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class Io(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                       "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Esteso(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        job = k.CreateJobObjectW(None, None)
        info = Esteso()
        info.Basic.LimitFlags = 0x2000                       # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not job or not k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        if not k.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle))):
            return None
        return job
    except Exception:   # noqa: BLE001 - senza job il server resta com'era prima (può restare orfano)
        return None


class LlamaCpp:
    tipo = "llama.cpp"

    def __init__(self, server: str, modello: str, thread: int = 4, contesto: int = 4096, seme: int = 42,
                 max_token: int = 700, timeout_avvio: float = 180, nome_modello: str | None = None,
                 extra: list[str] | None = None, cache_prefisso: str | None = None):
        self.server, self.modello, self.thread, self.contesto = server, modello, thread, contesto
        self.seme, self.max_token, self.timeout_avvio = seme, max_token, timeout_avvio
        self.nome_modello = nome_modello or os.path.basename(modello)
        self.qwen3 = "qwen3" in self.nome_modello.lower()
        self.proc = None
        self.misure: dict = {}
        self.extra = list(extra or [])
        # cartella per la cache su disco del prefisso fisso del prompt (istruzioni + esempio, nessun dato della giornata):
        # evita di rielaborare ~1100 token a ogni richiesta (4B: −18 s su 4 vCPU). Facoltativa.
        self.cache_prefisso = cache_prefisso
        self._prefisso_pronto = False

    def __enter__(self):
        if not os.path.exists(self.modello):
            raise ErroreMotore(f"modello non trovato: {self.modello}")
        # Collaudo ALFA B5: un llama-server orfano (stesso percorso) va chiuso prima di avviane un altro
        self.misure["orfani_terminati"] = termina_llama_orfani(self.server)
        self.porta = _porta_libera()
        # Chiave casuale per ogni avvio: su VDI/RDS 127.0.0.1 è condiviso tra sessioni dello stesso PC.
        self.api_key = secrets.token_urlsafe(32)
        args = [self.server, "-m", self.modello, "--host", "127.0.0.1", "--port", str(self.porta),
                "--api-key", self.api_key,
                "-t", str(self.thread), "-tb", str(self.thread), "-c", str(self.contesto), "-np", "1",
                "-ngl", "0", "--seed", str(self.seme), "--no-webui", "--log-disable"] + OPZIONI_MEMORIA + self.extra
        if self.cache_prefisso:
            try:
                os.makedirs(self.cache_prefisso, exist_ok=True)
                args += ["--slot-save-path", self.cache_prefisso]
            except OSError:
                self.cache_prefisso = None
        flags = 0x08000000 if sys.platform == "win32" else 0       # CREATE_NO_WINDOW
        t0 = time.monotonic()
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=flags)
        except OSError as e:
            raise ErroreMotore(f"impossibile avviare il motore: {e}") from e
        self._job = muori_con_il_padre(self.proc)      # se l'app viene terminata, il server non resta orfano
        while time.monotonic() - t0 < self.timeout_avvio:
            if self.proc.poll() is not None:
                raise ErroreMotore(f"il motore si è chiuso all'avvio (codice {self.proc.returncode})")
            try:
                with _get(f"http://127.0.0.1:{self.porta}/health", timeout=2, api_key=self.api_key) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.25)
        else:
            self.__exit__(None, None, None)
            raise ErroreMotore("il motore non ha risposto entro il tempo massimo")
        self.misure["secondi_caricamento"] = round(time.monotonic() - t0, 2)
        try:
            props = json.loads(_get(f"http://127.0.0.1:{self.porta}/props", timeout=5, api_key=self.api_key).read())
            self.versione_runtime = str(props.get("build_info") or "")
        except Exception:   # noqa: BLE001
            self.versione_runtime = ""
        return self

    def _nome_cache(self, prefisso: str) -> str:
        try:
            dim = os.path.getsize(self.modello)
        except OSError:
            dim = 0
        h = hashlib.sha256(f"{self.nome_modello}|{dim}|{self.versione_runtime}|{self.contesto}|{OPZIONI_MEMORIA}|"
                           .encode("utf-8") + prefisso.encode("utf-8")).hexdigest()[:24]
        return f"prefisso_{h}.bin"

    def _prepara_prefisso(self, prompt: str) -> None:
        """Ripristina (o crea la prima volta) la cache del prefisso fisso. Ogni errore viene ignorato."""
        self._prefisso_pronto = True
        i = prompt.rfind("<|im_start|>user\n")
        if not self.cache_prefisso or i <= 0:
            return
        prefisso = prompt[: i + len("<|im_start|>user\n")]
        nome = self._nome_cache(prefisso)
        base = f"http://127.0.0.1:{self.porta}"
        t0 = time.monotonic()
        try:
            if os.path.exists(os.path.join(self.cache_prefisso, nome)):
                _post(base + "/slots/0?action=restore", {"filename": nome}, timeout=60, api_key=self.api_key)
                self.misure["cache_prefisso"] = "ripristinata"
            else:
                _post(base + "/completion", {"prompt": prefisso, "n_predict": 0, "cache_prompt": True,
                                             "seed": self.seme}, timeout=600, api_key=self.api_key)
                _post(base + "/slots/0?action=save", {"filename": nome}, timeout=60, api_key=self.api_key)
                self.misure["cache_prefisso"] = "creata"
        except Exception:   # noqa: BLE001 - senza cache funziona lo stesso, solo più lentamente
            self.misure["cache_prefisso"] = "non_disponibile"
        self.misure["secondi_cache_prefisso"] = round(time.monotonic() - t0, 2)

    def genera(self, sistema: str, utente: str, schema: dict, esempio=None) -> tuple[str, dict]:
        prompt = prompt_chatml(sistema, utente, self.qwen3, esempio)
        if not self._prefisso_pronto:
            self._prepara_prefisso(prompt)
        body = {"prompt": prompt, "n_predict": self.max_token,
                "temperature": 0, "top_k": 1, "top_p": 1.0, "min_p": 0.0, "repeat_penalty": 1.0, "seed": self.seme,
                "json_schema": schema, "cache_prompt": True, "stop": ["<|im_end|>"]}
        t0 = time.monotonic()
        try:
            r = _post(f"http://127.0.0.1:{self.porta}/completion", body, timeout=600, api_key=self.api_key)
        except (urllib.error.URLError, OSError) as e:
            raise ErroreMotore(f"richiesta al motore non riuscita: {e}") from e
        tm = r.get("timings") or {}
        return r.get("content", ""), {"secondi": round(time.monotonic() - t0, 2),
                                      "token_prompt": tm.get("prompt_n"), "token_generati": tm.get("predicted_n"),
                                      "token_al_secondo": round(tm["predicted_per_second"], 1)
                                      if tm.get("predicted_per_second") else None,
                                      "secondi_prompt": round(tm["prompt_ms"] / 1000, 2) if tm.get("prompt_ms") else None,
                                      "token_prompt_in_cache": tm.get("cache_n")}

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.misure.update(_picco_memoria_mb(self.proc))
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(5)
        self.proc = None
        return False

    def descrizione(self) -> dict:
        return {"tipo": self.tipo, "modello": self.nome_modello, "runtime": self.versione_runtime or None}


class Ollama:
    """Servizio Ollama locale (già avviato). Il modello viene scaricato dalla memoria alla fine (keep_alive 0)."""
    tipo = "ollama"

    def __init__(self, modello: str = "qwen3:1.7b", url: str = "http://127.0.0.1:11434", thread: int = 4,
                 contesto: int = 4096, seme: int = 42, max_token: int = 700):
        _valida_url(url)
        self.modello, self.url, self.thread, self.contesto = modello, url.rstrip("/"), thread, contesto
        self.seme, self.max_token = seme, max_token
        self.qwen3 = "qwen3" in modello.lower()
        self.misure: dict = {}

    def __enter__(self):
        try:
            with _get(self.url + "/api/version", timeout=5) as response:
                v = json.loads(response.read())
            self.versione_runtime = "ollama " + v.get("version", "")
        except (urllib.error.URLError, OSError) as e:
            raise ErroreMotore(f"servizio Ollama non raggiungibile: {e}") from e
        t0 = time.monotonic()
        _post(self.url + "/api/generate", {"model": self.modello, "keep_alive": "5m"}, timeout=300)
        self.misure["secondi_caricamento"] = round(time.monotonic() - t0, 2)
        return self

    def genera(self, sistema: str, utente: str, schema: dict, esempio=None) -> tuple[str, dict]:
        es = [{"role": "user", "content": esempio[0]}, {"role": "assistant", "content": esempio[1]}] if esempio else []
        body = {"model": self.modello, "stream": False, "format": schema, "keep_alive": "5m",
                "messages": [{"role": "system", "content": sistema}] + es + [{"role": "user", "content": utente}],
                "options": {"temperature": 0, "top_k": 1, "seed": self.seme, "num_thread": self.thread,
                            "num_ctx": self.contesto, "num_predict": self.max_token}}
        if self.qwen3:
            body["think"] = False
        t0 = time.monotonic()
        r = _post(self.url + "/api/chat", body, timeout=600)
        return (r.get("message") or {}).get("content", ""), {
            "secondi": round(time.monotonic() - t0, 2), "token_prompt": r.get("prompt_eval_count"),
            "token_generati": r.get("eval_count"),
            "token_al_secondo": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1) if r.get("eval_duration") else None}

    def __exit__(self, *exc):
        try:
            _post(self.url + "/api/generate", {"model": self.modello, "keep_alive": 0}, timeout=30)
        except Exception:   # noqa: BLE001
            pass
        return False

    def descrizione(self) -> dict:
        return {"tipo": self.tipo, "modello": self.modello, "runtime": self.versione_runtime or None}
