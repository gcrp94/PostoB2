"""Motor de alertas — as regras, independentes do Streamlit.

Recebe a base já preparada (`analytics.preparar`) e devolve uma lista de
`Alerta`. Quem desenha é o painel; quem manda para o celular é o
`motor_alertas.py`. As duas saídas leem a MESMA lista: o dono não pode
receber no celular um alerta que o painel não mostra.

Três níveis, sempre com cor + ícone + palavra (nunca a cor sozinha):

* 🔴 **crítico** — exige ação (estoque acabando, perda que sugere vazamento);
* 🟡 **atenção** — merece olhar (margem caindo, venda fora do padrão);
* 🟢 **destaque** — o que vai bem (a Central não pode ser só problema).

Cada limite está numa constante aqui em cima, com o porquê. Mexer num
limite é mexer numa linha.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src import analytics as an
from src.formatting import (
    format_brl, format_decimal, format_litros, format_pct_simples, format_pp, format_rs_litro,
)
from src.theme import ICONES_COMBUSTIVEL

# Margem por litro dos últimos 7 dias contra os 30 dias anteriores a eles.
QUEDA_MARGEM_ATENCAO = 15.0      # %
QUEDA_MARGEM_CRITICA = 40.0
# Margem % do mês contra a média dos 12 meses fechados anteriores.
MARGEM_ABAIXO_HISTORICO_PP = 1.2
# Volume dos últimos 7 dias contra a média semanal das 8 semanas anteriores.
VENDA_ABAIXO_ATENCAO = -10.0     # %
VENDA_ABAIXO_CRITICA = -25.0
VENDA_ACIMA_DESTAQUE = 10.0
# Perda do LMC no mês, em % do vendido.
PERDA_CRITICA = an.TOLERANCIA_PERDA
PERDA_ATENCAO = an.ALERTA_PERDA
DIAS_MINIMOS_PERDA = 7           # com menos dias, a perda do mês ainda é ruído
# Posto com a última planilha N dias atrás dos outros.
DIAS_SEM_ENVIO = 2

ORDEM_NIVEL = {"critico": 0, "atencao": 1, "destaque": 2}
ICONE_NIVEL = {"critico": "🔴", "atencao": "🟡", "destaque": "🟢"}


@dataclass
class Alerta:
    nivel: str                   # critico | atencao | destaque
    tipo: str
    posto: str
    titulo: str                  # "ESTOQUE CRÍTICO"
    resumo: str                  # uma linha, vai para a Central e para o celular
    detalhes: list[str] = field(default_factory=list)
    produto: str | None = None
    aba: str = "Resumo"          # para onde o "Abrir →" leva, dentro do posto
    data_ref: date | None = None

    @property
    def chave(self) -> str:
        return f"{self.tipo}|{self.posto}|{self.produto or '-'}|{self.data_ref}"

    @property
    def icone(self) -> str:
        return ICONE_NIVEL[self.nivel]

    def texto_celular(self) -> str:
        return "\n".join([f"{self.posto} • {self.resumo}", *self.detalhes])


def _nome(produto: str) -> str:
    return f"{ICONES_COMBUSTIVEL.get(produto, '')} {produto}".strip()


# ---------------------------------------------------------------- regras ---
def regra_estoque(df, tanques) -> list[Alerta]:
    saida = []
    est = an.estoque_atual(df, tanques)
    for _, r in est[est["status"] != "ok"].iterrows():
        critico = r["status"] == "critico"
        dias = format_decimal(r["autonomia"], 1)
        saida.append(Alerta(
            nivel=r["status"], tipo="estoque", posto=r["posto"], produto=str(r["produto"]),
            titulo="ESTOQUE CRÍTICO" if critico else "ESTOQUE BAIXO",
            resumo=f"{r['produto']} com {dias} dia{'s' if r['autonomia'] >= 2 else ''} de autonomia",
            detalhes=[
                f"{_nome(r['produto'])}: {format_litros(r['estoque'])} ({format_pct_simples(r['pct'], 0)} do tanque)",
                f"Autonomia estimada: {dias} dia{'s' if r['autonomia'] >= 2 else ''}.",
                f"Consumo médio: {format_litros(r['media_dia'])}/dia (últimos 7 dias).",
            ],
            aba="Estoque", data_ref=r["data"].date()))
    return saida


def regra_perda(df, per: an.Periodo, postos: list[str]) -> list[Alerta]:
    if per.dias < DIAS_MINIMOS_PERDA:
        return []
    saida = []
    for posto in postos:
        t = an.perdas_lmc(df, per, posto)
        for _, r in t.iterrows():
            if r["perda_pct"] <= PERDA_ATENCAO:
                continue
            critico = r["perda_pct"] > PERDA_CRITICA
            saida.append(Alerta(
                nivel="critico" if critico else "atencao", tipo="perda", posto=posto,
                produto=str(r["produto"]),
                titulo="PERDA ACIMA DA TOLERÂNCIA" if critico else "PERDA ELEVADA NO LMC",
                resumo=f"{r['produto']} com perda de {format_pct_simples(r['perda_pct'], 2)} do vendido no mês",
                detalhes=[
                    f"{_nome(r['produto'])}: {format_litros(-r['perda_l'])} a menos na régua "
                    f"({format_brl(-r['perda_rs'])} em custo).",
                    f"Tolerância de referência: {format_pct_simples(PERDA_CRITICA, 1)} do vendido.",
                    "Verificar vazamento, aferição das bombas e medição dos tanques."
                    if critico else "Acompanhar a medição dos próximos dias.",
                ],
                aba="Estoque", data_ref=per.fim))
    return saida


def regra_desatualizado(df, data_ref, postos: list[str]) -> list[Alerta]:
    """Posto que ficou para trás dos outros no envio da planilha."""
    saida = []
    for posto in postos:
        ultima = an.ultima_data(df, posto)
        atraso = (data_ref - ultima).days
        if atraso < DIAS_SEM_ENVIO:
            continue
        saida.append(Alerta(
            nivel="atencao", tipo="desatualizado", posto=posto, titulo="DADOS DESATUALIZADOS",
            resumo=f"há {atraso} dias sem enviar a planilha",
            detalhes=[f"Última planilha com dados até {ultima:%d/%m/%Y}; os outros postos já "
                      f"estão em {data_ref:%d/%m}.",
                      "Os números deste posto no mês estão incompletos."],
            aba="Resumo", data_ref=data_ref))
    return saida


def regra_margem_produto(df, postos: list[str]) -> list[Alerta]:
    saida = []
    for posto in postos:
        data_ref = an.ultima_data(df, posto)
        fim_rec, ini_rec = data_ref, data_ref - timedelta(days=6)
        fim_base, ini_base = ini_rec - timedelta(days=1), ini_rec - timedelta(days=30)
        rec = an.recorte(df, ini_rec, fim_rec, posto).groupby("produto", observed=True)[
            ["margem", "vendas_l", "faturamento", "cmv"]].sum()
        base = an.recorte(df, ini_base, fim_base, posto).groupby("produto", observed=True)[
            ["margem", "vendas_l", "faturamento", "cmv"]].sum()
        for produto in rec.index:
            if produto not in base.index or not base.loc[produto, "vendas_l"]:
                continue
            m_rec = rec.loc[produto, "margem"] / rec.loc[produto, "vendas_l"]
            m_base = base.loc[produto, "margem"] / base.loc[produto, "vendas_l"]
            if m_base <= 0:
                continue
            queda = (m_base - m_rec) / m_base * 100
            if queda < QUEDA_MARGEM_ATENCAO:
                continue
            p_rec = rec.loc[produto, "faturamento"] / rec.loc[produto, "vendas_l"]
            p_base = base.loc[produto, "faturamento"] / base.loc[produto, "vendas_l"]
            c_rec = rec.loc[produto, "cmv"] / rec.loc[produto, "vendas_l"]
            c_base = base.loc[produto, "cmv"] / base.loc[produto, "vendas_l"]
            d_custo, d_preco = c_rec - c_base, p_rec - p_base
            if d_custo > 0.05 and d_preco < d_custo * 0.6:
                causa = (f"O custo subiu {format_rs_litro(d_custo)} e o preço de bomba, "
                         f"{format_rs_litro(max(d_preco, 0))} — o aumento não foi repassado.")
            elif d_preco < -0.03:
                causa = f"O preço de bomba caiu {format_rs_litro(-d_preco)} sem queda de custo equivalente."
            else:
                causa = "Preço e custo andaram em direções que comprimiram a margem."
            saida.append(Alerta(
                nivel="critico" if queda >= QUEDA_MARGEM_CRITICA else "atencao",
                tipo="margem_produto", posto=posto, produto=str(produto),
                titulo="MARGEM EM QUEDA",
                resumo=f"margem do {produto} caiu {format_pct_simples(queda, 1)}",
                detalhes=[
                    _nome(str(produto)),
                    f"Margem atual: {format_rs_litro(m_rec)} (últimos 7 dias).",
                    f"Média dos 30 dias anteriores: {format_rs_litro(m_base)}.",
                    f"Queda: {format_pct_simples(queda, 1)}. {causa}",
                ],
                aba="Margens", data_ref=data_ref))
    return saida


def regra_margem_historico(df, per: an.Periodo, postos: list[str]) -> list[Alerta]:
    saida = []
    for posto in postos:
        ind = an.indicadores(df, per, posto)
        hist = an.media_12_meses(df, per, posto)
        if hist["meses"] < 6 or np.isnan(ind["margem_pct"]):
            continue
        dif = ind["margem_pct"] - hist["margem_pct"]
        if dif > -MARGEM_ABAIXO_HISTORICO_PP:
            continue
        perdido = (hist["margem_litro"] - ind["margem_litro"]) * ind["litros"]
        saida.append(Alerta(
            nivel="atencao", tipo="margem_historico", posto=posto,
            titulo="MARGEM ABAIXO DO HISTÓRICO",
            resumo=f"margem bruta de {format_pct_simples(ind['margem_pct'], 1)} no mês, "
                   f"contra {format_pct_simples(hist['margem_pct'], 1)} na média de 12 meses",
            detalhes=[
                f"Margem do mês: {format_pct_simples(ind['margem_pct'], 1)} ({format_rs_litro(ind['margem_litro'])}).",
                f"Média dos 12 meses anteriores: {format_pct_simples(hist['margem_pct'], 1)} "
                f"({format_rs_litro(hist['margem_litro'])}).",
                f"Diferença: {format_pp(dif)} — cerca de {format_brl(perdido, 0)} a menos no mês.",
            ],
            aba="Margens", data_ref=per.fim))
    return saida


def regra_volume(df, postos: list[str]) -> list[Alerta]:
    saida = []
    for posto in postos:
        data_ref = an.ultima_data(df, posto)
        ini_rec = data_ref - timedelta(days=6)
        ini_base, fim_base = ini_rec - timedelta(days=56), ini_rec - timedelta(days=1)
        rec = an.recorte(df, ini_rec, data_ref, posto)["vendas_l"].sum()
        base = an.recorte(df, ini_base, fim_base, posto)["vendas_l"].sum() / 8
        if not base:
            continue
        var = (rec - base) / base * 100
        if var <= VENDA_ABAIXO_ATENCAO:
            nivel, titulo = ("critico" if var <= VENDA_ABAIXO_CRITICA else "atencao"), "VENDA FORA DO PADRÃO"
            resumo = f"vendas {format_pct_simples(-var, 1)} abaixo da média"
            frase = (f"Volume dos últimos 7 dias está {format_pct_simples(-var, 1)} abaixo "
                     "da média das 8 semanas anteriores.")
        elif var >= VENDA_ACIMA_DESTAQUE:
            nivel, titulo = "destaque", "VENDAS ACIMA DO PADRÃO"
            resumo = f"vendas {format_pct_simples(var, 1)} acima da média"
            frase = (f"Volume dos últimos 7 dias está {format_pct_simples(var, 1)} acima "
                     "da média das 8 semanas anteriores.")
        else:
            continue
        saida.append(Alerta(
            nivel=nivel, tipo="volume", posto=posto, titulo=titulo, resumo=resumo,
            detalhes=[frase, f"Últimos 7 dias: {format_litros(rec)} · média semanal: {format_litros(base)}."],
            aba="Vendas", data_ref=data_ref))
    return saida


def regra_destaques(df, per: an.Periodo, postos: list[str]) -> list[Alerta]:
    saida = []
    t = an.por_posto(df, per, postos)
    melhor = t.loc[t["margem_litro"].idxmax()]
    saida.append(Alerta(
        nivel="destaque", tipo="melhor_margem", posto=melhor["posto"],
        titulo="MAIOR MARGEM POR LITRO",
        resumo=f"maior margem por litro da rede no mês: {format_rs_litro(melhor['margem_litro'])}",
        detalhes=[f"Média da rede: {format_rs_litro(t['margem'].sum() / t['litros'].sum())}."],
        aba="Margens", data_ref=per.fim))
    maior = t.loc[t["faturamento"].idxmax()]
    saida.append(Alerta(
        nivel="destaque", tipo="maior_volume", posto=maior["posto"],
        titulo="MAIOR FATURAMENTO",
        resumo=f"maior faturamento da rede: {format_brl(maior['faturamento'], 0)} no mês",
        detalhes=[f"{format_litros(maior['litros'])} vendidos · "
                  f"{format_pct_simples(maior['faturamento'] / t['faturamento'].sum() * 100, 1)} da rede."],
        aba="Vendas", data_ref=per.fim))
    # Tendência de trimestre: litros por dia nos últimos 3 meses contra os 3 anteriores.
    for posto in postos:
        s = an.serie_mensal(df, posto)
        if len(s) < 6:
            continue
        rec, ant = s["litros_dia"].iloc[-3:].mean(), s["litros_dia"].iloc[-6:-3].mean()
        var = (rec - ant) / ant * 100
        if var >= 7:
            saida.append(Alerta(
                nivel="destaque", tipo="crescimento", posto=posto, titulo="VOLUME EM CRESCIMENTO",
                resumo=f"volume por dia {format_pct_simples(var, 1)} maior no último trimestre",
                detalhes=[f"Média de {format_litros(rec)}/dia nos últimos 3 meses, contra "
                          f"{format_litros(ant)}/dia nos 3 anteriores."],
                aba="Vendas", data_ref=per.fim))
    return saida


# -------------------------------------------------------------- execução ---
def gerar(df: pd.DataFrame, tanques: pd.DataFrame, postos: list[str]) -> list[Alerta]:
    """Todos os alertas, cada posto medido na SUA última data com dado."""
    data_ref = df["data"].max().date()
    per = an.periodo(df, data_ref.year, data_ref.month)
    alertas: list[Alerta] = []
    for regra in (lambda: regra_estoque(df, tanques),
                  lambda: regra_perda(df, per, postos),
                  lambda: regra_margem_produto(df, postos),
                  lambda: regra_margem_historico(df, per, postos),
                  lambda: regra_volume(df, postos),
                  lambda: regra_desatualizado(df, data_ref, postos),
                  lambda: regra_destaques(df, per, postos)):
        alertas.extend(regra())
    ordem_posto = {p: i for i, p in enumerate(postos)}
    alertas.sort(key=lambda a: (ORDEM_NIVEL[a.nivel], ordem_posto.get(a.posto, 99)))
    return alertas


def situacao_posto(alertas: list[Alerta], posto: str) -> str:
    niveis = {a.nivel for a in alertas if a.posto == posto}
    if "critico" in niveis:
        return "critico"
    if "atencao" in niveis:
        return "atencao"
    return "ok"
