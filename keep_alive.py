"""Despertador do painel: abre o app num navegador de verdade.

O mesmo do Painel de Finanças (`../DASHBOARD FINANÇAS/keep_alive.py`), com o
endereço e o sinal do B2 Gestão.

Por que um navegador, e não `curl`: a Streamlit Community Cloud só conta como
visita uma SESSÃO do app — a conexão WebSocket que o navegador abre depois de
carregar a página. Uma requisição HTTP comum recebe o HTML e vai embora, sem
abrir sessão nenhuma; para a plataforma, ninguém passou (foi o que aconteceu
no Finanças: o job com `curl` ficava verde e o app dormia do mesmo jeito).

Pela documentação oficial, "All apps without traffic for 12 hours go to
sleep". Quando isso acontece a página mostra "This app has gone to sleep due
to inactivity" e um botão "Yes, get this app back up!" — que só um navegador
consegue clicar.

O script NÃO faz login: chegar à tela de login já é uma sessão completa (o
Python do app roda, desenha o login e para). De quebra, abrir o painel liga
os ouvintes do 💬 B2 Assistente, se estiverem configurados nos Secrets.

Só funciona com o app aberto a visitantes (conferido em 30/09/2026: um
visitante anônimo chega ao painel). Se o app for restrito a e-mails em
*Settings → Sharing*, o navegador automático não tem conta e o job falha.
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("STREAMLIT_APP_URL") or "https://b2gestao.streamlit.app/"

# Texto da tela de login (ver `tela_login` em src/auth.py). É a prova de que o
# Python do app rodou — ou seja, de que houve SESSÃO, que é o que a plataforma
# conta. A moldura da Streamlit aparece mesmo com o app dormindo e não prova
# nada. Se o texto do login mudar, mude aqui.
SINAL_DO_APP = "Painel de gestão da Rede B2 Postos"
BOTAO_ACORDAR = "Yes, get this app back up!"

# Religar um app dormindo leva de meio minuto a alguns minutos.
ESPERA_APP_S = 300
# Depois que o app responde, fica conectado mais um pouco: a sessão precisa
# existir por tempo suficiente para a plataforma registrar a visita.
PERMANENCIA_S = 30


def app_respondeu(page) -> bool:
    """O Python do app rodou? Procura o sinal em TODOS os frames.

    O painel é servido dentro de um iframe (`/~/+/`); a página externa é só a
    moldura da Streamlit, sem texto nenhum. Procurar só nela nunca acharia.
    """
    for frame in page.frames:
        try:
            if frame.get_by_text(SINAL_DO_APP).count() > 0:
                return True
        except Exception:  # frame recarregando no meio da busca
            continue
    return False


def botao_acordar(page):
    """O botão de religar, se estiver na tela — na moldura ou num frame."""
    for frame in page.frames:
        try:
            botao = frame.get_by_role("button", name=BOTAO_ACORDAR)
            if botao.count() > 0 and botao.first.is_visible():
                return botao.first
        except Exception:
            continue
    return None


def main() -> int:
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page()
        print(f"Abrindo {APP_URL}")
        # domcontentloaded, e não networkidle: o app mantém um WebSocket aberto
        # o tempo todo, e "rede ociosa" pode nunca chegar.
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=90_000)

        clicou = False
        respondeu = False
        prazo = time.monotonic() + ESPERA_APP_S
        while time.monotonic() < prazo:
            if app_respondeu(page):
                respondeu = True
                break
            botao = None if clicou else botao_acordar(page)
            if botao is not None:
                print(f"App dormindo. Clicando em '{BOTAO_ACORDAR}'...")
                botao.click()
                clicou = True
            page.wait_for_timeout(5_000)

        if not respondeu:
            # O print responde "dormia? travou? a URL mudou?" sem adivinhar —
            # o workflow o anexa ao job quando este passo falha.
            page.screenshot(path="keep_alive_falha.png", full_page=True)
            print(f"::error::O painel não respondeu em {ESPERA_APP_S} s.")
            navegador.close()
            return 1

        print("App religado e respondendo." if clicou
              else "App já estava acordado e respondeu.")
        page.wait_for_timeout(PERMANENCIA_S * 1000)
        navegador.close()
        print("Sessão registrada — a próxima visita vem pelo agendamento.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
