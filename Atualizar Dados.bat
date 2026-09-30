@echo off
cd /d "%~dp0"
title B2 Gestao - Atualizar dados
set "PY=C:\Users\gustavo.paula\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"
echo Lendo as planilhas dos postos e montando a base do painel...
echo.
"%PY%" gerar_base.py
if errorlevel 1 (
    echo.
    echo A base NAO foi atualizada. Veja as mensagens acima. O painel continua com os dados anteriores.
    pause
    exit /b 1
)
echo.
echo Rodando o motor de alertas...
"%PY%" motor_alertas.py
echo.
echo Pronto. Se o painel estiver aberto, aperte F5 no navegador.
pause