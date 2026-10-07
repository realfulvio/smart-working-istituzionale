"""Controlla UTF-8 dei file testuali tracciati, sequenze da doppia codifica e scritture Python."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

def controlla(root):
    names=subprocess.check_output(['git','ls-files'],cwd=root,text=True,encoding='utf-8').splitlines()
    out={'utf8_non_valido':[], 'doppia_codifica':[], 'scritture_python_senza_encoding':[], 'scritture_powershell_senza_encoding':[]}
    extensions={'.py','.md','.json','.jsonl','.ps1','.iss','.yml','.yaml','.txt','.rtf','.html','.css','.js','.svg','.csv'}
    for name in names:
        p=root/name
        if not p.is_file() or p.suffix.lower() not in extensions:continue
        try:s=p.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:out['utf8_non_valido'].append(name);continue
        for line,text in enumerate(s.splitlines(),1):
            for match in re.finditer(r'[^\x00-\x7f]+',text):
                word=match.group()
                if not any(c in word for c in ('\u00c3','\u00c2','\u00e2','\u00f0')):continue
                for codec in ('cp1252','latin1'):
                    try:fixed=word.encode(codec).decode('utf-8')
                    except UnicodeError:continue
                    if fixed!=word:
                        out['doppia_codifica'].append({'file':name,'riga':line,'sequenza':word});break
        if p.suffix=='.py':
            for call in ast.walk(ast.parse(s)):
                if not isinstance(call,ast.Call):continue
                f=call.func;method=f.attr if isinstance(f,ast.Attribute) else ''
                if method=='write_text' and not any(k.arg=='encoding' for k in call.keywords):
                    out['scritture_python_senza_encoding'].append({'file':name,'riga':call.lineno})
                if isinstance(f,ast.Name) and f.id=='open':
                    mode=call.args[1].value if len(call.args)>1 and isinstance(call.args[1],ast.Constant) else 'r'
                    mode=next((k.value.value for k in call.keywords if k.arg=='mode' and isinstance(k.value,ast.Constant)),mode)
                    if any(c in str(mode) for c in 'wax') and 'b' not in str(mode) and not any(k.arg=='encoding' for k in call.keywords):
                        out['scritture_python_senza_encoding'].append({'file':name,'riga':call.lineno})
        if p.suffix=='.ps1':
            lines=s.splitlines()
            for i,line in enumerate(lines):
                if re.search(r'\b(?:Set-Content|Add-Content|Out-File)\b',line,re.I) and not line.lstrip().startswith('#'):
                    call=line
                    j=i
                    while call.rstrip().endswith('`') and j+1<len(lines):j+=1;call+=' '+lines[j]
                    if not re.search(r'-Encoding\s+(?:utf8|utf8NoBOM|ascii|unicode)\b',call,re.I):
                        out['scritture_powershell_senza_encoding'].append({'file':name,'riga':i+1})
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--esito',type=Path);ns=ap.parse_args()
    r=controlla(ns.root)
    if ns.esito:ns.esito.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False,indent=2));return int(any(r.values()))

if __name__=='__main__':raise SystemExit(main())
