"""Transporte do Telegram inteiramente em memória: nenhum teste usa a internet."""
import io
import json
import threading
import urllib.error

import pytest

from src import assistente_telegram as tg
from src.assistente import Resposta

TOKEN = "123456789:" + "A" * 35


class Retorno(io.BytesIO):
    status = 200


@pytest.fixture
def api(monkeypatch):
    """Telegram falso: guarda cada chamada e responde ok."""
    chamadas = []

    def abrir(req, timeout):
        metodo = req.full_url.rsplit("/", 1)[-1]
        chamadas.append((metodo, json.loads(req.data), req.full_url))
        resultado = {"getMe": {"username": "B2GestaoDemoBot", "first_name": "B2 Gestão"}}.get(metodo, True)
        return Retorno(json.dumps({"ok": True, "result": resultado}).encode())

    monkeypatch.setattr(tg.urllib.request, "urlopen", abrir)
    return chamadas


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("Teste tentou usar a internet.")
    monkeypatch.setattr(tg.urllib.request, "urlopen", proibido)


def servico(responder=lambda t: Resposta("📊 Resumo — B2 Centro", "💰 R$ 2,5 mi & <ok>",
                                         (("📦 Estoque", "estoque B2 Centro"),)), **kw):
    return tg.ServicoTelegram(TOKEN, responder, **kw)


def mensagem(texto, chat=42, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "from": {"first_name": "Gustavo"},
                                                "text": texto}}


@pytest.mark.parametrize("token", ["", "abc", "123:curto", "123456789 " + "A" * 35, "x" * 50])
def test_rejeita_token_invalido(token):
    with pytest.raises(ValueError):
        tg.ServicoTelegram(token, lambda t: None)


def test_resposta_vai_em_html_seguro_com_botoes(api):
    s = servico()
    s._tratar(mensagem("resumo centro"), tg._Sessao(threading.Event()))
    envio = [c for c in api if c[0] == "sendMessage"][0][1]
    assert envio["chat_id"] == 42 and envio["parse_mode"] == "HTML"
    assert envio["text"].startswith("<b>📊 Resumo — B2 Centro</b>")
    assert "&amp; &lt;ok&gt;" in envio["text"]                    # nada de HTML injetado
    # Primeira conversa: vem o teclado fixo com os postos.
    assert envio["reply_markup"]["keyboard"][1][0]["text"] == "⛽ Centro"


def test_start_mostra_menu_e_registra_conversa(api):
    registrados = []
    comandos = []
    s = servico(lambda t: comandos.append(t) or Resposta("🤖", "menu", (("🚨 Alertas", "alertas"),)),
                ao_registrar=lambda chat, nome: registrados.append((chat, nome)))
    s._tratar(mensagem("/start"), tg._Sessao(threading.Event()))
    assert comandos == ["ajuda"]
    assert registrados == [(42, "Gustavo")] and s.chats() == [42]


def test_clique_no_botao_vira_comando(api):
    comandos = []
    s = servico(lambda t: comandos.append(t) or Resposta("📦", "ok"), chats=[42])
    clique = {"update_id": 2, "callback_query": {"id": "cb1", "data": "estoque B2 Candói",
                                                 "from": {"first_name": "G"},
                                                 "message": {"chat": {"id": 42}}}}
    s._tratar(clique, tg._Sessao(threading.Event()))
    assert comandos == ["estoque B2 Candói"]
    assert "answerCallbackQuery" in [c[0] for c in api]


def test_texto_nao_entendido_responde_com_a_ajuda(api):
    def responder(texto):
        raise ValueError("Não entendi. Tente: estoque candói")
    s = servico(responder, chats=[42])
    s._tratar(mensagem("blabla"), tg._Sessao(threading.Event()))
    envio = [c for c in api if c[0] == "sendMessage"][0][1]
    assert "Tente: estoque candói" in envio["text"]


def test_alerta_vai_para_todas_as_conversas(api):
    s = servico(chats=[1, 2, 3])
    enviados, erro = s.enviar_para_todos(Resposta("🔴 ESTOQUE CRÍTICO — B2 Candói", "Diesel S10: 0,9 dia"))
    assert enviados == 3 and erro == ""
    assert sorted(c[1]["chat_id"] for c in api if c[0] == "sendMessage") == [1, 2, 3]


def test_erro_nao_mostra_o_token(monkeypatch):
    def falhar(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(tg.urllib.request, "urlopen", falhar)
    with pytest.raises(tg.ErroTelegram) as erro:
        tg._chamar(TOKEN, "getMe")
    assert TOKEN not in str(erro.value) and "@BotFather" in str(erro.value)


def test_conflito_de_duas_janelas_tem_mensagem_clara(monkeypatch):
    def falhar(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, None)
    monkeypatch.setattr(tg.urllib.request, "urlopen", falhar)
    with pytest.raises(tg.ErroTelegram, match="outra janela"):
        tg._chamar(TOKEN, "getUpdates")


def test_ignora_o_que_nao_e_texto(api):
    comandos = []
    s = servico(lambda t: comandos.append(t) or Resposta("x", "y"))
    sessao = tg._Sessao(threading.Event())
    for evento in [{}, None, {"message": {"chat": {"id": 1}}}, {"message": {"chat": {"id": 1}, "text": "  "}},
                   {"message": {"chat": {"id": "1"}, "text": "oi"}}]:
        s._tratar(evento, sessao)
    assert comandos == []


def test_parado_nao_responde(api):
    comandos = []
    s = servico(lambda t: comandos.append(t) or Resposta("x", "y"))
    sessao = tg._Sessao(threading.Event())
    sessao.parada.set()
    s._tratar(mensagem("resumo"), sessao)
    assert comandos == []


def test_ciclo_completo_ignora_fila_antiga_e_responde_a_nova(monkeypatch):
    """Liga, pula o que estava parado na fila, responde a pergunta nova e para."""
    sessao = tg._Sessao(threading.Event())
    enviados, respostas = [], []

    def chamar(token, metodo, dados=None, timeout=20):
        if metodo == "getMe":
            return {"username": "B2GestaoDemoBot", "first_name": "B2 Gestão"}
        if metodo == "getUpdates" and dados.get("offset") == -1:
            return [{"update_id": 10, "message": {"chat": {"id": 7}, "text": "pergunta de ontem"}}]
        if metodo == "getUpdates":
            if dados["offset"] == 11:
                return [mensagem("estoque candói", chat=7, update_id=11)]
            sessao.parada.set()          # segunda volta: encerra o teste
            return []
        if metodo == "sendMessage":
            enviados.append(dados)
        return True

    monkeypatch.setattr(tg, "_chamar", chamar)
    s = servico(lambda t: respostas.append(t) or Resposta("📦 Estoque — B2 Candói", "Diesel S10: 0,9 dia"),
                chats=[7])
    s._sessao = sessao
    s._executar(sessao)
    assert respostas == ["estoque candói"]            # a de ontem foi ignorada
    assert enviados and "Diesel S10" in enviados[0]["text"]
    assert s.status()["bot_usuario"] == "B2GestaoDemoBot"
