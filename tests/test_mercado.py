"""Radar de Mercado: leitura da ANP, ranking de preço, repasse entre duas datas e a escolha dos arquivos.

    python -m pytest tests/test_mercado.py

Os dados são fabricados aqui: o teste não depende de baixar nada da ANP.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src import mercado

B2 = "09182266000177"


def bruto(*linhas):
    """CSV da ANP em miniatura: (município, cnpj, produto, data, preço, estado)."""
    return pd.DataFrame([{
        "﻿Regiao - Sigla": "S", "Estado - Sigla": uf, "Municipio": mun, "Revenda": f"POSTO {cnpj[-4:]} LTDA",
        "CNPJ da Revenda": cnpj, "Nome da Rua": "RUA X", "Numero Rua": "10", "Complemento": "", "Bairro": "Centro",
        "Cep": "", "Produto": prod, "Data da Coleta": dia, "Valor de Venda": preco, "Valor de Compra": "",
        "Unidade de Medida": "R$ / litro", "Bandeira": "BRANCA"} for mun, cnpj, prod, dia, preco, uf in linhas])


def precos(*linhas):
    """Preços já normalizados: (cnpj, produto, 'AAAA-MM-DD', preço)."""
    return pd.DataFrame([{"data": pd.Timestamp(d), "cnpj": c, "revenda": f"POSTO {c}", "rua": "", "numero": "",
                          "bairro": "CENTRO", "municipio": "GUARAPUAVA", "produto": p, "preco": v,
                          "bandeira": "Branca", "eh_b2": c == B2} for c, p, d, v in linhas])


# ---------------------------------------------------------------- leitura ----
def test_normalizar_filtra_cidade_produto_e_arruma_o_cnpj():
    b = bruto(("GUARAPUAVA", "09.182.266/0001-77", "GASOLINA", "02/09/2026", "5,59", "PR"),
              ("GUARAPUAVA", "09182266000177", "GASOLINA", "02/09/2026", "5,59", "PR"),      # mesmo posto, CNPJ sem pontos
              ("CANDÓI", "10592615000108", "ETANOL", "02/09/2026", "3,69", "PR"),
              ("GUARAPUAVA", "11111111000111", "DIESEL", "02/09/2026", "6,10", "PR"),          # S500 não entra
              ("CURITIBA", "22222222000122", "GASOLINA", "02/09/2026", "6,00", "PR"),
              ("GUARAPUAVA", "33333333000133", "GASOLINA", "02/09/2026", "6,00", "SP"))
    n = mercado.normalizar_precos(b)
    assert set(n["cnpj"]) == {"09182266000177", "10592615000108"}
    assert len(n) == 2                                         # o duplicado de CNPJ formatado de outro jeito sumiu
    assert n.loc[n["cnpj"] == B2, "preco"].iloc[0] == pytest.approx(5.59)
    assert n.loc[n["cnpj"] == B2, "eh_b2"].iloc[0] and n["municipio"].tolist().count("CANDOI") == 1


def test_cadastro_marca_as_unidades_do_b2_e_da_nome():
    cad = pd.DataFrame([
        {"UF": "PR", "MUNICIPIO": "GUARAPUAVA", "CNPJ": "09182266000177", "RAZAOSOCIAL": "BEGNINI COMERCIO LTDA",
         "ENDERECO": "RUA GUAIRA,  3148", "BAIRRO": "CENTRO", "BANDEIRA": "BANDEIRA BRANCA"},
        {"UF": "PR", "MUNICIPIO": "CANDÓI", "CNPJ": "10592615000108", "RAZAOSOCIAL": "B2 COMERCIO DE COMBUSTIVEIS LTDA",
         "ENDERECO": "AV XV,  1571", "BAIRRO": "CENTRO", "BANDEIRA": "BANDEIRA BRANCA"},
        {"UF": "PR", "MUNICIPIO": "GUARAPUAVA", "CNPJ": "55555555000155", "RAZAOSOCIAL": "OUTRO POSTO LTDA",
         "ENDERECO": "RUA Y,  1", "BAIRRO": "CENTRO", "BANDEIRA": "IPIRANGA"}])
    c = mercado.normalizar_cadastro(cad)
    u = mercado.unidades_b2(c, precos((B2, "GASOLINA", "2026-09-02", 5.59)))
    assert list(u["nome"]) == ["B2 Centro", "B2 Candói"]                # a ordem do dono, não a alfabética
    assert dict(zip(u["nome"], u["tem_preco"])) == {"B2 Candói": False, "B2 Centro": True}


def test_nomes_do_dono_vem_do_cnpj_o_indio_e_o_posto_do_bairro_conradinho():
    assert mercado.nome_unidade("GUARAPUAVA", "CONRADINHO", "09182266000258") == "B2 Índio"
    assert mercado.nome_unidade("GUARAPUAVA", "PRIMAVERA", "09182266000410") == "B2 Primavera"
    assert mercado.nome_unidade("GUARAPUAVA", "BONSUCESSO", "09182266000339") == "B2 Bonsucesso"
    assert mercado.nome_unidade("CANDOI", "CENTRO", "10592615000108") == "B2 Candói"
    assert mercado.nome_unidade("GUARAPUAVA", "VILA NOVA", "09182266000999") == "B2 Vila Nova"   # unidade futura: cai no bairro


def test_preco_informado_entra_na_foto_e_informar_de_novo_troca_sem_duplicar():
    p = precos(("a", "GASOLINA", "2026-09-20", 5.59), ("b", "GASOLINA", "2026-09-21", 6.09))
    f = mercado.foto(p, "GASOLINA")
    un = pd.Series({"cnpj": "09182266000410", "razao": "BEGNINI COMERCIO LTDA", "bairro": "PRIMAVERA",
                    "municipio": "GUARAPUAVA", "bandeira": "Bandeira Branca"})
    g = mercado.com_preco_informado(f, un, "GASOLINA", 5.79, "2026-09-22")
    pos = mercado.posicao(g, un["cnpj"])
    assert pos["preco"] == pytest.approx(5.79) and pos["posicao"] == 2 and pos["n"] == 3
    assert bool(g.loc[un["cnpj"], "eh_b2"]) and g.loc[un["cnpj"], "bandeira"] == "Branca"
    outro = mercado.com_preco_informado(g, un, "GASOLINA", 5.50, "2026-09-23")          # informar de novo troca, não duplica
    assert len(outro) == 3 and mercado.posicao(outro, un["cnpj"])["posicao"] == 1      # a R$ 5,50 passa a ser o mais barato


# ------------------------------------------------------------- posição -----
def test_posicao_conta_so_quem_e_mais_barato_e_empate_divide_a_posicao():
    p = precos(("a", "GASOLINA", "2026-09-20", 5.59), ("b", "GASOLINA", "2026-09-21", 5.79),
               (B2, "GASOLINA", "2026-09-22", 5.79), ("c", "GASOLINA", "2026-09-22", 6.09))
    pos = mercado.posicao(mercado.foto(p, "GASOLINA"), B2)
    assert pos["posicao"] == 2 and pos["n"] == 4                # empatado com "b": os dois são 2º
    assert pos["minimo"] == pytest.approx(5.59) and pos["media"] == pytest.approx(5.815)


def test_foto_usa_a_ultima_coleta_de_cada_posto_dentro_da_janela():
    p = precos(("a", "GASOLINA", "2026-08-01", 5.00), ("a", "GASOLINA", "2026-09-20", 6.00),
               ("b", "GASOLINA", "2026-07-01", 4.00),                                          # velho demais
               ("c", "GASOLINA", "2026-09-27", 6.20))
    f = mercado.foto(p, "GASOLINA")                             # janela padrão de 14 dias até 27/09
    assert set(f.index) == {"a", "c"} and f.loc["a", "preco"] == 6.00


# ------------------------------------------------------------ repasse ------
def test_variacao_compara_so_os_mesmos_postos_nas_duas_pontas():
    p = precos(("a", "DIESEL S10", "2026-09-01", 6.50), ("a", "DIESEL S10", "2026-09-27", 7.30),
               (B2, "DIESEL S10", "2026-09-02", 6.49), (B2, "DIESEL S10", "2026-09-26", 7.49),
               ("so_antes", "DIESEL S10", "2026-09-01", 6.00),
               ("so_depois", "DIESEL S10", "2026-09-27", 9.00))      # um posto novo na amostra não pode puxar a média
    v = mercado.variacao(p, "DIESEL S10", "2026-09-02", "2026-09-28")
    assert set(v["cnpj"]) == {"a", B2}
    assert v.set_index("cnpj").loc[B2, "variacao"] == pytest.approx(1.00)
    assert v["variacao"].median() == pytest.approx(0.90)


# --------------------------------------------------------- série e achados --
def test_serie_semanal_pula_semana_sem_postos_suficientes_ou_sem_o_b2():
    linhas = []
    for sem, dia in enumerate(["2026-09-01", "2026-09-08", "2026-09-15"]):
        for i, v in enumerate([5.9, 6.0, 6.1, 6.2]):
            linhas.append((f"p{i}", "GASOLINA", dia, v))
        if sem != 1:                                              # na 2ª semana o B2 não foi pesquisado
            linhas.append((B2, "GASOLINA", dia, 5.95))
    linhas.append(("sozinho", "GASOLINA", "2026-09-22", 6.0))     # semana com 1 posto só
    s = mercado.serie_semanal(precos(*linhas), "GASOLINA", B2)
    assert len(s) == 2 and list(s["posicao"]) == [2, 2]
    r = mercado.ranking_historico(s)
    assert r["primeiro"] == 0 and r["top3"] == 1


def test_premio_da_aditivada_percebe_quando_e_sempre_igual():
    linhas = []
    for dia in ["2026-09-01", "2026-09-08", "2026-09-15"]:
        linhas += [(B2, "GASOLINA", dia, 5.69), (B2, "GASOLINA ADITIVADA", dia, 5.69),
                   ("x", "GASOLINA", dia, 5.89), ("x", "GASOLINA ADITIVADA", dia, 6.19)]
    prem = mercado.premio_aditivada(precos(*linhas), B2)
    assert prem["sempre_igual"] and prem["coletas"] == 3
    assert prem["mercado_mediana"] == pytest.approx(0.30) and prem["mercado_com_premio"] == 1.0


# ---------------------------------------------------- escolher os arquivos ---
HTML = """
<a href="https://x/dsas/ca/ca-2025-02.zip">s2</a><a href="https://x/dsas/ca/ca-2026-01.zip">s1</a>
<a href="https://x/dsan/2026/07-dados-abertos-precos-gasolina-etanol.csv">j</a>
<a href="https://x/dsan/2026/07-dados-abertos-precos-diesel-gnv.csv">j</a>
<a href="https://x/dsan/2026/08-dados-abertos-precos-2026-08-gasolina-etanol.csv">a</a>
<a href="https://x/dsan/2026/04-dados-abertos-precos-gasolina-etanol">sem extensão</a>
<a href="https://x/dsan/2025/precos-gasolina-etanol-12.csv">velho</a>
<a href="https://x/dsan/2026/07-dados-abertos-precos-glp.csv">glp</a>
"""


def test_descobrir_links_entende_os_nomes_irregulares():
    links = mercado.descobrir_links(HTML)
    assert set(links["semestres"]) == {(2025, 2), (2026, 1)}
    assert (2026, 4, "gasolina-etanol") in links["mensais"]            # o de abril vem sem ".csv"
    assert (2025, 12, "gasolina-etanol") in links["mensais"]
    assert not any("glp" in u for u in links["mensais"].values())


def test_selecionar_usa_o_semestre_fechado_e_o_mensal_so_para_o_que_sobra():
    escolhidos = dict(mercado.selecionar(mercado.descobrir_links(HTML), date(2026, 8, 20), meses=15))
    assert "ca-2025-02.zip" in escolhidos and "ca-2026-01.zip" in escolhidos
    assert "2026-07-gasolina-etanol.csv" in escolhidos and "2026-08-gasolina-etanol.csv" in escolhidos
    assert "2026-04-gasolina-etanol.csv" not in escolhidos             # abril já está no zip do 1º semestre
    assert "2025-12-gasolina-etanol.csv" not in escolhidos
    assert "cadastro-revendedores.csv" in escolhidos
