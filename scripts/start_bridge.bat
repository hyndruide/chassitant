@echo off
title Chassitant Bridge (Antigravity agy)
cd /d "%~dp0\.."
echo Verification de Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas installe ou n'est pas dans le PATH.
    pause
    exit /b 1
)
python bridge\server.py
pause
