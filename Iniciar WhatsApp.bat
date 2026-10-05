@echo off
cd /d "%~dp0"
title B2 Gestao - Assistente no WhatsApp (teste)
set "PY=C:\Users\gustavo.paula\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo  B2 Assistente no WhatsApp  -  TESTE com chip dedicado, so dados simulados.
echo  A pagina do QR abre no navegador. Deixe esta janela aberta; Ctrl+C para parar.
echo  Liberar um numero:  python whatsapp_assistente.py --autorizar 42999999999
echo.
"%PY%" whatsapp_assistente.py --abrir %*
echo.
pause
