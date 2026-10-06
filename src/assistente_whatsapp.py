"""B2 Assistente pelo WhatsApp — sessão logada num chip dedicado. TESTE, só com dados simulados.

Como funciona: um chip com WhatsApp (Business) vira o "robô". A conta é conectada como APARELHO
VINCULADO (QR, igual ao WhatsApp Web) pela biblioteca `neonize`, e o robô responde às mensagens
de quem estiver na lista de autorizados — com a mesma inteligência do Telegram (`assistente.responder`).

ATENÇÃO — leia antes de usar:

* É uma conexão NÃO OFICIAL: a Meta pode limitar ou banir o número que automatiza uma conta
  comum. Por isso: chip DEDICADO ao teste, só conversa com quem se autorizou, mensagens só em
  resposta, pausa de 1 a 2,5 s antes de cada resposta, limite por pessoa, nada em massa.
* A pasta `sessao_whatsapp/` é SEGREDO (quem a tem entra na conta): fora do Git, nunca enviar.
* Só dados SIMULADOS (`data/SIMULADO.txt`), como o Telegram. Para produção, o caminho é a API
  oficial (WhatsApp Business Platform): só o transporte muda, o cérebro é o mesmo.

Este módulo separa o que se testa sem internet (`Roteador`: quem pode falar, o que responder,
como formatar) do que depende da biblioteca (`ServicoWhatsApp`, importada só ao iniciar).
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import threading
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from src import base

PASTA_SESSAO = base.RAIZ / "sessao_whatsapp"           # SEGREDO — está no .gitignore
ARQ_SESSAO = PASTA_SESSAO / "b2.db"
CONFIG = base.RAIZ / "config_whatsapp.local.json"       # fora do Git: guarda os números autorizados
PORTA_QR = 8531                                          # página local (só 127.0.0.1) com o QR

MAX_ENTRADA = 300                  # caracteres lidos de cada mensagem
MAX_SAIDA = 3_500
LIMITE_MENSAGENS = (8, 60)         # no máximo 8 mensagens por pessoa a cada 60 s
PAUSA_RESPOSTA = (1.0, 2.5)        # segundos antes de responder (como alguém digitando)
SAUDACOES = ("oi", "ola", "menu", "ajuda", "start", "comecar", "bom dia", "boa tarde", "boa noite")


# ------------------------------------------------------------------ números ---
def normalizar_numero(texto) -> str:
    """Só dígitos, com o DDI 55 quando vier sem (DDD + número = 10 ou 11 dígitos)."""
    n = re.sub(r"\D", "", str(texto))
    return "55" + n if len(n) in (10, 11) else n


def _numero_valido(n: str) -> bool:
    """Celular/fixo brasileiro com DDI: 55 + DDD + 8 ou 9 dígitos (12 ou 13 dígitos). Descarta lixo da configuração."""
    return n.startswith("55") and len(n) in (12, 13)


def variantes(numero: str) -> set[str]:
    """O WhatsApp às vezes tira (ou põe) o 9º dígito dos celulares brasileiros: aceita os dois jeitos."""
    n = normalizar_numero(numero)
    saida = {n}
    if n.startswith("55") and len(n) == 13 and n[4] == "9":
        saida.add(n[:4] + n[5:])
    if n.startswith("55") and len(n) == 12:
        saida.add(n[:4] + "9" + n[4:])
    return saida


def mascarar(numero: str) -> str:
    n = re.sub(r"\D", "", str(numero))
    return f"…{n[-4:]}" if len(n) > 4 else "…"


# ------------------------------------------------------------------- config ---
def ler_config(arquivo: Path = CONFIG, ambiente: bool = False) -> dict:
    """Os números autorizados. Num servidor (sem o arquivo local), `B2_WHATSAPP_AUTORIZADOS` ("5542..., 5542...") os
    acrescenta — só com `ambiente=True`, para `autorizar`/`remover` não gravarem no arquivo o que veio do ambiente."""
    cfg = {"autorizados": [], "nomes": {}}
    if arquivo.exists():
        try:
            cfg.update(json.loads(arquivo.read_text(encoding="utf-8")))
        except ValueError:
            pass                       # arquivo corrompido: volta ao padrão (ninguém autorizado)
    numeros = {normalizar_numero(n) for n in cfg.get("autorizados", [])}
    if ambiente:
        bruto = os.environ.get("B2_WHATSAPP_AUTORIZADOS", "").replace("\n", ",").replace(";", ",")
        numeros |= {normalizar_numero(n) for n in bruto.split(",")}
    cfg["autorizados"] = sorted(n for n in numeros if _numero_valido(n))
    return cfg


def _gravar(cfg: dict, arquivo: Path) -> None:
    tmp = arquivo.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(arquivo)


def autorizar(numero: str, nome: str = "", arquivo: Path = CONFIG) -> str:
    n = normalizar_numero(numero)
    if len(n) < 12 or len(n) > 13 or not n.startswith("55"):
        raise ValueError("Número inválido. Use DDD + número, por exemplo 42 99999-9999.")
    cfg = ler_config(arquivo)
    cfg["autorizados"] = sorted(set(cfg["autorizados"]) | {n})
    if nome:
        cfg["nomes"][n] = nome
    _gravar(cfg, arquivo)
    return n


def remover(numero: str, arquivo: Path = CONFIG) -> bool:
    n = normalizar_numero(numero)
    cfg = ler_config(arquivo)
    ficam = [a for a in cfg["autorizados"] if a not in variantes(n)]
    removeu = len(ficam) != len(cfg["autorizados"])
    cfg["autorizados"] = ficam
    cfg["nomes"] = {k: v for k, v in cfg["nomes"].items() if k in ficam}
    _gravar(cfg, arquivo)
    return removeu


# ----------------------------------------------------------------- formatar ---
def formatar(resposta) -> tuple[str, dict[str, str]]:
    """Título em negrito + corpo; as sugestões viram uma lista numerada ("responda 2").

    Botões de resposta rápida não existem nesta conexão (são só da API oficial), então o número é o botão.
    """
    corpo = f"*{resposta.titulo}*\n\n{resposta.mensagem}"
    opcoes: dict[str, str] = {}
    sugestoes = list(getattr(resposta, "sugestoes", ()))[:9]
    if sugestoes:
        linhas = []
        for i, (rotulo, comando) in enumerate(sugestoes, 1):
            opcoes[str(i)] = comando
            linhas.append(f"{i} · {rotulo}")
        corpo += "\n\n_Responda com o número:_\n" + "\n".join(linhas)
    return (corpo if len(corpo) <= MAX_SAIDA else corpo[:MAX_SAIDA - 1] + "…"), opcoes


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.casefold()) if not unicodedata.combining(c)).strip(" !.?,")


# ------------------------------------------------------------------ roteador ---
@dataclass
class Saida:
    texto: str | None           # o que enviar (None = não responder)
    motivo: str                 # "ok" ou por que ignorou: grupo, minha, vazia, nao-autorizado, limite
    numero: str = ""            # o número autorizado que falou


class Roteador:
    """Decide se responde, a quem e o quê. Sem rede, sem biblioteca: testável."""

    def __init__(self, responder: Callable[[str], object], autorizados: Callable[[], Iterable[str]],
                 relogio: Callable[[], float] = time.monotonic):
        self._responder = responder
        self._autorizados = autorizados
        self._relogio = relogio
        self._opcoes: dict[str, dict[str, str]] = {}
        self._recentes: dict[str, deque] = defaultdict(deque)
        self.desconhecidos: dict[str, int] = {}            # quem tentou falar sem estar autorizado
        self.respostas = 0

    def _autorizado(self, remetentes: Iterable[str]) -> str | None:
        lista = {v for a in self._autorizados() for v in variantes(a)}
        for r in remetentes:
            for v in variantes(r):
                if v in lista:
                    return normalizar_numero(next(a for a in self._autorizados() if v in variantes(a)))
        return None

    def _dentro_do_limite(self, numero: str) -> bool:
        agora = self._relogio()
        fila = self._recentes[numero]
        while fila and agora - fila[0] > LIMITE_MENSAGENS[1]:
            fila.popleft()
        if len(fila) >= LIMITE_MENSAGENS[0]:
            return False
        fila.append(agora)
        return True

    def tratar(self, remetentes: list[str], texto: str, grupo: bool = False, minha: bool = False) -> Saida:
        remetentes = [r for r in remetentes if r]
        if minha:
            return Saida(None, "minha")
        if grupo:
            return Saida(None, "grupo")                     # grupos ficam para depois (e com autorização própria)
        texto = (texto or "").strip()[:MAX_ENTRADA]
        if not texto:
            return Saida(None, "vazia")
        numero = self._autorizado(remetentes)
        if numero is None:
            chave = mascarar(remetentes[0]) if remetentes else "…"
            self.desconhecidos[chave] = self.desconhecidos.get(chave, 0) + 1
            return Saida(None, "nao-autorizado")            # sem resposta: o robô não se revela a estranhos
        if not self._dentro_do_limite(numero):
            return Saida(None, "limite", numero)
        comando = self._opcoes.get(numero, {}).get(texto, texto)       # "2" = a 2ª sugestão da última resposta
        if _sem_acento(texto) in SAUDACOES:
            comando = "ajuda"
        try:
            resposta = self._responder(comando)
        except ValueError as erro:
            corpo, opcoes = formatar(_Simples("🤖 B2 Gestão", str(erro)))
        except Exception:
            corpo, opcoes = formatar(_Simples("🤖 B2 Gestão", "Não consegui consultar os dados agora. Tente de novo."))
        else:
            corpo, opcoes = formatar(resposta)
        self._opcoes[numero] = opcoes
        self.respostas += 1
        return Saida(corpo, "ok", numero)


@dataclass(frozen=True)
class _Simples:
    titulo: str
    mensagem: str
    sugestoes: tuple = (("🏪 Resumo da rede", "resumo rede"), ("🚨 Alertas", "alertas"))


# ------------------------------------------------------------- o cérebro ---
def responder_padrao() -> Callable[[str], object]:
    """O `assistente.responder` com a base da demonstração — recarregada só quando os dados mudam.

    Sem streamlit de propósito: roda num processo à parte do painel.
    """
    from src import assistente, assistente_agenda, auditoria, armazenamento
    trava = threading.Lock()
    cache = {"assinatura": None, "dados": None}

    def assinatura():
        envios = armazenamento.ARQ_ENVIOS
        return (base.assinatura(), auditoria.assinatura(), envios.stat().st_mtime_ns if envios.exists() else 0)

    def responder(comando: str):
        if not (base.PASTA_DADOS / "SIMULADO.txt").exists():
            raise ValueError("Esta conexão é exclusiva da demonstração com dados simulados.")
        with trava:
            a = assinatura()
            if cache["assinatura"] != a:
                cache["dados"], cache["assinatura"] = assistente_agenda.carregar_dados(), a
            d = cache["dados"]
        return assistente.responder(comando, d["df"], d["tanques"], d["postos"], simulado=True,
                                    alertas=d["alertas"], extras=d["extras"])
    return responder


# ---------------------------------------------------------------- serviço ---
def _texto_da_mensagem(ev) -> str:
    """O texto simples de uma mensagem recebida (conversa normal ou resposta/citação)."""
    m = ev.Message
    return (m.conversation or m.extendedTextMessage.text or "").strip()


class ServicoWhatsApp:
    """Conecta a sessão, escuta e responde. Um por processo."""

    def __init__(self, roteador: Roteador, avisar: Callable[[str], None] = print,
                 arquivo_sessao: Path = ARQ_SESSAO, dormir: Callable[[float], None] = time.sleep,
                 mudo: bool = False, qr_terminal: bool = False):
        """`mudo`: fica logado e escutando, mas NÃO responde — para ter o notebook e um servidor logados ao mesmo
        tempo sem que cada mensagem receba duas respostas. `qr_terminal`: desenha o QR no terminal (pareamento por SSH)."""
        self._mudo = mudo
        self._qr_terminal = qr_terminal
        self._rot = roteador
        self._avisar = avisar
        self._arquivo = arquivo_sessao
        self._dormir = dormir
        self._cliente = None
        self._trava = threading.RLock()
        self.estado = dict(conectado=False, pareado=False, numero="", qr=b"", erro="", respostas=0)

    # ------------------------------------------------------------ tratar
    def _tratar(self, cliente, ev) -> None:
        try:
            fonte = ev.Info.MessageSource
            remetentes = [fonte.Sender.User, fonte.SenderAlt.User]
            via_lid = getattr(fonte.Sender, "Server", "") == "lid"
            if via_lid and not fonte.SenderAlt.User:
                remetentes.append(self._telefone_do_lid(cliente, fonte.Sender))
            saida = self._rot.tratar(remetentes, _texto_da_mensagem(ev), grupo=fonte.IsGroup, minha=fonte.IsFromMe)
        except Exception as erro:
            self._avisar(f"[whatsapp] mensagem ignorada ({type(erro).__name__})")
            return
        if saida.motivo == "nao-autorizado":
            visto = [mascarar(r) for r in remetentes if r]
            forma = "o WhatsApp entregou um ID interno (LID) e não achei o telefone" if via_lid and len(visto) < 2 else "telefone"
            self._avisar(f"[whatsapp] mensagem de número NÃO autorizado ({' / '.join(visto) or '…'}; {forma}): ignorada. "
                         "Para liberar: python whatsapp_assistente.py --autorizar NUMERO")
            return
        if saida.texto is None:
            if saida.motivo == "limite":
                self._avisar(f"[whatsapp] limite de mensagens por minuto ({mascarar(saida.numero)}): ignorada")
            return
        if self._mudo:
            self._avisar(f"[whatsapp] (mudo) vi a mensagem de {mascarar(saida.numero)} e NÃO respondi: outro aparelho responde")
            return
        try:
            self._digitando(cliente, fonte.Chat)
            self._dormir(random.uniform(*PAUSA_RESPOSTA))
            cliente.send_message(fonte.Chat, saida.texto)
            with self._trava:
                self.estado["respostas"] = self._rot.respostas
                self.estado["erro"] = ""
            self._avisar(f"[whatsapp] respondi a {mascarar(saida.numero)}")
        except Exception as erro:
            with self._trava:
                self.estado["erro"] = f"Falha ao responder ({type(erro).__name__})."
            self._avisar(f"[whatsapp] falha ao responder: {type(erro).__name__}")

    @staticmethod
    def _telefone_do_lid(cliente, jid) -> str:
        """O WhatsApp às vezes entrega o remetente como ID interno (LID), sem o telefone: pergunta à sessão qual é."""
        try:
            return cliente.get_pn_from_lid(jid).User or ""
        except Exception:
            return ""

    def _digitando(self, cliente, chat) -> None:
        """"digitando…" antes da resposta. Enfeite: se falhar, segue."""
        try:
            from neonize.utils.enum import ChatPresence, ChatPresenceMedia
            cliente.send_chat_presence(chat, ChatPresence.CHAT_PRESENCE_COMPOSING,
                                       ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
        except Exception:
            pass

    # ------------------------------------------------------------ rodar
    def rodar(self) -> None:
        """Conecta e BLOQUEIA até Ctrl+C. O 1º uso mostra o QR (na página local e no terminal)."""
        from neonize.client import NewClient
        from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv, MessageEv, PairStatusEv

        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        cliente = NewClient(str(self._arquivo))
        self._cliente = cliente

        @cliente.event.qr
        def _qr(_c, dados: bytes):
            with self._trava:
                self.estado["qr"] = bytes(dados)
            if self._qr_terminal:
                import segno
                segno.make(bytes(dados)).terminal(compact=True)
            self._avisar("[whatsapp] QR novo: escaneie na página local (veja o endereço acima) ou no terminal.")

        @cliente.event(PairStatusEv)
        def _pareou(_c, ev):
            with self._trava:
                self.estado.update(pareado=True, qr=b"", numero=getattr(ev.ID, "User", ""))
            self._avisar("[whatsapp] Pareado! A conta agora é um aparelho vinculado.")

        @cliente.event(ConnectedEv)
        def _conectou(_c, _ev):
            with self._trava:
                self.estado.update(conectado=True, pareado=True, qr=b"", erro="")
            self._avisar("[whatsapp] Conectado. Mande uma mensagem de um número autorizado.")

        @cliente.event(DisconnectedEv)
        def _caiu(_c, _ev):
            with self._trava:
                self.estado["conectado"] = False
            self._avisar("[whatsapp] Conexão caiu; a biblioteca tenta voltar sozinha.")

        @cliente.event(LoggedOutEv)
        def _saiu(_c, _ev):
            with self._trava:
                self.estado.update(conectado=False, pareado=False,
                                   erro="O celular desconectou este aparelho. Apague sessao_whatsapp/ e pareie de novo.")
            self._avisar("[whatsapp] DESCONECTADO pelo celular. Apague a pasta sessao_whatsapp e pareie de novo.")

        @cliente.event(MessageEv)
        def _mensagem(c, ev):
            self._tratar(c, ev)

        cliente.connect()

    def parar(self) -> None:
        try:
            if self._cliente is not None:
                self._cliente.stop()
        except Exception:
            pass


# ------------------------------------------------------- página local do QR ---
def pagina_qr(estado: dict, autorizados: list[str]) -> str:
    """HTML (atualiza sozinho) com o QR atual e a situação. Só é servida em 127.0.0.1."""
    if estado.get("conectado"):
        corpo = ('<p class="ok">✅ <b>Conectado.</b> Mande uma mensagem do seu WhatsApp pessoal para o número do robô '
                 f'(autorizados: {len(autorizados)}).</p>')
    elif estado.get("qr"):
        import segno                                            # vem com o neonize; só o QR precisa dele
        svg = segno.make(estado["qr"]).svg_inline(scale=7, border=2)
        corpo = ("<p><b>Escaneie com o WhatsApp do chip do robô:</b><br>WhatsApp Business → ⋮ → <b>Aparelhos conectados</b> → "
                 f"<b>Conectar um aparelho</b>. O QR troca a cada ~20 s.</p><div class='qr'>{svg}</div>")
    else:
        corpo = "<p>Conectando ao WhatsApp… aguarde alguns segundos.</p>"
    erro = f'<p class="er">{html.escape(estado["erro"])}</p>' if estado.get("erro") else ""
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='refresh' content='3'><title>B2 Assistente — WhatsApp</title><style>"
            "body{font:16px/1.5 system-ui,sans-serif;max-width:520px;margin:24px auto;padding:0 16px;color:#14213d}"
            ".qr{background:#fff;padding:12px;display:inline-block;border:1px solid #dfe3ee;border-radius:12px}"
            ".ok{background:#e8f7ef;padding:12px;border-radius:10px}.er{background:#fdecec;padding:10px;border-radius:8px}"
            "@media(prefers-color-scheme:dark){body{background:#0d1226;color:#e8ebf5}}</style></head><body>"
            f"<h2>B2 Assistente · WhatsApp (teste)</h2>{corpo}{erro}</body></html>")


def servir_pagina_qr(servico: ServicoWhatsApp, porta: int = PORTA_QR):
    """Sobe a página do QR numa thread (127.0.0.1 apenas). Devolve o servidor (para .shutdown())."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Pagina(BaseHTTPRequestHandler):
        def do_GET(self):                                       # noqa: N802
            with servico._trava:
                estado = dict(servico.estado)
            corpo = pagina_qr(estado, ler_config(ambiente=True)["autorizados"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):                              # silêncio
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Pagina)
    threading.Thread(target=servidor.serve_forever, name="b2-whatsapp-qr", daemon=True).start()
    return servidor
