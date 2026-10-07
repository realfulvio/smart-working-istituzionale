# Costruisce RendicontoSW-host.exe (host Native Messaging dell'estensione del browser).
# Uso, nella radice del repository, con il venv di sviluppo attivo (requirements + pyinstaller):
#   powershell -ExecutionPolicy Bypass -File tools\pacchetto\build_host.ps1 [-Uscita build\host]
#
# DIFFERENZE da build_app.ps1 (intenzionali):
#  - --onefile --console: l'host parla con il browser su stdin/stdout. Con --windowed (come l'app) non esistono
#    stdin/stdout e il browser non riceverebbe risposte;
# FIRMA DEL CODICE: TODO con il certificato dell'Ente (l'eseguibile prodotto NON è firmato). Nessun aggiramento di
# Defender/ASR/EDR.
param([string]$Uscita = "build\host")
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --clean --onefile --console --name RendicontoSW-host `
    --distpath $Uscita --workpath "$Uscita\work" --specpath "$Uscita" `
    --add-data "$PWD\config;config" --add-data "$PWD\schema;schema" --collect-data tzdata `
    tools\pacchetto\host_entry.py
$s = Get-AuthenticodeSignature "$Uscita\RendicontoSW-host.exe"
Write-Host ("RendicontoSW-host.exe: firma {0} (TODO: firma con il certificato dell'Ente)" -f $s.Status)
