# Script de lancement PowerShell pour Chassitant Bridge
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

Write-Host "Vérification de Python..." -ForegroundColor Cyan
try {
    $pyVersion = python --version 2>&1
    Write-Host "Python détecté: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERREUR] Python n'est pas installé ou introuvable dans le PATH." -ForegroundColor Red
    exit 1
}

python bridge/server.py
