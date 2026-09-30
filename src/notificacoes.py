"""Envio de alerta para o celular — ntfy, Pushover ou só na tela (console).

    enviar_alerta(titulo="🔴 Estoque crítico",
                  mensagem="B2 Candói • Diesel S10 • autonomia 0,9 dia",
                  url="https://b2gestao.streamlit.app")

O canal vem do `config_alertas.toml` (na raiz) e pode ser trocado por
variável de ambiente — é assim que o GitHub Actions passa os segredos sem
gravá-los em arquivo:

    B2_CANAL=ntfy  B2_NTFY_TOPICO=...  B2_PUSHOVER_TOKEN=...  B2_PUSHOVER_USUARIO=...

* **ntfy** — aplicativo gratuito e de código aberto. O dono instala o app,
  assina o tópico e pronto. Use um nome de tópico difícil de adivinhar: no
  ntfy.sh público, quem souber o nome lê as mensagens.
* **Pushover** — aplicativo pago uma vez por plataforma, com período de
  teste; precisa do token do aplicativo e da chave do usuário.
* **telegram** — o mesmo robô do 💬 B2 Assistente: manda para todas as
  conversas que tocaram em Iniciar. Token e conversas vêm do
  `config_assistente.local.json` (ou de B2_TELEGRAM_TOKEN / B2_TELEGRAM_CHATS).
* **console** — o padrão: só imprime. Nada sai da máquina até alguém
  configurar um canal de propósito.
"""
from __future__ import annotations

import base64
import json
import os
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ_CONFIG = RAIZ / "config_alertas.toml"

PRIORIDADE_NTFY = {"critico": "urgent", "atencao": "high", "destaque": "default"}
PRIORIDADE_PUSHOVER = {"critico": 1, "atencao": 0, "destaque": -1}
TAGS_NTFY = {"critico": "rotating_light", "atencao": "warning", "destaque": "white_check_mark"}


def config() -> dict:
    cfg = {"envio": {"canal": "console", "niveis": ["critico", "atencao"], "url_painel": ""},
           "ntfy": {"servidor": "https://ntfy.sh", "topico": ""},
           "pushover": {"token": "", "usuario": ""}}
    if ARQ_CONFIG.exists():
        with open(ARQ_CONFIG, "rb") as f:
            lido = tomllib.load(f)
        for secao, valores in lido.items():
            cfg.setdefault(secao, {}).update(valores)
    amb = {
        ("envio", "canal"): "B2_CANAL", ("envio", "url_painel"): "B2_URL_PAINEL",
        ("ntfy", "topico"): "B2_NTFY_TOPICO", ("ntfy", "servidor"): "B2_NTFY_SERVIDOR",
        ("pushover", "token"): "B2_PUSHOVER_TOKEN", ("pushover", "usuario"): "B2_PUSHOVER_USUARIO",
    }
    for (secao, chave), var in amb.items():
        if os.environ.get(var):
            cfg[secao][chave] = os.environ[var]
    return cfg


def telegram_destinos() -> tuple[str, list[int]]:
    """Token e conversas do robô — os mesmos do 💬 B2 Assistente."""
    token, chats = os.environ.get("B2_TELEGRAM_TOKEN", ""), []
    local = RAIZ / "config_assistente.local.json"
    if local.exists():
        try:
            dados = json.loads(local.read_text(encoding="utf-8"))
            token = token or dados.get("telegram_token", "")
            chats = [int(c) for c in dados.get("telegram_chats", [])]
        except (ValueError, TypeError):
            pass
    if os.environ.get("B2_TELEGRAM_CHATS"):
        chats = [int(c) for c in os.environ["B2_TELEGRAM_CHATS"].split(",") if c.strip()]
    return token, chats


def canal_pronto(cfg: dict | None = None) -> tuple[str, bool, str]:
    """(canal, está configurado?, explicação)"""
    cfg = cfg or config()
    canal = cfg["envio"]["canal"]
    if canal == "telegram":
        token, chats = telegram_destinos()
        ok = bool(token and chats)
        return canal, ok, (f"{len(chats)} conversa(s) no robô" if ok else
                           "conecte o robô no 💬 B2 Assistente e toque em Iniciar no Telegram")
    if canal == "ntfy":
        ok = bool(cfg["ntfy"]["topico"])
        return canal, ok, "tópico configurado" if ok else "falta o tópico do ntfy"
    if canal == "pushover":
        ok = bool(cfg["pushover"]["token"] and cfg["pushover"]["usuario"])
        return canal, ok, "token e usuário configurados" if ok else "faltam o token e a chave do usuário"
    return "console", True, "modo demonstração: os alertas só aparecem na tela e no terminal"


def enviar_alerta(titulo: str, mensagem: str, url: str = "", nivel: str = "atencao",
                  cfg: dict | None = None) -> tuple[bool, str]:
    cfg = cfg or config()
    canal, pronto, motivo = canal_pronto(cfg)
    if not pronto:
        return False, motivo
    try:
        if canal == "telegram":
            from src import assistente_telegram as tg
            from src.assistente import Resposta
            token, chats = telegram_destinos()
            for chat in chats:
                tg.enviar_mensagem(token, chat, Resposta(titulo, mensagem))
            return True, f"telegram: {len(chats)} conversa(s)"
        if canal == "ntfy":
            destino = f"{cfg['ntfy']['servidor'].rstrip('/')}/{cfg['ntfy']['topico']}"
            # Título com acento/emoji vai codificado (RFC 2047), que o ntfy aceita.
            cab = {"Title": "=?UTF-8?B?" + base64.b64encode(titulo.encode()).decode() + "?=",
                   "Priority": PRIORIDADE_NTFY.get(nivel, "default"), "Tags": TAGS_NTFY.get(nivel, "")}
            if url:
                cab["Click"] = url
            req = urllib.request.Request(destino, data=mensagem.encode("utf-8"), headers=cab, method="POST")
        elif canal == "pushover":
            dados = {"token": cfg["pushover"]["token"], "user": cfg["pushover"]["usuario"],
                     "title": titulo, "message": mensagem, "priority": PRIORIDADE_PUSHOVER.get(nivel, 0)}
            if url:
                dados.update(url=url, url_title="Abrir o painel")
            req = urllib.request.Request("https://api.pushover.net/1/messages.json",
                                         data=urllib.parse.urlencode(dados).encode(), method="POST")
        else:
            print(f"[{nivel.upper()}] {titulo}\n{mensagem}\n")
            return True, "mostrado no terminal"
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300, f"{canal}: HTTP {r.status}"
    except Exception as erro:
        return False, f"{canal}: {erro}"
