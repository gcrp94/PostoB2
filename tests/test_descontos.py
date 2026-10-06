"""O botão "preço planilha × preço sistema": o desconto do boleto entre o custo da planilha e o custo cheio da nota.

    python -m pytest tests/test_descontos.py

Preço planilha = o que o posto paga (já com o desconto); preço sistema = planilha + desconto. Os dados são fabricados
com resposta conhecida (1.000 L por dia, custo R$ 5,00): cada número esperado sai de uma conta de cabeça.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import analytics as an
from src import antifraude, auditoria, base, descontos as desc


def tabela(*linhas):
    return pd.DataFrame(linhas, columns=desc.COLUNAS)


def movimento(posto="B2 Centro", produto="Gasolina Comum", dias=60, margem_dia=1000.0):
    inicio = pd.Timestamp(2026, 1, 1)
    return pd.DataFrame([{"posto": posto, "data": inicio + pd.Timedelta(days=d), "produto": produto,
                          "estoque_inicial": 20_000.0, "compras_l": 0.0, "vendas_l": 1000.0, "estoque_final": 19_000.0,
                          "custo_medio": 5.0, "preco_medio": 5.0 + margem_dia / 1000.0} for d in range(dias)])


def compras(*linhas, posto="B2 Centro", produto="Gasolina Comum"):
    """(dia do ano, litros, distribuidora)"""
    return pd.DataFrame([{"posto": posto, "data": pd.Timestamp(2026, 1, 1) + pd.Timedelta(days=d), "produto": produto,
                          "litros": l, "custo": 5.0, "valor": 5.0 * l, "nota_fiscal": f"NF{d}", "distribuidora": dist}
                         for d, l, dist in linhas])


# ----------------------------------------------------------------- a tabela ---
def test_por_compra_o_especifico_vale_mais_que_o_todos_e_sem_linha_e_zero():
    t = tabela(("Alfa", "Todos", 0.05), ("Alfa", "Etanol", 0.08), ("Sul", "Todos", 0.03))
    c = pd.DataFrame({"distribuidora": ["Alfa", "Alfa", "Sul", "Outra"],
                      "produto": ["Gasolina Comum", "Etanol", "Etanol", "Etanol"]})
    assert list(desc.por_compra(c, t)) == pytest.approx([0.05, 0.08, 0.03, 0.0])


def test_validar_descarta_o_que_nao_presta_e_aceita_virgula_decimal():
    bruta = pd.DataFrame({"distribuidora": ["Alfa", "", "Sul", "Paraná", "Alfa"],
                          "produto": ["", "Etanol", "Todos", "Etanol", ""],
                          "desconto": ["0,06", "0,05", "-0.01", "9,9", "0,07"]})        # vazia, negativa, absurda, repetida
    limpa, avisos = desc.validar(bruta)
    assert list(limpa["distribuidora"]) == ["Alfa"] and limpa.loc[0, "desconto"] == pytest.approx(0.07)   # ficou a última
    assert limpa.loc[0, "produto"] == desc.TODOS and avisos


def test_gravar_e_carregar_voltam_iguais_e_arquivo_ausente_e_tabela_vazia(tmp_path):
    arq = tmp_path / "d.csv"
    assert desc.carregar(arq).empty and desc.assinatura(arq) == 0
    desc.gravar(tabela(("Alfa", "Todos", 0.06), ("Sul", "Etanol", 0.09)), arq)
    t = desc.carregar(arq)
    assert list(t["distribuidora"]) == ["Alfa", "Sul"] and list(t["desconto"]) == pytest.approx([0.06, 0.09])
    assert desc.assinatura(arq) > 0 and not list(tmp_path.glob("*.tmp"))


# ---------------------------------------------------- o desconto de cada dia ---
def test_desconto_diario_e_a_media_ponderada_pelos_litros_das_compras_dos_ultimos_30_dias():
    mov = movimento(dias=60)
    c = compras((0, 10_000, "Alfa"), (4, 30_000, "Sul"))
    t = tabela(("Alfa", "Todos", 0.10), ("Sul", "Todos", 0.05))
    d = desc.desconto_diario(mov, c, t)
    assert d.iloc[0] == pytest.approx(0.10)                                  # antes da 2ª compra: só a primeira
    assert d.iloc[4] == pytest.approx(0.0625)                                # (10.000×0,10 + 30.000×0,05) ÷ 40.000


def test_a_compra_sai_da_janela_depois_de_30_dias_e_sem_compra_vale_o_ultimo_conhecido():
    mov = movimento(dias=60)
    c = compras((0, 10_000, "Alfa"), (4, 30_000, "Sul"))
    t = tabela(("Alfa", "Todos", 0.10), ("Sul", "Todos", 0.05))
    d = desc.desconto_diario(mov, c, t)
    assert d.iloc[29] == pytest.approx(0.0625)                               # a janela é de 30 dias: no dia 29 a compra do dia 0 ainda conta
    assert d.iloc[30] == pytest.approx(0.05)                                 # no dia 30 ela saiu; sobrou a do dia 4
    assert d.iloc[59] == pytest.approx(0.05)                                 # depois de 30 dias sem compra: o último conhecido


def test_antes_da_primeira_compra_vale_o_primeiro_desconto_conhecido():
    mov = movimento(dias=20)
    c = compras((10, 10_000, "Alfa"))
    d = desc.desconto_diario(mov, c, tabela(("Alfa", "Todos", 0.07)))
    assert d.iloc[0] == pytest.approx(0.07) and d.iloc[19] == pytest.approx(0.07)


def test_cada_posto_e_produto_tem_o_proprio_desconto_e_sem_tabela_ou_compras_tudo_zero():
    mov = pd.concat([movimento("B2 Centro", dias=10), movimento("B2 Índio", dias=10)], ignore_index=True)
    c = pd.concat([compras((0, 10_000, "Alfa"), posto="B2 Centro"), compras((0, 10_000, "Sul"), posto="B2 Índio")])
    t = tabela(("Alfa", "Todos", 0.10), ("Sul", "Todos", 0.04))
    d = desc.desconto_diario(mov, c, t)
    assert d[mov["posto"] == "B2 Centro"].iloc[0] == pytest.approx(0.10) and d[mov["posto"] == "B2 Índio"].iloc[0] == pytest.approx(0.04)
    assert (desc.desconto_diario(mov, c, tabela()) == 0).all() and (desc.desconto_diario(mov, None, t) == 0).all()


# -------------------------------------------------------------- o botão ---
def preparado(custo, mov=None, c=None, t=None):
    return an.preparar(mov if mov is not None else movimento(dias=10),
                       c if c is not None else compras((0, 10_000, "Alfa")),
                       t if t is not None else tabela(("Alfa", "Todos", 0.10)), custo)


def test_modo_planilha_nao_muda_nada_e_sem_tabela_os_dois_precos_sao_iguais():
    assert an.preparar(movimento(dias=10))["margem"].sum() == pytest.approx(preparado("planilha")["margem"].sum())
    sem = an.preparar(movimento(dias=10), None, None, "sistema")
    assert sem["margem"].sum() == pytest.approx(10_000) and (sem["desconto_litro"] == 0).all()


def test_modo_sistema_soma_o_desconto_ao_custo_e_a_margem_cai_na_mesma_conta():
    plan, sis = preparado("planilha"), preparado("sistema")
    assert plan["margem"].sum() == pytest.approx(10_000)                     # 1.000 L × R$ 1,00 × 10 dias
    assert sis["margem"].sum() == pytest.approx(9_000)                       # menos 1.000 L × R$ 0,10 × 10 dias
    assert (sis["custo_medio"] - plan["custo_medio"]).round(4).eq(0.10).all()
    for df in (plan, sis):                                                   # os dois custos ficam nas duas tabelas
        assert df["custo_planilha"].eq(5.0).all() and df["custo_sistema"].round(6).eq(5.10).all()


def test_perda_do_lmc_tambem_e_valorada_no_custo_escolhido():
    mov = movimento(dias=2)
    mov["estoque_final"] = [18_900.0, 19_000.0]                              # perde 100 L no 1º dia
    plan, sis = preparado("planilha", mov), preparado("sistema", mov)
    assert plan["perda_rs"].iloc[0] == pytest.approx(-500.0) and sis["perda_rs"].iloc[0] == pytest.approx(-510.0)


def test_modo_invalido_e_recusado():
    with pytest.raises(ValueError):
        an.preparar(movimento(dias=3), None, None, "outro")


def test_o_ponto_de_equilibrio_chega_mais_tarde_no_preco_do_sistema():
    mov = movimento(dias=31)
    desp = pd.DataFrame([{"posto": "B2 Centro", "data": pd.Timestamp(2026, 1, 5), "categoria": "Aluguel",
                          "descricao": "t", "valor": 10_000.0}])
    c, t = compras((0, 10_000, "Alfa")), tabela(("Alfa", "Todos", 0.10))
    plan = an.equilibrio_mes(an.preparar(mov, c, t, "planilha"), desp, "B2 Centro", 2026, 1)
    sis = an.equilibrio_mes(an.preparar(mov, c, t, "sistema"), desp, "B2 Centro", 2026, 1)
    assert plan["dia_equilibrio"] == 10 and sis["dia_equilibrio"] == 12      # 1.000/dia × 10 dias; 900/dia → 11,1 → dia 12


# -------------------------------------- as conferências olham o que o posto informou ---
def test_antifraude_nao_acusa_o_desconto_do_boleto_nem_muda_com_o_botao():
    b = base.carregar()
    t = tabela(("Distribuidora Alfa", "Todos", 0.07), ("Distribuidora Sul", "Todos", 0.09),
               ("Distribuidora Paraná", "Todos", 0.05))
    ultimo = b.movimento["data"].max()
    per = an.periodo(an.preparar(b.movimento), ultimo.year, ultimo.month)
    postos = b.postos["posto"].tolist()
    plan = antifraude.sinais(an.preparar(b.movimento, b.compras, t, "planilha"), b.compras, auditoria.ler(), postos, per)
    sis = antifraude.sinais(an.preparar(b.movimento, b.compras, t, "sistema"), b.compras, auditoria.ler(), postos, per)
    chave = lambda s: (s.tipo, s.posto, s.titulo, s.detalhe)                 # noqa: E731
    assert sorted(map(chave, plan)) == sorted(map(chave, sis))
