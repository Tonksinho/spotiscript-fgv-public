# Registra a tarefa quinzenal do SpotiScript (a cada 15 dias).
# O script coletar.py também valida o intervalo; use --force para antecipar.
# Execute no PowerShell:  .\agendar_tarefas.ps1

$ErrorActionPreference = "Stop"

$WorkDir = $PSScriptRoot
$Python  = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    $Python = "C:\Python314\python.exe"
}

if (-not (Test-Path $Python)) {
    throw "Python não encontrado. Instale Python 3 e garanta que 'python' está no PATH."
}
if (-not (Test-Path $WorkDir)) {
    throw "Pasta do projeto não encontrada: $WorkDir"
}

$action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "coletar.py --slot agendado" `
    -WorkingDirectory $WorkDir

$start = (Get-Date).Date.AddHours(10)
if ($start -lt (Get-Date)) {
    $start = $start.AddDays(1)
}

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $start `
    -RepetitionInterval (New-TimeSpan -Days 15) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$oldNames = @(
    "SpotiScript Diario",
    "SpotiScript Manha",
    "SpotiScript Tarde"
)
foreach ($name in $oldNames) {
    $old = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($old) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "[OK] Tarefa antiga removida: $name"
    }
}

Register-ScheduledTask `
    -TaskName "SpotiScript Quinzenal" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Coleta quinzenal: Analytics CSV + planilha principal + Google Sheets + dashboard" `
    -Force | Out-Null

Write-Host "[OK] Tarefa registrada: SpotiScript Quinzenal"
Write-Host ""
Write-Host "Agendamento:"
Write-Host "  - A cada 15 dias às 10:00 (primeira execução: $($start.ToString('dd/MM/yyyy HH:mm')))"
Write-Host "  - Pipeline: spotiscrap -> export analytics -> consolidar -> Google Sheets -> dashboard"
Write-Host "  - Rodar agora: python coletar.py --force"
Write-Host ""
Write-Host "Status: $WorkDir\data\coleta_status\ultima_coleta_ok.json"
Write-Host "Log:    $WorkDir\data\coleta_agendada.log"