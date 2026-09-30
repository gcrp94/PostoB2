"""B2 Assistente pelo Telegram — conversa de verdade, com botões.

Por que Telegram na demonstração (e não só ntfy): o dono conversa como no
WhatsApp — digita "estoque candói" ou toca num botão (⛽ Candói, 🚨 Alertas)
e a resposta chega em um segundo. Criar o robô leva um minuto dentro do
próprio Telegram (@BotFather) e não precisa de servidor: este módulo
"pergunta" ao Telegram se há mensagem nova (long polling), então funciona no
notebook da apresentação, atrás de qualquer Wi-Fi.

Só biblioteca padrão (urllib). O token do robô nunca aparece em mensagem de
erro nem na tela — ele vai na URL, e a URL não é mostrada.

A inteligência não mora aqui: `responder(texto)` é injetado (é o
`assistente.responder` com a base carregada). Este módulo só transporta.
"""
from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

API = "https://api.telegram.org"
TIMEOUT_ESPERA = 25          # segundos que o Telegram segura o getUpdates
MAX_TEXTO = 4_000            # limite do Telegram é 4.096
PADRAO_TOKEN = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,60}$")

# Teclado fixo embaixo da conversa: a demonstração inteira em toques.
TECLADO = [
    ["🏪 Resumo da rede", "🚨 Alertas"],
    ["⛽ Centro", "⛽ Bonsucesso", "⛽ Primavera"],
    ["⛽ Índio", "⛽ Candói", "📦 Estoque da rede"],
]


class ErroTelegram(Exception):
    """Falha já traduzida para a tela — sem URL, sem token."""


def token_valido(token: str) -> bool:
    return bool(PADRAO_TOKEN.match(token.strip()))


def _chamar(token: str, metodo: str, dados: dict | None = None, timeout: int = 20) -> object:
    """Chama a API do Telegram. Erros viram ErroTelegram com texto limpo."""
    req = urllib.request.Request(
        f"{API}/bot{token}/{metodo}", method="POST",
        data=json.dumps(dados or {}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "B2-Gestao/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corpo = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 404):
            raise ErroTelegram("O Telegram recusou o código do robô. Confira o token copiado do @BotFather.")
        if erro.code == 409:
            raise ErroTelegram("Este robô já está conectado em outra janela do painel. Feche a outra.")
        if erro.code == 403:
            raise ErroTelegram("Esta conversa bloqueou o robô.")
        raise ErroTelegram(f"O Telegram respondeu com erro {erro.code}.")
    except (TimeoutError, urllib.error.URLError) as erro:
        motivo = getattr(erro, "reason", erro)
        if isinstance(motivo, TimeoutError) or isinstance(erro, TimeoutError):
            raise TimeoutError("sem novidade") from None
        raise ErroTelegram("Sem conexão com o Telegram. Verifique a internet.") from None
    if not isinstance(corpo, dict) or not corpo.get("ok"):
        raise ErroTelegram("O Telegram não aceitou o pedido.")
    return corpo.get("result")


def formatar(resposta) -> str:
    """Título em negrito + corpo, em HTML seguro para o Telegram."""
    texto = f"<b>{html.escape(resposta.titulo)}</b>\n\n{html.escape(resposta.mensagem)}"
    return texto if len(texto) <= MAX_TEXTO else texto[:MAX_TEXTO - 1] + "…"


def botoes(resposta) -> dict | None:
    """As sugestões da resposta viram botões embaixo dela (até 3 por linha)."""
    sug = [s for s in getattr(resposta, "sugestoes", ()) if len(s[1].encode("utf-8")) <= 64]
    if not sug:
        return None
    linhas = [sug[i:i + 3] for i in range(0, len(sug), 3)]
    return {"inline_keyboard": [[{"text": r, "callback_data": c} for r, c in linha] for linha in linhas]}


def enviar_mensagem(token: str, chat_id: int, resposta, teclado_fixo: bool = False) -> None:
    dados = {"chat_id": chat_id, "text": formatar(resposta), "parse_mode": "HTML",
             "disable_web_page_preview": True}
    if teclado_fixo:
        dados["reply_markup"] = {"keyboard": [[{"text": t} for t in linha] for linha in TECLADO],
                                 "resize_keyboard": True, "is_persistent": True,
                                 "input_field_placeholder": "Pergunte: estoque candói"}
    else:
        inline = botoes(resposta)
        if inline:
            dados["reply_markup"] = inline
    _chamar(token, "sendMessage", dados)


@dataclass
class _Sessao:
    parada: threading.Event
    offset: int | None = None
    conhecidos: set = field(default_factory=set)


class ServicoTelegram:
    """Um robô por processo: escuta, responde e guarda quem conversou."""

    def __init__(self, token: str, responder: Callable[[str], object],
                 chats: list[int] | None = None, ao_registrar: Callable[[int, str], None] | None = None):
        token = token.strip()
        if not token_valido(token):
            raise ValueError("Isso não parece um token do @BotFather (formato 123456789:ABC…).")
        self._token = token
        self._responder = responder
        self._ao_registrar = ao_registrar
        self._lock = threading.RLock()
        self._sessao: _Sessao | None = None
        self._chats: dict[int, str] = {int(c): "" for c in (chats or [])}
        self._estado = dict(ativo=False, conectado=False, erro="", bot_usuario="", bot_nome="",
                            ultimo_comando="", ultima_resposta="", respostas=0)

    # ------------------------------------------------------------ controle
    def iniciar(self) -> None:
        with self._lock:
            if self._sessao is not None and not self._sessao.parada.is_set():
                return
            sessao = _Sessao(threading.Event(), conhecidos=set(self._chats))
            self._sessao = sessao
            self._estado.update(ativo=True, conectado=False, erro="")
            threading.Thread(target=self._executar, args=(sessao,), name="b2-assistente-telegram",
                             daemon=True).start()

    def parar(self) -> None:
        with self._lock:
            if self._sessao is not None:
                self._sessao.parada.set()
            self._estado.update(ativo=False, conectado=False)

    def status(self) -> dict:
        with self._lock:
            estado = dict(self._estado)
            estado["chats"] = len(self._chats)
            return estado

    def chats(self) -> list[int]:
        with self._lock:
            return list(self._chats)

    def _atualizar(self, sessao: _Sessao, **valores) -> None:
        with self._lock:
            if self._sessao is sessao and not sessao.parada.is_set():
                self._estado.update(valores)

    # ------------------------------------------------------------ envio
    def enviar_para_todos(self, resposta) -> tuple[int, str]:
        """Manda a mesma mensagem a todas as conversas registradas (os alertas)."""
        enviados, ultimo_erro = 0, ""
        for chat in self.chats():
            try:
                enviar_mensagem(self._token, chat, resposta)
                enviados += 1
            except (ErroTelegram, TimeoutError) as erro:
                ultimo_erro = str(erro)
        return enviados, ultimo_erro

    def _registrar(self, chat_id: int, nome: str) -> bool:
        with self._lock:
            novo = chat_id not in self._chats
            self._chats[chat_id] = nome
        if novo and self._ao_registrar:
            try:
                self._ao_registrar(chat_id, nome)
            except Exception:
                pass            # guardar a conversa é conveniência; responder é o que importa
        return novo

    # ------------------------------------------------------------ recepção
    def _tratar(self, atualizacao: dict, sessao: _Sessao) -> None:
        if sessao.parada.is_set() or not isinstance(atualizacao, dict):
            return
        clique = atualizacao.get("callback_query")
        if isinstance(clique, dict):
            mensagem = clique.get("message") or {}
            chat = (mensagem.get("chat") or {}).get("id")
            texto = clique.get("data") or ""
            try:
                _chamar(self._token, "answerCallbackQuery", {"callback_query_id": clique.get("id")})
            except (ErroTelegram, TimeoutError):
                pass
            nome = (clique.get("from") or {}).get("first_name", "")
        else:
            mensagem = atualizacao.get("message") or {}
            chat = (mensagem.get("chat") or {}).get("id")
            texto = mensagem.get("text") or ""
            nome = (mensagem.get("from") or {}).get("first_name", "")
        if not isinstance(chat, int) or not isinstance(texto, str) or not texto.strip():
            return
        texto = texto.strip()[:300]
        novo = self._registrar(chat, nome)
        inicio = texto.lower().startswith(("/start", "/menu", "/ajuda"))
        comando = "ajuda" if inicio else texto
        self._atualizar(sessao, ultimo_comando=texto)
        try:
            _chamar(self._token, "sendChatAction", {"chat_id": chat, "action": "typing"}, timeout=10)
        except (ErroTelegram, TimeoutError):
            pass
        try:
            resposta = self._responder(comando)
        except ValueError as erro:
            resposta = _Simples("🤖 B2 Gestão", str(erro))
        except Exception:
            resposta = _Simples("🤖 B2 Gestão", "Não consegui consultar os dados agora. Tente de novo.")
        try:
            # Na primeira conversa (ou no /start) vai o teclado fixo com os botões.
            enviar_mensagem(self._token, chat, resposta, teclado_fixo=inicio or novo)
            if inicio or novo:
                inline = botoes(resposta)
                if inline:
                    _chamar(self._token, "sendMessage", {"chat_id": chat, "text": "Mais opções 👇",
                                                          "reply_markup": inline})
            with self._lock:
                self._estado["respostas"] += 1
            self._atualizar(sessao, ultima_resposta=resposta.titulo, erro="")
        except ErroTelegram as erro:
            self._atualizar(sessao, erro=str(erro))

    def _executar(self, sessao: _Sessao) -> None:
        espera = 1
        while not sessao.parada.is_set():
            try:
                if not self._estado["bot_usuario"]:
                    eu = _chamar(self._token, "getMe")
                    self._atualizar(sessao, bot_usuario=eu.get("username", ""), bot_nome=eu.get("first_name", ""))
                if sessao.offset is None:
                    # Ignora o que ficou parado na fila antes de ligar: responder
                    # pergunta de ontem na frente do comprador seria estranho.
                    antigas = _chamar(self._token, "getUpdates", {"offset": -1, "timeout": 0})
                    sessao.offset = (antigas[-1]["update_id"] + 1) if antigas else 0
                self._atualizar(sessao, conectado=True, erro="")
                novas = _chamar(self._token, "getUpdates",
                                {"offset": sessao.offset, "timeout": TIMEOUT_ESPERA,
                                 "allowed_updates": ["message", "callback_query"]},
                                timeout=TIMEOUT_ESPERA + 10)
                for atualizacao in novas or []:
                    sessao.offset = max(sessao.offset, int(atualizacao.get("update_id", 0)) + 1)
                    self._tratar(atualizacao, sessao)
                espera = 1
                continue
            except TimeoutError:
                continue                     # espera longa sem novidade: normal
            except ErroTelegram as erro:
                self._atualizar(sessao, conectado=False, erro=str(erro))
            except Exception:
                self._atualizar(sessao, conectado=False, erro="Falha inesperada ao falar com o Telegram.")
            if sessao.parada.wait(espera):
                break
            espera = min(espera * 2, 30)


@dataclass(frozen=True)
class _Simples:
    titulo: str
    mensagem: str
    sugestoes: tuple = (("🏪 Resumo da rede", "resumo rede"), ("🚨 Alertas", "alertas"))
