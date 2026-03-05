@echo off
title DWG Quality Checker
"C:\Users\Luizq\Programming\AutomacaoAutocad\.venv\Scripts\python.exe" "%~dp0launcher.py"
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Algo deu errado. Pressione qualquer tecla para fechar.
    pause >nul
)
