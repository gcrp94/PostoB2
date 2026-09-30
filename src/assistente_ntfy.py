"""Transporte da demonstração de comandos pelo ntfy, sem dependência da UI.

O tópico é exclusivo do assistente. As respostas recebem a tag
``b2-resposta`` para não serem interpretadas como novos comandos.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Protocol


class Resposta(Protocol):
    titulo: str
    mensagem: str


@dataclass(frozen=True)
class _Ajuda:
    titulo: str = "🤖 B2 Gestão — ajuda"
    mensagem: str = "Não entendi o comando. Envie ajuda para ver as consultas disponíveis."


@dataclass
class _Sessao:
    parada: threading.Event
    inicio: int
    ultimo_id: str = ""
    vistos: OrderedDict = field(default_factory=OrderedDict)
    pendente: tuple[str, Resposta] | None = None


TIMEOUT = 20
MAX_COMANDO = 600
MAX_LINHA = 16_384
MAX_MENSAGEM = 4_096
TAG_RESPOSTA = "b2-resposta"


class ServicoNtfy:
    def __init__(self, servidor: str, topico: str,
                 responder: Callable[[str], Resposta], token: str = ""):
        servidor = servidor.strip().rstrip("/")
        partes = urllib.parse.urlsplit(servidor)
        if (partes.scheme not in {"http", "https"} or not partes.hostname
                or partes.username or partes.password or partes.query or partes.fragment
                or any(c.isspace() for c in servidor)):
            raise ValueError("Informe um servidor ntfy com endereço http:// ou https:// válido.")
        try:
            partes.port
        except ValueError as erro:
            raise ValueError("A porta do servidor ntfy é inválida.") from erro
        if not re.fullmatch(r"[A-Za-z0-9_-]+", topico):
            raise ValueError("O tópico aceita apenas letras, números, hífen e sublinhado.")
        if "\r" in token or "\n" in token:
            raise ValueError("O token ntfy é inválido.")
        self.servidor, self.topico = servidor, topico
        self._responder, self._token = responder, token.strip()
        self._lock = threading.RLock()
        self._sessao: _Sessao | None = None
        self._thread: threading.Thread | None = None
        self._estado = dict(ativo=False, conectado=False, erro="",
                            ultimo_comando="", ultima_resposta="")

    def iniciar(self) -> None:
        """Inicia uma única escuta; repetições durante a execução não fazem nada."""
        with self._lock:
            if self._sessao is not None and not self._sessao.parada.is_set():
                return
            sessao = _Sessao(threading.Event(), int(time.time()))
            self._sessao = sessao
            self._estado.update(ativo=True, conectado=False, erro="")
            self._thread = threading.Thread(target=self._executar, args=(sessao,),
                                            name="b2-assistente-ntfy", daemon=True)
            self._thread.start()

    def parar(self) -> None:
        """Para novas ações; uma leitura HTTP em curso termina em até 20 segundos."""
        with self._lock:
            if self._sessao is not None:
                self._sessao.parada.set()
            self._estado.update(ativo=False, conectado=False)

    def status(self) -> dict:
        with self._lock:
            return dict(self._estado)

    def _estado_da_sessao(self, sessao: _Sessao, **valores) -> None:
        with self._lock:
            if self._sessao is sessao and not sessao.parada.is_set():
                self._estado.update(valores)

    def _cabecalhos(self) -> dict:
        cab = {"Accept": "application/json", "User-Agent": "B2-Gestao-Demo/1.0"}
        if self._token:
            cab["Authorization"] = f"Bearer {self._token}"
        return cab

    @staticmethod
    def _erro_rede(erro: Exception) -> str:
        # Não incluir URL, tópico privado ou token em mensagens da interface.
        if isinstance(erro, urllib.error.HTTPError):
            return f"O ntfy respondeu HTTP {erro.code}. Confira o servidor e o acesso ao tópico."
        return "Não foi possível comunicar com o ntfy. Verifique a conexão e tente novamente."

    def _publicar(self, resposta: Resposta) -> tuple[bool, str]:
        try:
            titulo, mensagem = resposta.titulo, resposta.mensagem
            if (not isinstance(titulo, str) or not isinstance(mensagem, str)
                    or not titulo.strip() or not mensagem.strip()
                    or len(titulo.encode("utf-8")) > 256
                    or len(mensagem.encode("utf-8")) > MAX_MENSAGEM):
                return False, "A resposta está vazia ou excede o limite de tamanho do ntfy."
            corpo = {"topic": self.topico, "title": titulo, "message": mensagem,
                     "tags": ["robot", TAG_RESPOSTA], "priority": 3}
            cab = self._cabecalhos()
            cab["Content-Type"] = "application/json; charset=utf-8"
            req = urllib.request.Request(self.servidor + "/", method="POST", headers=cab,
                                         data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"))
            with urllib.request.urlopen(req, timeout=TIMEOUT) as retorno:
                if not 200 <= retorno.status < 300:
                    return False, f"O ntfy respondeu HTTP {retorno.status}."
                publicado = json.loads(retorno.read(MAX_LINHA))
                if not isinstance(publicado, dict) or not publicado.get("id"):
                    return False, "O ntfy não confirmou o recebimento da resposta."
            return True, "Resposta enviada ao ntfy."
        except (AttributeError, TypeError, ValueError):
            return False, "A resposta ou a confirmação do ntfy é inválida."
        except Exception as erro:
            return False, self._erro_rede(erro)

    def enviar(self, resposta: Resposta) -> tuple[bool, str]:
        """Publica uma resposta manual e só registra sucesso após confirmação HTTP."""
        ok, detalhe = self._publicar(resposta)
        with self._lock:
            self._estado["erro"] = "" if ok else detalhe
            if ok:
                self._estado["ultima_resposta"] = resposta.mensagem
        return ok, detalhe

    @staticmethod
    def _confirmar(sessao: _Sessao, identificador: str) -> None:
        sessao.ultimo_id = identificador
        sessao.vistos[identificador] = None
        if len(sessao.vistos) > 2_048:
            sessao.vistos.popitem(last=False)

    def _enviar_pendente(self, sessao: _Sessao) -> bool:
        if sessao.parada.is_set() or sessao.pendente is None:
            return False
        identificador, resposta = sessao.pendente
        ok, detalhe = self._publicar(resposta)
        if ok:
            self._confirmar(sessao, identificador)
            sessao.pendente = None
            self._estado_da_sessao(sessao, erro="", ultima_resposta=resposta.mensagem)
        else:
            self._estado_da_sessao(sessao, erro=detalhe)
        return ok

    def _processar(self, evento: object, sessao: _Sessao) -> bool:
        """False interrompe a leitura para tentar novamente a resposta pendente."""
        if sessao.parada.is_set() or not isinstance(evento, dict):
            return True
        if evento.get("event") != "message" or evento.get("topic") != self.topico:
            return True
        identificador, instante = evento.get("id"), evento.get("time")
        if (not isinstance(identificador, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identificador)
                or type(instante) is not int or instante < sessao.inicio
                or identificador in sessao.vistos):
            return True
        tags = evento.get("tags", [])
        titulo = evento.get("title", "")
        mensagem = evento.get("message")
        titulo_bot = isinstance(titulo, str) and titulo.lower().lstrip().startswith(
            ("🤖", "b2 gestão", "b2 gestao", "b2 assistente"))
        if (not isinstance(tags, list) or TAG_RESPOSTA in tags or titulo_bot
                or "attachment" in evento or not isinstance(mensagem, str)
                or not mensagem.strip() or len(mensagem) > MAX_COMANDO):
            self._confirmar(sessao, identificador)
            return True
        comando = mensagem.strip()
        self._estado_da_sessao(sessao, ultimo_comando=comando)
        try:
            resposta = self._responder(comando)
        except ValueError as erro:
            # A consulta também pode recusar dados reais. Não chamar outra
            # consulta como alternativa: preservar o motivo desse bloqueio.
            resposta = _Ajuda(mensagem=str(erro).strip() or _Ajuda().mensagem)
        except Exception:
            resposta = _Ajuda(mensagem="Não consegui consultar os dados agora. Tente novamente ou envie ajuda.")
        sessao.pendente = (identificador, resposta)
        return self._enviar_pendente(sessao)

    def _consumir(self, sessao: _Sessao) -> None:
        desde = sessao.ultimo_id or str(sessao.inicio)
        url = f"{self.servidor}/{self.topico}/json?" + urllib.parse.urlencode({"since": desde})
        req = urllib.request.Request(url, headers=self._cabecalhos())
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fluxo:
            self._estado_da_sessao(sessao, conectado=True, erro="")
            while not sessao.parada.is_set():
                linha = fluxo.readline(MAX_LINHA + 1)
                if not linha:
                    return
                if len(linha) > MAX_LINHA:
                    raise ValueError("Evento ntfy excede o limite.")
                try:
                    evento = json.loads(linha)
                except (UnicodeDecodeError, ValueError):
                    continue
                if not self._processar(evento, sessao):
                    return

    def _executar(self, sessao: _Sessao) -> None:
        espera = 1
        while not sessao.parada.is_set():
            try:
                if sessao.pendente is not None and not self._enviar_pendente(sessao):
                    if sessao.parada.wait(espera):
                        break
                    espera = min(espera * 2, 20)
                    continue
                self._consumir(sessao)
                espera = 1
            except Exception as erro:
                ocioso = isinstance(erro, TimeoutError) or (
                    isinstance(erro, urllib.error.URLError)
                    and isinstance(erro.reason, TimeoutError))
                # O keepalive do ntfy pode levar mais que nosso timeout de
                # parada. Reabrir pelo cursor é normal quando não há comandos.
                self._estado_da_sessao(sessao, erro="" if ocioso else self._erro_rede(erro))
            finally:
                self._estado_da_sessao(sessao, conectado=False)
            if sessao.parada.wait(espera):
                break
            espera = min(espera * 2, 20)
