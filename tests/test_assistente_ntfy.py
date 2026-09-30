"""Transporte ntfy inteiramente em memória: nenhum teste publica na internet."""
import io
import json
import threading
import urllib.error
from dataclasses import dataclass

import pytest

from src import assistente_ntfy as ntfy


@dataclass
class Resposta:
    titulo: str = "🤖 B2 Gestão — resumo"
    mensagem: str = "Rede com 5 postos."


class Retorno(io.BytesIO):
    status = 200


@pytest.fixture(autouse=True)
def nenhuma_rede(monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("Teste tentou usar rede real.")
    monkeypatch.setattr(ntfy.urllib.request, "urlopen", proibido)


def servico(responder=lambda texto: Resposta(), **kwargs):
    return ntfy.ServicoNtfy("https://ntfy.exemplo", "b2-demo", responder, **kwargs)


def sessao(s):
    atual = ntfy._Sessao(threading.Event(), 100)
    s._sessao = atual
    return atual


def evento(identificador="comando1", **kwargs):
    return {"event": "message", "topic": "b2-demo", "id": identificador,
            "time": 101, "message": "resumo", **kwargs}


@pytest.mark.parametrize("servidor,topico", [
    ("ftp://ntfy.exemplo", "demo"), ("https://", "demo"),
    ("https://nome:senha@ntfy.exemplo", "demo"),
    ("https://ntfy.exemplo?token=segredo", "demo"),
    ("https://ntfy.exemplo", "../privado"), ("https://ntfy.exemplo", "demo/outro"),
    ("https://ntfy.exemplo", "demo?since=all"), ("https://ntfy.exemplo", ""),
])
def test_rejeita_enderecos_e_topicos_invalidos(servidor, topico):
    with pytest.raises(ValueError):
        ntfy.ServicoNtfy(servidor, topico, lambda texto: Resposta())


def test_publica_json_com_marca_contra_loop_e_autenticacao(monkeypatch):
    requisicoes = []
    def abrir(req, timeout):
        requisicoes.append((req, timeout))
        return Retorno(b'{"id":"resposta1","event":"message"}')
    monkeypatch.setattr(ntfy.urllib.request, "urlopen", abrir)
    s = servico(token="token-do-teste")
    assert s.enviar(Resposta())[0]
    req, timeout = requisicoes[0]
    assert req.full_url == "https://ntfy.exemplo/"
    assert req.method == "POST" and timeout == 20
    assert req.get_header("Authorization") == "Bearer token-do-teste"
    assert json.loads(req.data) == {"topic": "b2-demo", "title": Resposta.titulo,
                                   "message": Resposta.mensagem,
                                   "tags": ["robot", "b2-resposta"], "priority": 3}
    assert s.status()["ultima_resposta"] == Resposta.mensagem


def test_nao_registra_sucesso_sem_confirmacao(monkeypatch):
    monkeypatch.setattr(ntfy.urllib.request, "urlopen", lambda *a, **k: Retorno(b'{}'))
    s = servico()
    assert not s.enviar(Resposta())[0]
    assert s.status()["ultima_resposta"] == ""
    assert s.status()["erro"]


def test_falha_nao_expoe_url_ou_credenciais(monkeypatch):
    def falhar(*args, **kwargs):
        raise urllib.error.URLError("https://secreto:token@privado.exemplo")
    monkeypatch.setattr(ntfy.urllib.request, "urlopen", falhar)
    s = servico()
    ok, motivo = s.enviar(Resposta())
    assert not ok and "secreto" not in motivo and "token@" not in motivo
    assert s.status()["ultima_resposta"] == ""


def test_dedup_e_respostas_nao_viram_comandos(monkeypatch):
    comandos, publicados = [], []
    s = servico(lambda texto: comandos.append(texto) or Resposta())
    atual = sessao(s)
    monkeypatch.setattr(s, "_publicar", lambda r: publicados.append(r) or (True, "ok"))
    assert s._processar(evento(), atual)
    assert s._processar(evento(), atual)
    assert s._processar(evento("resposta1", tags=["b2-resposta"]), atual)
    assert s._processar(evento("resposta2", title="🤖 B2 Gestão — resposta"), atual)
    assert comandos == ["resumo"] and len(publicados) == 1


@pytest.mark.parametrize("dado", [
    [], None, {"event": "open"}, evento(time=99), evento(time="101"),
    evento(topic="outro"), evento(attachment={"url": "https://exemplo/arquivo"}),
    evento(message="x" * 601), evento(message=None), evento(message=" "),
    evento(tags="b2-resposta"), evento(event="keepalive"), evento(id=""),
])
def test_ignora_historico_anexos_e_eventos_estranhos(dado):
    comandos = []
    s = servico(lambda texto: comandos.append(texto) or Resposta())
    assert s._processar(dado, sessao(s))
    assert comandos == []


def test_comando_invalido_recebe_motivo_sem_contornar_bloqueio(monkeypatch):
    comandos, respostas = [], []
    def responder(texto):
        comandos.append(texto)
        raise ValueError("Este assistente só pode consultar os dados da demonstração.")
    s = servico(responder)
    monkeypatch.setattr(s, "_publicar", lambda r: respostas.append(r) or (True, "ok"))
    assert s._processar(evento(message="qualquer coisa"), sessao(s))
    assert comandos == ["qualquer coisa"]
    assert respostas[0].mensagem == "Este assistente só pode consultar os dados da demonstração."


def test_preserva_pendente_e_cursor_ate_entrega_confirmada(monkeypatch):
    comandos, tentativas = [], []
    s = servico(lambda texto: comandos.append(texto) or Resposta())
    atual = sessao(s)
    atual.ultimo_id = "anterior"
    def publicar(resposta):
        tentativas.append(resposta)
        return (len(tentativas) > 1, "rede indisponível")
    monkeypatch.setattr(s, "_publicar", publicar)
    assert not s._processar(evento(), atual)
    assert atual.ultimo_id == "anterior" and atual.pendente is not None
    assert s.status()["ultima_resposta"] == ""
    assert s._enviar_pendente(atual)
    assert atual.ultimo_id == "comando1" and atual.pendente is None
    assert s._processar(evento(), atual)
    assert comandos == ["resumo"] and len(tentativas) == 2
    assert s.status()["ultima_resposta"] == Resposta.mensagem


def test_stream_usa_timestamp_no_inicio_e_id_ao_reconectar(monkeypatch):
    urls, comandos = [], []
    s = servico(lambda texto: comandos.append(texto) or Resposta())
    atual = sessao(s)
    conteudo = b'linha invalida\n' + json.dumps(evento()).encode() + b'\n'
    def abrir(req, timeout):
        urls.append(req.full_url)
        return Retorno(conteudo)
    monkeypatch.setattr(ntfy.urllib.request, "urlopen", abrir)
    monkeypatch.setattr(s, "_publicar", lambda r: (True, "ok"))
    s._consumir(atual)
    s._consumir(atual)
    assert urls == ["https://ntfy.exemplo/b2-demo/json?since=100",
                    "https://ntfy.exemplo/b2-demo/json?since=comando1"]
    assert comandos == ["resumo"]


def test_iniciar_idempotente_e_parar_interrompe_comandos(monkeypatch):
    threads, comandos = [], []
    class ThreadFake:
        def __init__(self, **kwargs):
            threads.append(kwargs)
        def start(self):
            pass
    monkeypatch.setattr(ntfy.threading, "Thread", ThreadFake)
    s = servico(lambda texto: comandos.append(texto) or Resposta())
    s.iniciar()
    s.iniciar()
    assert len(threads) == 1 and threads[0]["daemon"]
    anterior = s._sessao
    s.parar()
    assert not s.status()["ativo"] and not s.status()["conectado"]
    s._processar(evento(time=anterior.inicio), anterior)
    assert comandos == []
    s.iniciar()
    assert len(threads) == 2 and s.status()["ativo"]
    s._estado_da_sessao(anterior, erro="erro da conexão encerrada")
    assert s.status()["erro"] == ""


def test_status_e_copia_independente():
    s = servico()
    estado = s.status()
    estado["ativo"] = True
    assert not s.status()["ativo"]


def test_timeout_ocioso_reconecta_sem_alarme(monkeypatch):
    s = servico()
    atual = sessao(s)
    def consumir(_sessao):
        raise TimeoutError("nenhum evento novo")
    monkeypatch.setattr(s, "_consumir", consumir)
    monkeypatch.setattr(atual.parada, "wait", lambda _segundos: True)
    s._executar(atual)
    assert s.status()["erro"] == ""
