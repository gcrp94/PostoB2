"""Testes do painel: as contas fecham, a conferência recusa o que deve e o
motor de alertas acha as situações da demonstração.

    python -m pytest

Rodam sobre a base que está em `data/base/` (a simulada, na apresentação).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import alertas as al
from src import analytics as an
from src import base, validacao

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLOS = RAIZ / "exemplos_para_envio"
# As histórias da demonstração só existem nos dados simulados.
SIMULADO = pytest.mark.skipif(not (RAIZ / "data" / "SIMULADO.txt").exists(),
                              reason="só com os dados simulados da demonstração")


@pytest.fixture(scope="module")
def b():
    return base.carregar()


@pytest.fixture(scope="module")
def df(b):
    return an.preparar(b.movimento)


@pytest.fixture(scope="module")
def postos(b):
    return b.postos["posto"].tolist()


def test_postos_somam_a_rede(df, postos):
    """O quadro das unidades fecha com os cartões da rede — ao centavo."""
    fim = df["data"].max()
    per = an.periodo(df, fim.year, fim.month)
    rede = an.indicadores(df, per)
    t = an.por_posto(df, per, postos)
    assert t["litros"].sum() == pytest.approx(rede["litros"])
    assert t["faturamento"].sum() == pytest.approx(rede["faturamento"], abs=0.01)
    assert t["margem"].sum() == pytest.approx(rede["margem"], abs=0.01)


def test_combustiveis_somam_o_posto(df, postos):
    fim = df["data"].max()
    per = an.periodo(df, fim.year, fim.month)
    for p in postos:
        comb = an.por_combustivel(df, per, p)
        ind = an.indicadores(df, per, p)
        assert comb["faturamento"].sum() == pytest.approx(ind["faturamento"], abs=0.01)


def test_comparacao_usa_os_mesmos_dias_de_cada_posto(df):
    """Posto atrasado no envio compara com os MESMOS dias dele no mês anterior."""
    fim = df["data"].max()
    for posto, g in df.groupby("posto"):
        per = an.periodo(g, fim.year, fim.month)
        if per.parcial:
            assert per.anterior_fim.day == min(per.fim.day, per.anterior_fim.day)
            assert per.anterior_fim.day == per.fim.day or per.anterior_fim.day < per.fim.day


def test_lmc_fecha(df):
    """Estoque inicial de cada dia = estoque final do dia anterior."""
    for _, g in df.sort_values("data").groupby(["posto", "produto"], observed=True):
        dif = (g["estoque_inicial"] - g["estoque_final"].shift()).iloc[1:].abs()
        assert (dif <= 1).all()


@SIMULADO
def test_motor_acha_as_situacoes_da_demonstracao(df, b, postos):
    alertas = al.gerar(df, b.tanques, postos)
    achados = {(a.tipo, a.posto, a.nivel) for a in alertas}
    assert ("estoque", "B2 Candói", "critico") in achados
    assert ("perda", "B2 Primavera", "critico") in achados
    assert ("margem_produto", "B2 Bonsucesso", "atencao") in achados
    assert ("volume", "B2 Índio", "atencao") in achados
    assert ("desatualizado", "B2 Primavera", "atencao") in achados
    # E nenhum alarme no posto que está em ordem.
    assert al.situacao_posto(alertas, "B2 Centro") == "ok"


@SIMULADO
def test_conferencia_recusa_planilha_com_erro(df, b, postos):
    arq = next(EXEMPLOS.glob("COM ERRO*.xlsx"))
    rel = validacao.validar(arq.read_bytes(), arq.name, "B2 Candói", postos, b.tanques, df)
    assert not rel.aprovado
    textos = " ".join(rel.erros)
    assert "Custo médio" in textos
    assert "estoque negativo em 17/09" in textos


@SIMULADO
def test_conferencia_aceita_planilha_boa_e_mostra_a_diferenca(df, b, postos):
    arq = next(EXEMPLOS.glob("GERENCIAL_B2_PRIMAVERA*.xlsx"))
    rel = validacao.validar(arq.read_bytes(), arq.name, "B2 Primavera", postos, b.tanques, df)
    assert rel.aprovado, rel.erros
    assert rel.comparacao["litros"] > 0          # traz os dias que faltavam


@SIMULADO
def test_conferencia_recusa_planilha_de_outro_posto(df, b, postos):
    arq = next(EXEMPLOS.glob("GERENCIAL_B2_PRIMAVERA*.xlsx"))
    rel = validacao.validar(arq.read_bytes(), arq.name, "B2 Centro", postos, b.tanques, df)
    assert any("Primavera" in e for e in rel.erros)
