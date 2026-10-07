# Costruisce RendicontoSW-collector (PyInstaller, cartella --onedir: un solo processo, avvio rapido).
# Uso (da PowerShell, nella radice del repository, con il venv di sviluppo attivo):
#   powershell -ExecutionPolicy Bypass -File tools\build_collector.ps1
# Nessuna firma del codice: l'eseguibile non è firmato (vedi README, «Firma del codice»).
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --clean --onedir --console --name RendicontoSW-collector `
  --distpath build\dist --workpath build\work --specpath build `
  --add-data "..\config;config" --add-data "..\schema;schema" `
  --collect-data tzdata --hidden-import win32timezone `
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc `
  tools\collector_entry.py
