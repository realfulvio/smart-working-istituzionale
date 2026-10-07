from applicazione.movimento import Movimento, mescola

class Root:
    def __init__(self):self.callbacks={};self.n=0
    def bind(self,*args,**kw):pass
    def after(self,ms,fn):
        self.n+=1;self.callbacks[self.n]=(ms,fn);return self.n
    def after_cancel(self,n):self.callbacks.pop(n,None)
    def winfo_exists(self):return True

def test_clock_pause_riduzione_e_ripresa(monkeypatch):
    t=[0.0];root=Root();g=Movimento(root,"complete",clock=lambda:t[0]);foreground=[True]
    monkeypatch.setattr(g,"primo_piano",lambda:foreground[0])
    values=[];g.effetto(root,values.append,.18)
    t[0]=.034;g._tick();assert values and values[-1] < 1
    before=list(values);foreground[0]=False;t[0]=.068;g._tick();assert values==before
    foreground[0]=True;t[0]=6;g._tick();assert values==before
    g.interazione();t[0]=6.034;g._tick();assert len(values)>len(before)
    g.abilita("ridotte");assert values[-1]==1 and not g.jobs
    assert all(ms>=34 for ms,_ in root.callbacks.values())

def test_sistema_non_leggibile_riduce(monkeypatch):
    import applicazione.movimento as m
    monkeypatch.setattr(m,"windows_ridotto",lambda:True)
    g=Movimento(Root());values=[];g.effetto(g.root,values.append,.2)
    assert values==[1] and g.timer is None
    assert mescola("white","#000000",1)=="#000000"
