@echo off
cd /d "%~dp0"
title B2 Gestao - Coleta do Menor Preco (Nota Parana)
set "PY=C:\Users\gustavo.paula\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

rem Uma coleta por dia (o proprio script recusa a segunda). Para agendar todo dia:
rem   schtasks /Create /SC DAILY /ST 08:30 /TN "B2 Menor Preco" /TR "\"%~f0\""
"%PY%" coletar_nota_parana.py %*
echo.
timeout /t 20
