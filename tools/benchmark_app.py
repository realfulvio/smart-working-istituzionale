"""Banco sintetico della vera App Tk; nessun sensore, nessun dato operativo."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def memoria():
    from ctypes import wintypes as w
    class M(ctypes.Structure):
        _fields_=[("cb",w.DWORD),("fault",w.DWORD)]+[(n,ctypes.c_size_t) for n in ("peak","working","pp","p","np","n","page","peakpage","private")]
    m=M();m.cb=ctypes.sizeof(M)
    k=ctypes.windll.kernel32;k.GetCurrentProcess.restype=w.HANDLE
    f=ctypes.windll.psapi.GetProcessMemoryInfo;f.argtypes=[w.HANDLE,ctypes.c_void_p,w.DWORD]
    if not f(k.GetCurrentProcess(),ctypes.byref(m),m.cb):raise OSError("Misura memoria fallita")
    return m.working/1048576,m.private/1048576

def limite_gb(gb):
    if not gb:return {"limite_job_gb":None}
    from ctypes import wintypes as w
    class B(ctypes.Structure):
        _fields_=[("process_time",ctypes.c_longlong),("job_time",ctypes.c_longlong),("flags",w.DWORD),("minws",ctypes.c_size_t),("maxws",ctypes.c_size_t),("processi",w.DWORD),("affinita",ctypes.c_size_t),("priority",w.DWORD),("scheduling",w.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(n,ctypes.c_ulonglong) for n in ("read","write","other","readbytes","writebytes","otherbytes")]
    class E(ctypes.Structure):
        _fields_=[("basic",B),("io",IO),("process_limit",ctypes.c_size_t),("job_limit",ctypes.c_size_t),("peak_process",ctypes.c_size_t),("peak_job",ctypes.c_size_t)]
    k=ctypes.windll.kernel32;k.CreateJobObjectW.restype=w.HANDLE
    k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
    k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    k.GetCurrentProcess.restype=w.HANDLE
    job=k.CreateJobObjectW(None,None);info=E();info.basic.flags=0x200;info.job_limit=gb*1024**3
    ok=bool(k.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) and k.AssignProcessToJobObject(job,k.GetCurrentProcess()))
    return {"limite_job_gb":gb if ok else None,"job_impostato":ok,"winerror":ctypes.GetLastError() if not ok else None}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--edizione",default="neutra");ap.add_argument("--movimento",choices=["on","off"],required=True);ap.add_argument("--ram",type=int,default=0);ap.add_argument("--esito",required=True)
    ns=ap.parse_args();os.environ["RENDICONTO_EDIZIONE"]=ns.edizione
    limite=limite_gb(ns.ram)
    if ns.ram:
        from redattore import profilo
        profilo.memoria_gb=lambda:(ns.ram,4.0)
    from tools.schermate_documentazione import servizio,Orologio,T
    from collector import giornata,postazione
    from applicazione.gui import App
    from applicazione.tema import Bottone,Scheda
    postazione.rileva=lambda:{"nome_macchina":"PC-ESEMPIO","tipo":"VDI","sistema_operativo":"Windows 11 (ESEMPIO)","processore":"CPU esempio","ram_gb":ns.ram or 12}
    with tempfile.TemporaryDirectory(prefix="rsw_bench_") as temp:
        oro=Orologio();giornata._adesso=oro
        s=servizio(temp,str(Path(temp)/"pdf"),oro,argparse.Namespace(server=None,modelli=None))
        s.imp["riduci_animazioni"]="complete" if ns.movimento=="on" else "ridotte"
        s.registra_informativa("Rossi Maria (ESEMPIO)","Ufficio dimostrativo")
        oro.t=T("08:00");s.avvia();oro.t=T("12:00");s.chiudi();g=oro.t.date().isoformat();s.genera(g,usa_ai=False)
        app=App(s);app.update();app.focus_force()
        def discendenti(w):
            for c in w.winfo_children():yield c;yield from discendenti(c)
        start=time.monotonic()
        while time.monotonic()-start<1.5:app.update();time.sleep(.02)
        c0=time.process_time();t0=time.monotonic();frame0=app.movimento.frame
        peakws=peakprivate=0;last_hover=-1;last_screen=-1;foreground=[]
        while time.monotonic()-t0<12:
            elapsed=time.monotonic()-t0
            # Uso normale simulato: una schermata ogni 4 s, hover ogni 0,5 s.
            screen=int(elapsed/4)
            if screen!=last_screen:
                [lambda:app.vai_revisione(g),app.vai_impostazioni,app.vai_oggi][screen%3]();last_screen=screen
            hover=int(elapsed*2)
            if hover!=last_hover:
                app.movimento.interazione()
                cards=[w for w in discendenti(app) if isinstance(w,Scheda)]
                buttons=[w for w in discendenti(app) if isinstance(w,Bottone)]
                if cards:cards[0]._eleva(bool(hover%2))
                if buttons:buttons[0]._hover(bool(hover%2))
                foreground.append(app.movimento.primo_piano());last_hover=hover
            app.update();ws,private=memoria();peakws=max(peakws,ws);peakprivate=max(peakprivate,private);time.sleep(.02)
        result={"edizione":ns.edizione,"movimento":ns.movimento,"ram_profilo_simulata_gb":ns.ram or None,**limite,"durata_s":round(time.monotonic()-t0,3),"cpu_percento_un_core":round((time.process_time()-c0)/(time.monotonic()-t0)*100,3),"working_set_picco_mb":round(peakws,2),"privata_picco_mb":round(peakprivate,2),"frame_animazione":app.movimento.frame-frame0,"foreground_campioni":sum(foreground),"campioni_interazione":len(foreground)}
        # Non deve muoversi senza input o in background.
        app.movimento.ultimo_input-=6
        app.update();time.sleep(.3);app.update();idle0=app.movimento.frame
        pause=time.monotonic()
        while time.monotonic()-pause<.6:app.update();time.sleep(.03)
        result["fermo_inattivo"]=app.movimento.frame==idle0
        app.withdraw();app.movimento.interazione();app.update();back0=app.movimento.frame
        pause=time.monotonic()
        while time.monotonic()-pause<.6:app.update();time.sleep(.03)
        result["fermo_background"]=app.movimento.frame==back0
        app.destroy()
    Path(ns.esito).parent.mkdir(parents=True,exist_ok=True);Path(ns.esito).write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result))

if __name__=="__main__":main()
