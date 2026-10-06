"""Ponto de equilíbrio: o dia do mês em que o acumulado (margem bruta + perda/sobra) cobriu os custos.

    python -m pytest tests/test_equilibrio.py

Os dados são fabricados com resposta conhecida: 1.000 L/dia vendidos, custo R$ 5,00, preço escolhido para dar a
margem do dia que o teste quer — assim cada número esperado sai de uma conta que dá para fazer de cabeça.
"""
from __future__ import annotations

import calendar

import pandas as pd
import pytest

from src import analytics as an

CUSTO = 5.0


def movimento(posto="B2 Centro", ano=2026, mes=1, ate_dia=31, margem_dia=1000.0, perdas=None, sem_dado=()):
    """1.000 L por dia; `perdas` = {dia: reais perdidos no LMC}; `sem_dado` = dias sem planilha."""
    perdas = perdas or {}
    linhas = []
    for d in range(1, ate_dia + 1):
        if d in sem_dado:
            continue
        vendas = 1000.0
        linhas.append({"posto": posto, "data": pd.Timestamp(ano, mes, d), "produto": "Gasolina Comum",
                       "estoque_inicial": 20_000.0, "compras_l": 0.0, "vendas_l": vendas,
                       "estoque_final": 20_000.0 - vendas - perdas.get(d, 0.0) / CUSTO,
                       "custo_medio": CUSTO, "preco_medio": CUSTO + margem_dia / vendas})
    return pd.DataFrame(linhas)


def despesas(posto="B2 Centro", ano=2026, mes=1, valor=10_000.0, dia=5):
    return pd.DataFrame([{"posto": posto, "data": pd.Timestamp(ano, mes, dia), "categoria": "Folha de pagamento",
                          "descricao": "teste", "valor": valor}])


def juntar(*partes):
    return pd.concat([p for p in partes if len(p)], ignore_index=True)


def preparado(*partes):
    return an.preparar(juntar(*partes))


# ---------------------------------------------------------------- um mês ---
def test_mes_fechado_acha_o_dia_em_que_o_acumulado_cobre_os_custos():
    df = preparado(movimento())                                   # R$ 1.000/dia, mês inteiro
    eq = an.equilibrio_mes(df, despesas(valor=10_000), "B2 Centro", 2026, 1)
    assert eq["disponivel"] and not eq["parcial"]
    assert eq["dia_equilibrio"] == 10                             # 10 × 1.000 = 10.000 no dia 10
    assert eq["custos"] == 10_000 and not eq["custos_estimados"]
    assert eq["acumulado"] == pytest.approx(31_000) and eq["resultado_ate_agora"] == pytest.approx(21_000)
    assert eq["dias_acima"] == 21 and eq["falta"] == 0
    assert eq["curva"].loc[10] == pytest.approx(10_000) and len(eq["curva"]) == 31


def test_mes_fechado_que_nao_cobriu_diz_quanto_faltou_e_nao_inventa_previsao():
    df = preparado(movimento(margem_dia=200))                     # 31 × 200 = 6.200 < 10.000
    eq = an.equilibrio_mes(df, despesas(valor=10_000), "B2 Centro", 2026, 1)
    assert eq["dia_equilibrio"] is None and eq["falta"] == pytest.approx(3_800)
    assert eq["previsto_dia"] is None and eq["fecha_no_mes"] is None


def test_mes_em_andamento_projeta_pelo_ritmo_dos_ultimos_7_dias():
    df = preparado(movimento(ate_dia=12))                         # 12.000 até o dia 12
    eq = an.equilibrio_mes(df, despesas(valor=20_000), "B2 Centro", 2026, 1)
    assert eq["parcial"] and eq["dia_equilibrio"] is None
    assert eq["falta"] == pytest.approx(8_000) and eq["ritmo"] == pytest.approx(1_000)
    assert eq["dias_faltam"] == 8 and eq["previsto_dia"] == 20 and eq["fecha_no_mes"] is True
    assert eq["pct_coberto"] == pytest.approx(60)


def test_mes_em_andamento_que_nao_fecha_no_mes_avisa():
    df = preparado(movimento(ate_dia=12, margem_dia=100))         # 100/dia: faltam 18.800 → 188 dias
    eq = an.equilibrio_mes(df, despesas(valor=20_000), "B2 Centro", 2026, 1)
    assert eq["previsto_dia"] > eq["dias_mes"] and eq["fecha_no_mes"] is False


def test_ritmo_zero_ou_negativo_nao_dividie_nem_promete_data():
    df = preparado(movimento(ate_dia=12, margem_dia=0))
    eq = an.equilibrio_mes(df, despesas(valor=20_000), "B2 Centro", 2026, 1)
    assert eq["previsto_dia"] is None and eq["fecha_no_mes"] is False


def test_mes_em_andamento_estima_os_custos_pela_media_dos_meses_fechados_se_o_lancado_for_menor():
    df = preparado(movimento(mes=11, ate_dia=30), movimento(mes=12, ate_dia=31), movimento(mes=1, ano=2027, ate_dia=10))
    desp = juntar(despesas(mes=11, valor=10_000), despesas(mes=12, valor=12_000),
                  despesas(mes=1, ano=2027, valor=3_000))         # janeiro: só 3.000 lançados até agora
    eq = an.equilibrio_mes(df, desp, "B2 Centro", 2027, 1)
    assert eq["custos_lancados"] == 3_000 and eq["custos"] == pytest.approx(11_000)    # média de nov e dez
    assert eq["custos_estimados"] is True


def test_perda_do_lmc_reduz_o_acumulado_e_sobra_aumenta():
    df = preparado(movimento(ate_dia=10, perdas={3: 600}))        # perde R$ 600 no dia 3
    eq = an.equilibrio_mes(df, despesas(valor=20_000), "B2 Centro", 2026, 1)
    assert eq["acumulado"] == pytest.approx(10_000 - 600)
    sobra = preparado(movimento(ate_dia=10, perdas={3: -400}))    # sobra de R$ 400
    assert an.equilibrio_mes(sobra, despesas(valor=20_000), "B2 Centro", 2026, 1)["acumulado"] == pytest.approx(10_400)


def test_dia_sem_planilha_conta_zero_e_o_acumulado_nao_pula():
    df = preparado(movimento(sem_dado={4, 5}))
    eq = an.equilibrio_mes(df, despesas(valor=10_000), "B2 Centro", 2026, 1)
    assert eq["curva"].loc[5] == pytest.approx(3_000)             # dias 1,2,3 contam; 4 e 5 valem zero
    assert eq["dia_equilibrio"] == 12                             # 10.000 só no 10º dia COM venda (dia 12)


def test_sem_despesas_ou_sem_vendas_nao_inventa_equilibrio():
    df = preparado(movimento())
    sem = an.equilibrio_mes(df, despesas(valor=10_000).iloc[0:0], "B2 Centro", 2026, 1)
    assert not sem["disponivel"] and "DESPESAS" in sem["motivo"]
    assert not an.equilibrio_mes(df, despesas(), "B2 Centro", 2026, 5)["disponivel"]
    assert not an.equilibrio_mes(df, despesas(), "Outro Posto", 2026, 1)["disponivel"]


def test_litros_para_empatar_saem_dos_custos_e_da_margem_por_litro():
    df = preparado(movimento())                                   # margem R$ 1,00 por litro
    eq = an.equilibrio_mes(df, despesas(valor=10_000), "B2 Centro", 2026, 1)
    assert eq["margem_litro"] == pytest.approx(1.0) and eq["litros_equilibrio_mes"] == pytest.approx(10_000)
    assert eq["litros_dia_equilibrio"] == pytest.approx(10_000 / 31) and eq["litros_dia_atual"] == pytest.approx(1_000)


# -------------------------------------------------------- as médias ---
def cenario():
    """3 postos em 6 meses fechados + o mês atual. O Centro cobre no dia 10 (margem 1.000/dia, custos 10.000)."""
    partes, desp = [], []
    for posto, margem, custo in (("B2 Centro", 1000, 10_000), ("B2 Índio", 500, 10_000), ("B2 Candói", 2000, 10_000)):
        for mes in range(7, 13):
            partes.append(movimento(posto, 2025, mes, ate_dia=calendar.monthrange(2025, mes)[1], margem_dia=margem))
            desp.append(despesas(posto, 2025, mes, custo))
        partes.append(movimento(posto, 2026, 1, ate_dia=31, margem_dia=margem))
        desp.append(despesas(posto, 2026, 1, custo))
    return preparado(*partes), juntar(*desp)


def test_historico_do_proprio_posto_e_a_media_de_dias_dos_meses_anteriores():
    df, desp = cenario()
    eq = an.equilibrio(df, desp, "B2 Centro", 2026, 1)
    h = eq["historico"]
    assert h["n"] == 6 and h["n_cobriu"] == 6 and h["media_dia"] == pytest.approx(10.0)     # sempre no dia 10
    assert h["meses"][0][:2] == (2025, 7) and h["curva_media"].loc[10] == pytest.approx(10_000)
    assert eq["dia_equilibrio"] == 10                                                       # igual à média: nem melhor nem pior


def test_media_da_rede_compara_o_mesmo_mes_dos_tres_postos():
    df, desp = cenario()
    eq = an.equilibrio(df, desp, "B2 Centro", 2026, 1)
    dias = {p: v["dia"] for p, v in eq["rede"]["postos"].items()}
    assert dias == {"B2 Centro": 10, "B2 Índio": 20, "B2 Candói": 5}                         # 10.000 ÷ 500 = 20; ÷ 2.000 = 5
    assert eq["rede"]["media_dia"] == pytest.approx((10 + 20 + 5) / 3)
    assert all(v["cobriu"] and not v["previsto"] for v in eq["rede"]["postos"].values())


def test_na_rede_o_posto_que_ainda_nao_cobriu_entra_pela_previsao_e_vem_marcado():
    df, desp = cenario()
    df = preparado(df[~((df["posto"] == "B2 Índio") & (df["data"] > "2026-01-12"))])         # Índio só até o dia 12
    eq = an.equilibrio(df, desp, "B2 Centro", 2026, 1)
    indio = eq["rede"]["postos"]["B2 Índio"]
    assert indio["previsto"] and not indio["cobriu"] and indio["dia"] == 12 + 8              # falta 4.000 a 500/dia = 8 dias


def test_sem_historico_nao_inventa_media():
    df = preparado(movimento())
    eq = an.equilibrio(df, despesas(valor=10_000), "B2 Centro", 2026, 1)
    assert eq["historico"]["n"] == 0 and eq["historico"]["media_dia"] is None and eq["historico"]["curva_media"] is None


# ---------------------------------------------------------- a régua do LB ---
def regua(**kw):
    from src import equilibrio_ui
    base = {"acumulado": 31_000.0, "custos": 10_000.0}
    return equilibrio_ui._regua({**base, **kw})


def test_regua_cobriu_mostra_o_que_cobre_em_azul_e_o_que_passa_em_laranja():
    h = regua()                                                    # LB 31.000 contra custos 10.000
    assert 'class="eq-lb" style="width:32.26%"' in h and 'class="eq-extra" style="width:67.74%"' in h
    assert 'class="eq-tique" style="left:32.26%"' in h and "eq-falta" not in h
    assert "LB <b>R$ 31,0 mil</b>" in h and "Custos <b>R$ 10,0 mil</b>" in h and "+ <b>R$ 21,0 mil</b>" in h


def test_regua_ainda_falta_mostra_o_vazio_listrado_e_quanto_falta():
    h = regua(acumulado=12_000.0, custos=20_000.0)
    assert 'class="eq-lb" style="width:60.00%"' in h and 'class="eq-falta" style="width:40.00%"' in h
    assert 'class="eq-tique" style="left:100.00%"' in h and "eq-extra" not in h
    assert "faltam <b>R$ 8,0 mil</b>" in h and "LB <b>R$ 12,0 mil</b>" in h


def test_regua_empate_exato_nao_inventa_sobra_nem_falta():
    h = regua(acumulado=10_000.0, custos=10_000.0)
    assert "eq-extra" not in h and "eq-falta" not in h and 'style="width:100.00%"' in h


def test_regua_com_lb_negativo_nao_quebra_e_a_trilha_fica_vazia():
    h = regua(acumulado=-500.0, custos=10_000.0)
    assert 'class="eq-lb" style="width:0.00%"' in h and "faltam <b>R$ 10,5 mil</b>" in h
