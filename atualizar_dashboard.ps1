# Abre o dashboard Power BI (PBIP no repo Git) e mostra status do CSV.
# Uso: .\atualizar_dashboard.ps1

$ErrorActionPreference = "Stop"

function Find-PBIDesktopExe {
    $candidates = @(
        "${env:ProgramFiles}\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "$env:LOCALAPPDATA\Programs\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
    )

    try {
        $pkg = Get-AppxPackage -Name "Microsoft.MicrosoftPowerBIDesktop" -ErrorAction SilentlyContinue |
            Sort-Object Version -Descending | Select-Object -First 1
        if ($pkg -and $pkg.InstallLocation) {
            $storeExe = Join-Path $pkg.InstallLocation "bin\PBIDesktop.exe"
            if (Test-Path $storeExe) { $candidates = @($storeExe) + $candidates }
        }
    } catch { }

    $winApps = Join-Path $env:ProgramFiles "WindowsApps"
    if (Test-Path $winApps) {
        try {
            Get-ChildItem $winApps -Directory -Filter "Microsoft.MicrosoftPowerBIDesktop_*" -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending |
                ForEach-Object {
                    $storeExe = Join-Path $_.FullName "bin\PBIDesktop.exe"
                    if (Test-Path $storeExe) { $candidates = @($storeExe) + $candidates }
                }
        } catch { }
    }

    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return (Resolve-Path $path).Path }
    }
    return $null
}

$WorkDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Csv     = "C:\DadosPowerBI\spotify-fgv\spotify_historico_dashboard.csv"
$Excel   = "C:\DadosPowerBI\spotify-fgv\spotify_analytics_historico.xlsx"
$PbipDir = Join-Path $WorkDir "powerbi-dashboards\dashboards\spotify-fgv"
$Pbip    = Join-Path $PbipDir "SpotifyDashboardFGV.pbip"
$Pbip    = (Resolve-Path $Pbip).Path

if (-not (Test-Path $Csv)) {
    Write-Host "[ERRO] CSV nao encontrado: $Csv" -ForegroundColor Red
    Write-Host "       Rode: python coletar.py --force"
    exit 1
}

$csvInfo = Get-Item $Csv
$lastLine = Get-Content $Csv -Tail 1 -Encoding UTF8
$lastDate = ($lastLine -split ',')[0]

Write-Host ""
Write-Host "=== SpotiScript - status do dashboard ===" -ForegroundColor Cyan
Write-Host ("CSV atualizado: {0}" -f $csvInfo.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))
Write-Host ("Ultima data nos dados: {0}" -f $lastDate)
Write-Host ("CSV: {0}" -f $Csv)
if (Test-Path $Excel) {
    $xlsxInfo = Get-Item $Excel
    Write-Host ("Excel: {0} ({1})" -f $Excel, $xlsxInfo.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))
}
Write-Host ("PBIP: {0}" -f $Pbip)
Write-Host ""
Write-Host "Apos abrir, clique em Atualizar (F5) no Power BI." -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $Pbip)) {
    Write-Host "[ERRO] PBIP nao encontrado: $Pbip" -ForegroundColor Red
    exit 1
}

$pbi = Find-PBIDesktopExe
if (-not $pbi) {
    Write-Host "[ERRO] PBIDesktop.exe nao encontrado." -ForegroundColor Red
    Write-Host "Abra o Power BI manualmente: File > Open > Browse > $Pbip"
    exit 1
}

# Fecha instancia anterior para evitar conflito de projeto
Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$proc = Start-Process -FilePath $pbi -ArgumentList @("`"$Pbip`"") -WorkingDirectory $PbipDir -PassThru -Wait:$false
Start-Sleep -Seconds 4

if ($proc -and -not $proc.HasExited) {
    Write-Host "[OK] Power BI iniciado (PID $($proc.Id))" -ForegroundColor Green
    Write-Host "     Clique em Atualizar (F5) para carregar o CSV." -ForegroundColor Green
} else {
    Write-Host "[AVISO] O Power BI pode ter fechado ao abrir o projeto." -ForegroundColor Yellow
    Write-Host "Tente manualmente: File > Open > Browse >" -ForegroundColor Yellow
    Write-Host $Pbip
}

Write-Host ""
exit 0