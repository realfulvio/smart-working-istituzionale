# Misura peso e velocità del pacchetto già costruito (build\dist\RendicontoSW, vedi tools\pacchetto\build_app.ps1).
# Pensato per la CI (.github/workflows/misura-peso.yml), così le misure sono confrontabili tra una modifica e l'altra.
# Scrive il risultato in JSON (-Esito) e un riepilogo Markdown in $env:GITHUB_STEP_SUMMARY se presente.
param(
    [string]$Dist = "build\dist\RendicontoSW",
    [string]$Esito = "misura.json",
    [string]$Esempio = "examples\01_giornata_ufficio\finale.json",
    [int]$Ripetizioni = 5,
    [int]$SecondiRaccolta = 30
)
$ErrorActionPreference = "Stop"
$ris = [ordered]@{}

# ------------------------------------------------------------------------------------------ dimensioni
$file = Get-ChildItem $Dist -Recurse -File
$ris.dimensione_mb = [math]::Round(($file | Measure-Object Length -Sum).Sum / 1MB, 1)
$ris.numero_file = $file.Count
$radice = (Resolve-Path $Dist).Path
$ris.per_cartella_mb = [ordered]@{}
Get-ChildItem $Dist | ForEach-Object {
    $dim = if ($_.PSIsContainer) { (Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum } else { $_.Length }
    [pscustomobject]@{ nome = $_.Name; mb = [math]::Round($dim / 1MB, 2) }
} | Sort-Object mb -Descending | Select-Object -First 8 | ForEach-Object { $ris.per_cartella_mb[$_.nome] = $_.mb }
# primo livello dentro _internal (PyInstaller 6), dove sta quasi tutto
$interno = Join-Path $Dist "_internal"
$ris.per_pacchetto_mb = [ordered]@{}
if (Test-Path $interno) {
    Get-ChildItem $interno | ForEach-Object {
        $dim = if ($_.PSIsContainer) { (Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum } else { $_.Length }
        [pscustomobject]@{ nome = $_.Name; mb = [math]::Round($dim / 1MB, 2) }
    } | Sort-Object mb -Descending | Select-Object -First 15 | ForEach-Object { $ris.per_pacchetto_mb[$_.nome] = $_.mb }
}
$ris.file_piu_grandi_mb = [ordered]@{}
$file | Sort-Object Length -Descending | Select-Object -First 10 | ForEach-Object {
    $ris.file_piu_grandi_mb[$_.FullName.Substring($radice.Length + 1)] = [math]::Round($_.Length / 1MB, 2)
}
$zip = Join-Path $env:TEMP "misura-peso.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$Dist\*" -DestinationPath $zip -CompressionLevel Optimal
$ris.zip_mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)

# ------------------------------------------------------------------------- avvio a freddo (genera un PDF)
$exe = Join-Path $Dist "RendicontoSW.exe"
$tempi = @()
for ($i = 0; $i -lt $Ripetizioni; $i++) {
    $pdf = Join-Path $env:TEMP "misura-$i.pdf"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process $exe -ArgumentList @("--smoke-pdf", $Esempio, $pdf) -PassThru -Wait -WindowStyle Hidden
    $sw.Stop()
    if ($p.ExitCode -ne 0) { throw "smoke-pdf non riuscito (codice $($p.ExitCode))" }
    $tempi += [math]::Round($sw.Elapsed.TotalMilliseconds)
}
$ris.smoke_pdf_ms = $tempi
$ris.smoke_pdf_mediana_ms = ($tempi | Sort-Object)[[int][math]::Floor($tempi.Count / 2)]

# ----------------------------------------------- processo di raccolta (sempre acceso durante la giornata)
$base = Join-Path $env:TEMP "rsw-misura"
if (Test-Path $base) { Remove-Item $base -Recurse -Force }
New-Item -ItemType Directory $base | Out-Null
$env:RSW_BASE = $base
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process $exe -ArgumentList "_esegui" -PassThru -WindowStyle Hidden
$demone = Join-Path $base "stato\demone.json"
while (-not (Test-Path $demone) -and -not $p.HasExited -and $sw.Elapsed.TotalSeconds -lt 60) { Start-Sleep -Milliseconds 100 }
$ris.raccolta = [ordered]@{ avvio_ms = [math]::Round($sw.Elapsed.TotalMilliseconds); partito = (Test-Path $demone) }
if (-not $p.HasExited) {
    Start-Sleep -Seconds $SecondiRaccolta
    $p.Refresh()
    if (-not $p.HasExited) {
        $ris.raccolta.memoria_ws_mb = [math]::Round($p.WorkingSet64 / 1MB, 1)
        $ris.raccolta.memoria_privata_mb = [math]::Round($p.PrivateMemorySize64 / 1MB, 1)
        $ris.raccolta.cpu_s = [math]::Round($p.TotalProcessorTime.TotalSeconds, 2)
        $ris.raccolta.thread = $p.Threads.Count
        $ris.raccolta.handle = $p.HandleCount
        Stop-Process $p -Force
    }
}
$ris.raccolta.terminato_da_solo = $p.HasExited -and -not $ris.raccolta.Contains("memoria_ws_mb")
$log = Join-Path $base "diagnostica\collector.log"
if (Test-Path $log) { $ris.raccolta.log = (Get-Content $log -Tail 5) -join " | " }

$ris | ConvertTo-Json -Depth 6 | Set-Content $Esito -Encoding utf8
Get-Content $Esito
if ($env:GITHUB_STEP_SUMMARY) {
    $md = @("### Misura peso e velocità", "", "| voce | valore |", "|---|---|",
            "| pacchetto (cartella) | $($ris.dimensione_mb) MB in $($ris.numero_file) file |",
            "| pacchetto compresso (zip) | $($ris.zip_mb) MB |",
            "| avvio a freddo + PDF (mediana di $Ripetizioni) | $($ris.smoke_pdf_mediana_ms) ms |",
            "| processo di raccolta: avvio | $($ris.raccolta.avvio_ms) ms |",
            "| processo di raccolta: memoria (working set / privata) | $($ris.raccolta.memoria_ws_mb) / $($ris.raccolta.memoria_privata_mb) MB |",
            "| processo di raccolta: CPU in $SecondiRaccolta s | $($ris.raccolta.cpu_s) s |")
    $md -join "`n" | Add-Content $env:GITHUB_STEP_SUMMARY -Encoding UTF8
}
