"""Controle de fraudes, placar da reunião e disparos automáticos.

    python -m pytest tests/test_controle.py
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src import alertas as al
from src import analytics as an
from src import antifraude, assistente, auditoria, base, reuniao
from src import assistente_agenda as agenda
from src import assistente_telegram as tg
from src.assistente import Resposta

RAIZ = Path(__file__).resolve().parent.parent
SIMULADO = pytest.mark.skipif(not (RAIZ / "data" / "SIMULADO.txt").exists(),
                              reason="só com os dados simulados da demonstração")


def mov(linhas):
    """Movimento mínimo: (posto, data, produto, vendas, estoque final)."""
    return pd.DataFrame([{"posto": p, "data": pd.Timestamp(d), "produto": pr, "vendas_l": v, "estoque_final": e,
                          "compras_l": 0.0, "estoque_inicial": e + 1000, "preco_medio": 6.0, "custo_medio": 5.4}
                         for p, d, pr, v, e in linhas])


# ------------------------------------------------------------ auditoria -----
def test_dia_novo_nao_e_alteracao():
    antiga = mov([("B2 Centro", "2026-09-20", "Etanol", 1000, 9000)])
    nova = mov([("B2 Centro", "2026-09-20", "Etanol", 1000, 9000),
                ("B2 Centro", "2026-09-21", "Etanol", 1100, 7900)])
    assert auditoria.comparar(antiga, nova).empty


def test_gravidade_cresce_com_a_idade_do_dia_alterado():
    dias = ["2026-09-01", "2026-09-12", "2026-09-17", "2026-09-19"]
    antiga = mov([("B2 Centro", d, "Etanol", 1000, 9000) for d in dias])
    nova = mov([("B2 Centro", d, "Etanol", 900, 9000) for d in dias[:3]] +
               [("B2 Centro", dias[3], "Etanol", 1000, 9000)])
    m = auditoria.comparar(antiga, nova).set_index("data")["gravidade"]
    assert m[pd.Timestamp("2026-09-17")] == "atencao"          # 2 dias antes do último
    assert m[pd.Timestamp("2026-09-12")] == "critico"          # 7 dias
    assert m[pd.Timestamp("2026-09-01")] == "critico"


def test_mes_fechado_e_critico_mesmo_recente():
    antiga = mov([("B2 Centro", "2026-08-31", "Etanol", 1000, 9000),
                  ("B2 Centro", "2026-09-01", "Etanol", 1000, 9000)])
    nova = mov([("B2 Centro", "2026-08-31", "Etanol", 800, 9000),
                ("B2 Centro", "2026-09-01", "Etanol", 1000, 9000)])
    m = auditoria.comparar(antiga, nova)
    assert list(m["gravidade"]) == ["critico"]
    assert m.iloc[0]["impacto_rs"] == pytest.approx(-1200.0)       # −200 L × R$ 6,00


def test_linha_apagada_vai_para_a_trilha():
    antiga = mov([("B2 Centro", "2026-09-10", "Etanol", 1000, 9000),
                  ("B2 Centro", "2026-09-20", "Etanol", 1000, 9000)])
    nova = mov([("B2 Centro", "2026-09-20", "Etanol", 1000, 9000)])
    m = auditoria.comparar(antiga, nova)
    assert list(m["campo"]) == ["Linha inteira"]
    assert "APAGADA" in auditoria.descrever(m.iloc[0])


def test_registrar_e_ler_ida_e_volta(tmp_path, monkeypatch):
    monkeypatch.setattr(auditoria, "ARQ_AUDITORIA", tmp_path / "auditoria.csv")
    antiga = mov([("B2 Índio", "2026-09-01", "Diesel S10", 2000, 9000),
                  ("B2 Índio", "2026-09-20", "Diesel S10", 2000, 9000)])
    nova = mov([("B2 Índio", "2026-09-01", "Diesel S10", 1500, 9000),
                ("B2 Índio", "2026-09-20", "Diesel S10", 2000, 9000)])
    n = auditoria.registrar(auditoria.comparar(antiga, nova), "Envio pelo painel", "paulo.indio",
                            quando=datetime(2026, 9, 21, 8, 30))
    aud = auditoria.ler()
    assert n == 1 and aud.iloc[0]["usuario"] == "paulo.indio"
    alerta = al.regra_auditoria(aud, ["B2 Índio"])[0]
    assert alerta.nivel == "critico" and alerta.aba == "Auditoria"
    assert "paulo.indio" in alerta.detalhes[-1]


# ------------------------------------------------------- sinais (demo) -----
@pytest.fixture(scope="module")
def demo():
    b = base.carregar()
    df = an.preparar(b.movimento)
    return b, df, b.postos["posto"].tolist(), auditoria.ler()


@SIMULADO
def test_auditoria_acha_as_fraudes_plantadas(demo):
    b, df, postos, aud = demo
    achados = {(s.tipo, s.posto, s.nivel) for s in antifraude.sinais(df, b.compras, aud, postos)}
    assert ("alteracao", "B2 Primavera", "critico") in achados
    assert ("sem_nota", "B2 Bonsucesso", "critico") in achados
    assert ("nf_repetida", "B2 Índio", "atencao") in achados
    # A 2ª via da nota repetida não vira também "nota sem entrada".
    assert ("nota_sem_entrada", "B2 Índio", "atencao") not in achados
    # O posto em ordem continua limpo.
    assert not [s for s in antifraude.sinais(df, b.compras, aud, postos) if s.posto == "B2 Centro"]


@SIMULADO
def test_central_recebe_um_alerta_so_por_posto_alterado(demo):
    b, df, postos, aud = demo
    alertas = [a for a in al.gerar(df, b.tanques, postos, auditoria=aud) if a.tipo == "auditoria"]
    assert [(a.posto, a.nivel) for a in alertas] == [("B2 Primavera", "critico")]
    # A correção normal do Bonsucesso fica só na trilha.


@SIMULADO
def test_planilha_alterada_e_avisada_na_conferencia(demo):
    from src import validacao
    b, df, postos, _ = demo
    arq = next((RAIZ / "exemplos_para_envio").glob("ALTERADA*.xlsx"))
    rel = validacao.validar(arq.read_bytes(), arq.name, "B2 Primavera", postos, b.tanques, df)
    assert rel.aprovado, rel.erros
    assert len(rel.alteracoes) == 2
    assert any("de 08/09" in a for a in rel.alteracoes) and any("de 09/09" in a for a in rel.alteracoes)
    assert any("ALTERA 2 dia(s)" in a for a in rel.avisos)


@SIMULADO
def test_placar_e_pauta_da_reuniao(demo):
    b, df, postos, aud = demo
    from src import armazenamento
    fim = df["data"].max()
    per = an.periodo(df, fim.year, fim.month)
    p = reuniao.placar(df, b.despesas, armazenamento.ler_envios(), aud, per, postos)
    assert list(p["posto"]) == postos
    linha = p.set_index("posto").loc["B2 Primavera"]
    assert linha["alteracoes"] == 2 and linha["pontualidade"] < reuniao.META_PONTUALIDADE
    rede = reuniao.medias_rede(p)
    pauta = reuniao.pauta(p[p["posto"] == "B2 Primavera"].iloc[0], rede, p)
    assert pauta[0].startswith("🔴") and "alterados" in pauta[0]
    html = reuniao.ficha_html(p.iloc[0], rede, p, per, simulado=True)
    assert "Combinados" in html and "nan" not in html.lower()


# -------------------------------------------------------------- agenda -----
ITENS = [
    {"id": "bom-dia", "nome": "Bom dia", "conteudo": "resumo rede", "quando": "horario", "hora": "07:30",
     "dias": agenda.DIAS, "ativo": True},
    {"id": "chegada", "nome": "Chegada", "conteudo": "alertas", "quando": "chegada", "hora": "",
     "dias": agenda.DIAS, "ativo": True},
    {"id": "cobranca", "nome": "Cobrança", "conteudo": "pendencias", "quando": "limite", "hora": "10:00",
     "dias": agenda.DIAS[:5], "ativo": True},
]


def ids(lista):
    return [i["id"] for i in lista]


def test_disparo_sai_na_hora_e_uma_vez_por_dia():
    seg = datetime(2026, 9, 28, 7, 31)                         # segunda-feira
    assert ids(agenda.devidos(ITENS, seg, {}, chegou=False)) == ["bom-dia"]
    assert agenda.devidos(ITENS, seg, {"bom-dia": "2026-09-28"}, chegou=False) == []
    # Painel ligado às 14h não manda o bom-dia atrasado.
    assert agenda.devidos(ITENS, datetime(2026, 9, 28, 14, 0), {}, chegou=False) == []


def test_chegada_dispara_quando_os_dados_entram():
    momento = datetime(2026, 9, 28, 15, 0)
    assert ids(agenda.devidos(ITENS, momento, {}, chegou=True)) == ["chegada"]
    assert agenda.devidos(ITENS, momento, {}, chegou=False) == []


def test_cobranca_respeita_os_dias_e_o_desligado():
    sabado = datetime(2026, 9, 26, 10, 5)
    assert "cobranca" not in ids(agenda.devidos(ITENS, sabado, {}, chegou=False))
    desligado = [dict(i, ativo=False) for i in ITENS]
    assert agenda.devidos(desligado, datetime(2026, 9, 28, 10, 5), {}, chegou=True) == []


@SIMULADO
def test_cobranca_avisa_quem_esta_pendente_e_cala_se_todos_em_dia():
    d = agenda.carregar_dados()
    r = agenda.gerar_conteudo(ITENS[2], d)
    assert r is not None and "Primavera" in r.mensagem
    em_dia = dict(d, df=d["df"][d["df"]["posto"] != "B2 Primavera"], postos=[p for p in d["postos"]
                                                                            if p != "B2 Primavera"])
    assert agenda.gerar_conteudo(ITENS[2], em_dia) is None


def test_agendador_dispara_na_hora_e_na_chegada(monkeypatch):
    monkeypatch.setattr(agenda, "agora", lambda: datetime(2026, 9, 28, 7, 35))
    monkeypatch.setattr(agenda, "carregar", lambda: ITENS[:2])
    monkeypatch.setattr(agenda, "gerar_conteudo",
                        lambda item, d, chegaram=None: Resposta(item["nome"], ", ".join(chegaram or [])))
    dados = {"df": pd.DataFrame({"posto": ["B2 Centro"], "data": [pd.Timestamp("2026-09-26")]}),
             "postos": ["B2 Centro"]}
    assinatura, enviados, estado = [(1,)], [], {}
    ag = agenda.Agendador(lambda: dados, lambda r: (enviados.append((r.titulo, r.mensagem)), (1, ""))[1],
                          lambda: assinatura[0], lambda: dict(estado), estado.update)
    ag._tique()              # 1º giro: só o bom-dia (sem base anterior, não há "chegada")
    assert enviados == [("Bom dia", "")] and estado == {"bom-dia": "2026-09-28"}
    ag._tique()              # nada mudou e o bom-dia já foi
    assert len(enviados) == 1
    dados["df"] = pd.DataFrame({"posto": ["B2 Centro"], "data": [pd.Timestamp("2026-09-27")]})
    assinatura[0] = (2,)
    ag._tique()              # planilha nova do Centro
    assert enviados[-1] == ("Chegada", "B2 Centro")
    assert ag.historico[0][1] == "Chegada" and "1 conversa" in ag.historico[0][2]


# ------------------------------------------------------ Telegram em grupo ---
TOKEN = "123456789:" + "A" * 35


@pytest.fixture
def api(monkeypatch):
    import io
    import json

    chamadas = []

    class Retorno(io.BytesIO):
        status = 200

    def abrir(req, timeout):
        chamadas.append((req.full_url.rsplit("/", 1)[-1], json.loads(req.data)))
        return Retorno(json.dumps({"ok": True, "result": True}).encode())

    monkeypatch.setattr(tg.urllib.request, "urlopen", abrir)
    return chamadas


def test_robo_adicionado_ao_grupo_registra_e_se_apresenta(api):
    registrados, removidos = [], []
    s = tg.ServicoTelegram(TOKEN, lambda t: Resposta("ok", "ok"),
                           ao_registrar=lambda c, n: registrados.append((c, n)), ao_remover=removidos.append)
    entrou = {"update_id": 1, "my_chat_member": {"chat": {"id": -100123, "title": "Diretoria B2"},
                                                  "new_chat_member": {"status": "member"}}}
    s._tratar(entrou, tg._Sessao(threading.Event()))
    assert registrados == [(-100123, "Diretoria B2")]
    assert s.conversas() == [(-100123, "Diretoria B2", "grupo")]
    assert any(c[0] == "sendMessage" and c[1]["chat_id"] == -100123 for c in api)
    saiu = {"update_id": 2, "my_chat_member": {"chat": {"id": -100123, "title": "Diretoria B2"},
                                                "new_chat_member": {"status": "kicked"}}}
    s._tratar(saiu, tg._Sessao(threading.Event()))
    assert s.chats() == [] and removidos == [-100123]


def test_no_grupo_nao_vai_teclado_fixo(api):
    s = tg.ServicoTelegram(TOKEN, lambda t: Resposta("📊", "ok", (("📦 Estoque", "estoque"),)))
    msg = {"update_id": 3, "message": {"chat": {"id": -100555, "title": "Gerentes"},
                                       "from": {"first_name": "Ana"}, "text": "/resumo centro"}}
    s._tratar(msg, tg._Sessao(threading.Event()))
    envios = [c[1] for c in api if c[0] == "sendMessage"]
    assert envios and all("keyboard" not in (e.get("reply_markup") or {}) for e in envios)
    assert s.conversas()[0][1] == "Gerentes"


@pytest.mark.parametrize("texto,esperado", [
    ("/reuniao", ("reuniao", None)),
    ("/auditoria primavera", ("auditoria", "B2 Primavera")),
    ("pendências", ("pendencias", None)),
    ("/estoque@B2GestaoDemoBot candoi", ("estoque", "B2 Candói")),
])
def test_comandos_novos_do_assistente(texto, esperado):
    postos = ["B2 Centro", "B2 Bonsucesso", "B2 Primavera", "B2 Índio", "B2 Candói"]
    assert assistente.entender(texto, postos) == esperado
