@echo off
cd /d "%~dp0"
title B2 Gestao - Dados simulados
set "PY=C:\Users\gustavo.paula\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"
echo ATENCAO: isto SOBRESCREVE as planilhas simuladas em data\ (12 meses, 5 postos).
echo Use antes de uma apresentacao, para voltar ao cenario original.
echo Quando os dados reais chegarem, NAO rode este arquivo.
echo.
choice /M "Continuar"
if errorlevel 2 exit /b 0
"%PY%" gerar_dados_simulados.py
"%PY%" gerar_base.py
echo.
echo Pronto. Abra o painel com o "Abrir App.bat".
pause