"""Disparos automáticos do B2 Assistente — o que vai para o celular, e quando.

Cada disparo tem um CONTEÚDO (resumo da rede, alertas, placar da reunião,
auditoria, planilhas pendentes, resumo de um posto) e um QUANDO:

* **horario** — todo dia escolhido, no horário (ex.: 07:30 de seg a dom);
* **chegada** — assim que dados novos entram na base (planilha enviada);
* **limite** — cobrança: no horário, se algum posto não mandou a planilha,
  avisa quem está pendente. Se está tudo em dia, não manda nada.

Vai para TODAS as conversas do robô do Telegram — pessoas e grupos (quem
adiciona o robô ao grupo da diretoria passa a receber ali).

A agenda fica em `data/assistente_agenda.json` (vai para o Git: não tem
segredo). O "já mandei hoje" fica no `config_assistente.local.json`.

Um disparo de horário só sai dentro de `JANELA_MIN` minutos depois da hora:
se o painel foi reiniciado às 14h, ele não manda o bom-dia das 7h atrasado.

Este módulo não usa Streamlit: o agendador roda dentro do painel (thread), e
o `motor_alertas.py --chegada` usa as mesmas funções no GitHub Actions.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from src import alertas as al
from src import analytics, armazenamento, assistente, auditoria, base

ARQ_AGENDA = base.PASTA_DADOS / "assistente_agenda.json"
JANELA_MIN = 15
INTERVALO_S = 20
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
NOMES_DIAS = {"seg": "seg", "ter": "ter", "qua": "qua", "qui": "qui", "sex": "sex", "sab": "sáb", "dom": "dom"}

CONTEUDOS = {
    "resumo rede": "🏪 Resumo da rede",
    "alertas": "🚨 Alertas (o que exige ação)",
    "estoque rede": "📦 Estoque da rede",
    "vendas rede": "💰 Vendas da rede",
    "margem rede": "📈 Margem da rede",
    "reuniao": "📋 Placar das gerências",
    "auditoria": "🛡️ Auditoria (sinais de fraude)",
    "pendencias": "⏳ Planilhas pendentes",
}
QUANDO = {
    "horario": "Todo dia, no horário",
    "chegada": "Assim que os dados chegarem",
    "limite": "Cobrar se não chegar até o horário",
}

PADRAO = [
    {"id": "bom-dia", "nome": "Bom dia da rede", "conteudo": "resumo rede", "quando": "horario",
     "hora": "07:30", "dias": DIAS, "ativo": True},
    {"id": "chegada", "nome": "Alertas quando os dados chegam", "conteudo": "alertas", "quando": "chegada",
     "hora": "", "dias": DIAS, "ativo": True},
    {"id": "cobranca", "nome": "Cobrança de planilhas", "conteudo": "pendencias", "quando": "limite",
     "hora": "10:00", "dias": DIAS[:6], "ativo": True},
    {"id": "placar", "nome": "Placar para a reunião de segunda", "conteudo": "reuniao", "quando": "horario",
     "hora": "08:00", "dias": ["seg"], "ativo": True},
]


def agora() -> datetime:
    return auditoria.agora()


# --------------------------------------------------------------- agenda -----
def carregar() -> list[dict]:
    if ARQ_AGENDA.exists():
        try:
            itens = json.loads(ARQ_AGENDA.read_text(encoding="utf-8"))
            if isinstance(itens, list):
                return itens
        except ValueError:
            pass
    return [dict(i) for i in PADRAO]


def salvar(itens: list[dict]):
    ARQ_AGENDA.parent.mkdir(parents=True, exist_ok=True)
    temp = ARQ_AGENDA.with_suffix(".tmp")
    temp.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(ARQ_AGENDA)


def descrever(item: dict) -> str:
    conteudo = CONTEUDOS.get(item["conteudo"]) or f"⛽ {item['conteudo'].replace('resumo ', 'Resumo ')}"
    if item["quando"] == "chegada":
        return f"{conteudo} · assim que os dados chegarem"
    dias = item.get("dias") or DIAS
    if dias == DIAS:
        quais = "todo dia"
    elif dias == DIAS[:5]:
        quais = "seg a sex"
    elif dias == DIAS[:6]:
        quais = "seg a sáb"
    else:
        quais = ", ".join(NOMES_DIAS[d] for d in dias)
    prefixo = "cobra às" if item["quando"] == "limite" else "às"
    return f"{conteudo} · {prefixo} {item['hora']} · {quais}"


def devidos(itens: list[dict], momento: datetime, estado: dict, chegou: bool) -> list[dict]:
    """Os disparos que vencem agora. Pura: é o que os testes conferem."""
    hoje = momento.strftime("%Y-%m-%d")
    dia = DIAS[momento.weekday()]
    saida = []
    for item in itens:
        if not item.get("ativo"):
            continue
        if item["quando"] == "chegada":
            if chegou:
                saida.append(item)
            continue
        if dia not in (item.get("dias") or DIAS) or estado.get(item["id"]) == hoje:
            continue
        try:
            h, m = map(int, item["hora"].split(":"))
        except (ValueError, AttributeError):
            continue
        inicio = momento.replace(hour=h, minute=m, second=0, microsecond=0)
        if inicio <= momento < inicio + timedelta(minutes=JANELA_MIN):
            saida.append(item)
    return saida


# ---------------------------------------------------------------- dados -----
def carregar_dados() -> dict:
    """Tudo o que os conteúdos usam, lido da base (sem Streamlit)."""
    b = base.carregar()
    df = analytics.preparar(b.movimento)
    postos = b.postos["posto"].tolist()
    aud = auditoria.ler()
    return {"df": df, "tanques": b.tanques, "postos": postos,
            "alertas": al.gerar(df, b.tanques, postos, auditoria=aud),
            "extras": {"despesas": b.despesas, "compras": b.compras, "auditoria": aud,
                       "envios": armazenamento.ler_envios()},
            "simulado": (base.PASTA_DADOS / "SIMULADO.txt").exists()}


def gerar_conteudo(item: dict, d: dict, chegaram: list[str] | None = None) -> assistente.Resposta | None:
    """A mensagem do disparo — ou None quando não há o que dizer (cobrança
    com todos em dia)."""
    extras = dict(d["extras"])
    if item["conteudo"] == "pendencias":
        # Na vida real, o esperado é o dia de ontem; na demonstração (dados
        # parados no tempo), a régua é o posto mais adiantado da rede.
        ref = d["df"]["data"].max() if d["simulado"] else pd.Timestamp(agora().date() - timedelta(days=1))
        if not assistente.pendencias(d["df"], d["postos"], ref):
            return None
        extras["referencia"] = ref
    r = assistente.responder(item["conteudo"], d["df"], d["tanques"], d["postos"], simulado=d["simulado"],
                             alertas=d["alertas"], extras=extras)
    if item["quando"] == "chegada":
        quem = ", ".join(p.replace("B2 ", "") for p in (chegaram or [])) or "a rede"
        r = assistente.Resposta(f"📥 Dados novos — {quem}", r.titulo + "\n\n" + r.mensagem, r.sugestoes)
    elif item["quando"] == "horario":
        r = assistente.Resposta(f"⏰ {item['nome']}", r.titulo + "\n\n" + r.mensagem, r.sugestoes)
    return r


def ultimas_por_posto(d: dict) -> dict:
    return {p: d["df"].loc[d["df"]["posto"] == p, "data"].max() for p in d["postos"]}


# ------------------------------------------------------------- agendador ----
class Agendador:
    """Fica no ar dentro do painel e dispara na hora certa."""

    def __init__(self, dados: Callable[[], dict], enviar: Callable[[assistente.Resposta], tuple[int, str]],
                 assinatura: Callable[[], tuple], ler_estado: Callable[[], dict],
                 gravar_estado: Callable[[dict], None]):
        self._dados, self._enviar, self._assinatura = dados, enviar, assinatura
        self._ler_estado, self._gravar_estado = ler_estado, gravar_estado
        self._parada = threading.Event()
        self._thread: threading.Thread | None = None
        self._ultima_assinatura = None
        self._ultimas: dict = {}
        self.historico: list[tuple[datetime, str, str]] = []

    def iniciar(self):
        if self._thread and self._thread.is_alive():
            return
        self._parada.clear()
        self._thread = threading.Thread(target=self._laco, name="b2-agendador", daemon=True)
        self._thread.start()

    def parar(self):
        self._parada.set()

    def disparar(self, item: dict, chegaram: list[str] | None = None) -> tuple[int, str]:
        try:
            resposta = gerar_conteudo(item, self._dados(), chegaram)
        except Exception as erro:
            self._anotar(item["nome"], f"erro ao montar: {erro}")
            return 0, str(erro)
        if resposta is None:
            self._anotar(item["nome"], "nada a avisar (todos em dia)")
            return 0, "nada a avisar"
        n, erro = self._enviar(resposta)
        self._anotar(item["nome"], f"enviado para {n} conversa(s)" if n else (erro or "nenhuma conversa"))
        return n, erro

    def _anotar(self, nome: str, resultado: str):
        self.historico.insert(0, (agora(), nome, resultado))
        del self.historico[30:]

    def _laco(self):
        while not self._parada.is_set():
            try:
                self._tique()
            except Exception as erro:
                self._anotar("agendador", f"falha: {erro}")
            self._parada.wait(INTERVALO_S)

    def _tique(self):
        assinatura = self._assinatura()
        chegou = self._ultima_assinatura is not None and assinatura != self._ultima_assinatura
        d = self._dados()
        ultimas = ultimas_por_posto(d)
        chegaram = [p for p, u in ultimas.items() if self._ultimas and u != self._ultimas.get(p)]
        self._ultima_assinatura, self._ultimas = assinatura, ultimas
        momento = agora()
        estado = self._ler_estado()
        for item in devidos(carregar(), momento, estado, chegou):
            self.disparar(item, chegaram)
            if item["quando"] != "chegada":
                estado[item["id"]] = momento.strftime("%Y-%m-%d")
                self._gravar_estado(estado)


# ---------------------------------------------- fora do painel (Actions) ----
def disparar_chegada_fora_do_painel() -> list[str]:
    """Usado pelo `motor_alertas.py --chegada` depois que a base nova é montada
    na nuvem: manda os disparos de "chegada" direto pela API do Telegram."""
    from src import assistente_telegram as tg
    from src import notificacoes
    token, chats = notificacoes.telegram_destinos()
    log = []
    if not (token and chats):
        return ["Telegram sem token ou sem conversas — nada enviado."]
    d = carregar_dados()
    for item in carregar():
        if item.get("ativo") and item["quando"] == "chegada":
            resposta = gerar_conteudo(item, d)
            if resposta is None:
                continue
            for chat in chats:
                try:
                    tg.enviar_mensagem(token, chat, resposta)
                    log.append(f"{item['nome']} → conversa {chat}: ok")
                except Exception as erro:
                    log.append(f"{item['nome']} → conversa {chat}: {erro}")
    return log
