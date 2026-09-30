@echo off
cd /d "%~dp0"
title B2 Gestao - Painel da Rede B2 Postos
set "PY=C:\Users\gustavo.paula\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

rem Evita a pergunta de "boas-vindas" (e-mail) do Streamlit na primeira vez.
if not exist "%UserProfile%\.streamlit" mkdir "%UserProfile%\.streamlit"
if not exist "%UserProfile%\.streamlit\credentials.toml" (
    echo [general] > "%UserProfile%\.streamlit\credentials.toml"
    echo email = "" >> "%UserProfile%\.streamlit\credentials.toml"
)

rem Primeira vez nesta maquina: sem planilhas, gera as simuladas; sem base, monta.
if not exist "data\CADASTRO DOS POSTOS.xlsx" (
    echo Primeira execucao: gerando as planilhas simuladas...
    "%PY%" gerar_dados_simulados.py
)
if not exist "data\base\movimento.parquet" (
    echo Montando a base do painel...
    "%PY%" gerar_base.py
)

echo.
echo  ==============================================
echo    B2 GESTAO - Painel da Rede B2 Postos
echo  ==============================================
echo   Abrindo no navegador: http://localhost:8520
echo   Deixe esta janela aberta enquanto usa o painel.
echo   O robo do celular (Telegram) liga sozinho quando o navegador abrir.
echo   Para o celular na mesma rede Wi-Fi, use o endereco
echo   "Network URL" que aparece logo abaixo.
echo.
"%PY%" -m streamlit run app.py --server.port=8520 --server.headless=false
pause