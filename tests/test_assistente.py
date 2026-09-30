"""As respostas do B2 Assistente: entende o jeito de digitar no celular,
responde com a data do dado, não inventa número e cabe na tela.
"""
from pathlib import Path

import pandas as pd
import pytest

from src import alertas as al
from src import analytics as an, base
from src.assistente import entender, responder

POSTOS = ["B2 Centro", "B2 Bonsucesso", "B2 Primavera", "B2 Índio", "B2 Candói"]
SIMULADO = pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "data" / "SIMULADO.txt").exists(),
                              reason="só com os dados simulados da demonstração")


def _linha(data, posto="B2 Centro", produto="Gasolina Comum", vendas=100, preco=6, custo=5, estoque=1000):
    return {"data": data, "posto": posto, "produto": produto, "vendas_l": vendas,
            "preco_medio": preco, "custo_medio": custo, "estoque_inicial": estoque + vendas,
            "compras_l": 0, "estoque_final": estoque}


def _df(*linhas):
    return an.preparar(pd.DataFrame(linhas))


def _tanques(*postos):
    return pd.DataFrame([{"posto": p, "produto": produto, "capacidade": 10000}
                         for p in postos for produto in an.COMBUSTIVEIS])


@pytest.mark.parametrize("texto,esperado", [
    ("resumo b2 centro", ("resumo", "B2 Centro")),
    ("  RESUMO   CENTRO ", ("resumo", "B2 Centro")),
    ("estoque candói", ("estoque", "B2 Candói")),
    ("ESTOQUE B2 CANDOI", ("estoque", "B2 Candói")),
    ("⛽ Índio", ("resumo", "B2 Índio")),
    ("como está o estoque do candoi?", ("estoque", "B2 Candói")),
    ("quanto vendeu o bonsucesso", ("vendas", "B2 Bonsucesso")),
    ("margem primavera", ("margem", "B2 Primavera")),
    ("🏪 Resumo da rede", ("resumo", None)),
    ("📦 Estoque da rede", ("estoque", None)),
    ("🚨 Alertas", ("alertas", None)),
    ("oi", ("ajuda", None)),
])
def test_entende_o_jeito_de_digitar_no_celular(texto, esperado):
    assert entender(texto, POSTOS) == esperado


@pytest.mark.parametrize("texto", ["", "   ", "blablabla", "centroo"])
def test_texto_sem_sentido_devolve_a_ajuda(texto):
    with pytest.raises(ValueError, match="estoque candói"):
        entender(texto, POSTOS)


def test_resumo_traz_mes_dia_e_estoque_com_a_data():
    df = _df(*[_linha(d) for d in pd.date_range("2026-09-01", periods=7)],
             _linha("2026-08-01", vendas=50))
    r = responder("resumo centro", df, _tanques("B2 Centro"), ["B2 Centro"])
    assert r.titulo == "📊 Resumo — B2 Centro"
    assert "📅 Setembro até 07/09 · dados simulados" in r.mensagem
    assert "⛽ Litros: 700 L" in r.mensagem
    assert "🗓️ Dia 07/09: R$ 600,00 · 100 L" in r.mensagem
    assert "⛽ Gasolina Comum: 1.000 L — 10,0 dias" in r.mensagem
    assert "hoje" not in r.mensagem.lower()


def test_estoque_critico_manda_confirmar_a_entrega():
    df = _df(*[_linha(d, estoque=50) for d in pd.date_range("2026-09-01", periods=7)])
    r = responder("estoque centro", df, _tanques("B2 Centro"), ["B2 Centro"], simulado=False)
    assert "Gasolina Comum: 50 L — 0,5 dia 🔴" in r.mensagem
    assert "Confirme hoje a entrega" in r.mensagem
    assert "simulados" not in r.mensagem


def test_sem_dado_nao_vira_nan_nem_quebra():
    vazio = pd.DataFrame()
    assert "Ainda não há dados" in responder("resumo centro", vazio, vazio, ["B2 Centro"]).mensagem
    df = _df(_linha("2026-09-01"))
    r = responder("estoque candoi", df, _tanques("B2 Centro", "B2 Candói"), ["B2 Centro", "B2 Candói"])
    assert "ainda não há planilha" in r.mensagem


def test_consulta_nao_altera_a_base():
    df = _df(*[_linha(d) for d in pd.date_range("2026-09-01", periods=7)])
    copia = df.copy(deep=True)
    for c in ("resumo centro", "vendas centro", "margem centro", "estoque centro", "resumo rede", "alertas"):
        responder(c, df, _tanques("B2 Centro"), ["B2 Centro"])
    pd.testing.assert_frame_equal(df, copia)


@SIMULADO
def test_demonstracao_conta_a_historia_certa():
    b = base.carregar()
    df = an.preparar(b.movimento)
    postos = b.postos["posto"].tolist()
    alertas = al.gerar(df, b.tanques, postos)
    estoque = responder("estoque candói", df, b.tanques, postos, alertas=alertas).mensagem
    assert "Diesel S10" in estoque and "🔴" in estoque
    rede = responder("resumo rede", df, b.tanques, postos, alertas=alertas).mensagem
    assert "🟢 Centro" in rede and "🔴 Candói" in rede
    lista = responder("alertas", df, b.tanques, postos, alertas=alertas).mensagem
    assert "EXIGE AÇÃO" in lista and "Primavera" in lista


@SIMULADO
def test_toda_resposta_cabe_no_celular_e_nao_tem_nan():
    b = base.carregar()
    df = an.preparar(b.movimento)
    postos = b.postos["posto"].tolist()
    alertas = al.gerar(df, b.tanques, postos)
    comandos = ["ajuda", "alertas"] + [f"{c} {p}" for c in ("resumo", "estoque", "vendas", "margem")
                                       for p in postos + ["rede"]]
    for comando in comandos:
        r = responder(comando, df, b.tanques, postos, alertas=alertas)
        assert len((r.titulo + r.mensagem).encode("utf-8")) <= 3500, comando
        assert "nan" not in r.mensagem.lower() and "inf " not in r.mensagem.lower(), comando
        assert all(len(c.encode("utf-8")) <= 64 for _, c in r.sugestoes), comando   # limite do Telegram
