"""Sinais de fraude — o que a planilha permite cruzar para achar desvio.

Nenhum sinal é acusação: é "confira isto". Cada um diz o que achou, onde, e
por que importa. Os cruzamentos usam o que o posto JÁ manda (movimento
diário, notas das distribuidoras e a trilha de auditoria):

1. **Dado alterado depois de recebido** (trilha de auditoria) — o sinal mais
   forte: venda de dia antigo baixada depois de informada é o jeito de
   "sumir" com dinheiro do caixa.
2. **Perda ou sobra no LMC acima da tolerância** — perda é combustível que
   saiu sem venda registrada (vazamento, bomba descalibrada ou venda por fora);
   sobra grande sugere medição errada ou produto adulterado (água, solvente).
3. **Combustível recebido sem nota** — o movimento diz que entrou carga e não
   há nota da distribuidora no dia: carga desviada, ou compra "por fora".
4. **Nota sem entrada no tanque** — o contrário: nota lançada e nada entrou no
   tanque. Nota fria, ou carga que foi parar em outro lugar.
5. **Nota fiscal repetida** — a mesma nota lançada duas vezes infla custo e
   contas a pagar.
6. **Valor da nota ≠ litros × custo** — erro de digitação ou maquiagem.
7. **Custo médio informado diferente do que as notas dão** — custo inflado
   esconde margem (e o dinheiro que ela representa).
8. **Venda abaixo do custo** — desconto não autorizado, venda a conhecido.
9. **Números redondos demais** — vendas "de cabeça", e não do encerrante.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from src import analytics as an
from src import auditoria
from src.formatting import format_brl, format_decimal, format_int, format_litros, format_pct_simples, format_rs_litro

SOBRA_ATENCAO = 0.5            # % do vendido
DIF_COMPRA_MIN_L = 500         # litros de diferença entre movimento e notas
DIF_VALOR_NOTA = 5.0           # R$ entre valor da nota e litros × custo (o custo vem com 4 casas)
DIF_CUSTO_MEDIO = 0.02         # R$/L em média nos dias de entrega
REDONDOS_PCT = 25.0            # % dos dias com venda múltipla de 100 L


@dataclass
class Sinal:
    nivel: str          # critico | atencao
    tipo: str
    posto: str
    titulo: str
    detalhe: str
    porque: str
    produto: str | None = None

    @property
    def icone(self) -> str:
        return "🔴" if self.nivel == "critico" else "🟡"


def _no_periodo(df: pd.DataFrame, inicio, fim, coluna="data") -> pd.DataFrame:
    d = pd.to_datetime(df[coluna])
    return df[(d >= pd.Timestamp(inicio)) & (d <= pd.Timestamp(fim))]


def sinal_alteracoes(aud: pd.DataFrame, postos: list[str]) -> list[Sinal]:
    saida = []
    sus = auditoria.suspeitas(aud)
    for posto in postos:
        g = sus[sus["posto"] == posto]
        if g.empty:
            continue
        dias = g["data"].dt.normalize().nunique()
        vendas = g[g["campo"] == "Vendas"]["diferenca"].sum()
        quem = ", ".join(sorted({u for u in g["usuario"] if u})) or "não identificado"
        nivel = "critico" if (g["gravidade"] == "critico").any() else "atencao"
        texto = f"{dias} dia(s) já recebido(s) alterado(s) depois · enviado por {quem}"
        if vendas < 0:
            texto += f" · vendas reduzidas em {format_int(-vendas)} L"
        saida.append(Sinal(nivel, "alteracao", posto, "Dados alterados depois de recebidos", texto,
                           "Baixar a venda de um dia antigo depois de informada é o jeito clássico de "
                           "esconder dinheiro que não entrou no caixa."))
    return saida


def sinal_lmc(df: pd.DataFrame, per: an.Periodo, postos: list[str]) -> list[Sinal]:
    saida = []
    for posto in postos:
        dp = df[df["posto"] == posto]
        if dp.empty:
            continue
        pp = an.periodo(dp, per.ano, per.mes)
        for _, r in an.perdas_lmc(df, pp, posto).iterrows():
            if r["perda_pct"] > an.TOLERANCIA_PERDA:
                saida.append(Sinal("critico", "perda", posto, "Perda no LMC acima da tolerância",
                                   f"{r['produto']}: {format_litros(-r['perda_l'])} a menos na régua "
                                   f"({format_pct_simples(r['perda_pct'], 2)} do vendido)",
                                   "Combustível que saiu do tanque sem venda registrada: vazamento, bomba "
                                   "descalibrada ou venda por fora.", str(r["produto"])))
            elif r["perda_pct"] < -SOBRA_ATENCAO:
                saida.append(Sinal("atencao", "sobra", posto, "Sobra no LMC acima do normal",
                                   f"{r['produto']}: {format_litros(r['perda_l'])} a mais na régua "
                                   f"({format_pct_simples(-r['perda_pct'], 2)} do vendido)",
                                   "Sobra grande e repetida sugere medição errada ou produto adulterado.",
                                   str(r["produto"])))
    return saida


def sinal_compras(df: pd.DataFrame, compras: pd.DataFrame, inicio, fim, postos: list[str]) -> list[Sinal]:
    """Cruza o que o movimento diz que entrou com as notas das distribuidoras."""
    saida = []
    if compras is None or compras.empty:
        return saida
    c = compras.copy()
    c["data"] = pd.to_datetime(c["data"]).dt.normalize()
    c["produto"] = c["produto"].astype(str)
    mov = _no_periodo(df, inicio, fim)
    mov = mov.assign(produto=mov["produto"].astype(str)).groupby(["posto", "data", "produto"])["compras_l"].sum()
    periodo = _no_periodo(c, inicio, fim)
    # A 2ª via de uma nota repetida vira o sinal "nota lançada duas vezes", e
    # não também "nota sem entrada no tanque" — um problema, um aviso.
    unicas = periodo[~periodo.duplicated(["posto", "nota_fiscal"], keep="first")]
    notas = unicas.groupby(["posto", "data", "produto"])["litros"].sum()
    juntos = pd.concat([mov.rename("tanque"), notas.rename("notas")], axis=1).fillna(0)
    juntos["dif"] = juntos["tanque"] - juntos["notas"]
    for (posto, data, produto), r in juntos[juntos["dif"].abs() >= DIF_COMPRA_MIN_L].iterrows():
        if posto not in postos:
            continue
        if r["dif"] > 0:
            saida.append(Sinal("critico", "sem_nota", posto, "Combustível recebido sem nota",
                               f"{produto} em {data:%d/%m}: {format_litros(r['tanque'])} entraram no tanque, "
                               f"notas somam {format_litros(r['notas'])}",
                               "Carga sem nota é compra por fora (sem imposto) ou desvio de outra carga.",
                               produto))
        else:
            saida.append(Sinal("atencao", "nota_sem_entrada", posto, "Nota sem entrada no tanque",
                               f"{produto} em {data:%d/%m}: notas de {format_litros(r['notas'])}, "
                               f"tanque recebeu {format_litros(r['tanque'])}",
                               "Nota lançada sem combustível no tanque: nota fria ou carga desviada.",
                               produto))
    for (posto, nf), g in periodo.groupby(["posto", "nota_fiscal"]):
        if len(g) > 1 and posto in postos:
            datas = ", ".join(pd.to_datetime(g["data"]).dt.strftime("%d/%m"))
            saida.append(Sinal("atencao", "nf_repetida", posto, "Nota fiscal lançada duas vezes",
                               f"NF {nf} aparece {len(g)} vezes ({datas}) · {format_litros(g['litros'].sum())}",
                               "Nota repetida infla o custo e as contas a pagar."))
    divergentes = periodo[(periodo["valor"] - periodo["litros"] * periodo["custo"]).abs() > DIF_VALOR_NOTA]
    for posto, g in divergentes.groupby("posto"):
        if posto in postos:
            saida.append(Sinal("atencao", "valor_nota", posto, "Valor de nota não bate com litros × custo",
                               f"{len(g)} nota(s) com diferença · maior: "
                               f"{format_brl((g['valor'] - g['litros'] * g['custo']).abs().max())}",
                               "Erro de digitação ou maquiagem do custo de compra."))
    return saida


def sinal_custo_informado(df: pd.DataFrame, compras: pd.DataFrame, inicio, fim, postos) -> list[Sinal]:
    """No dia da entrega, o custo médio informado deve ser a média ponderada do
    estoque com a carga nova. Muito longe disso, o custo foi 'ajustado'."""
    saida = []
    if compras is None or compras.empty:
        return saida
    c = compras.copy()
    c["data"] = pd.to_datetime(c["data"]).dt.normalize()
    c["produto"] = c["produto"].astype(str)
    custo_dia = c.groupby(["posto", "data", "produto"]).agg(litros=("litros", "sum"), valor=("valor", "sum"))
    mov = df.assign(produto=df["produto"].astype(str)).sort_values("data")
    for (posto, produto), g in mov.groupby(["posto", "produto"]):
        if posto not in postos:
            continue
        g = g.reset_index(drop=True)
        difs = []
        for i in range(1, len(g)):
            r, ant = g.iloc[i], g.iloc[i - 1]
            if not (pd.Timestamp(inicio) <= r["data"] <= pd.Timestamp(fim)) or r["compras_l"] <= 0:
                continue
            chave = (posto, r["data"], produto)
            if chave not in custo_dia.index:
                continue
            nota = custo_dia.loc[chave]
            esperado = ((r["estoque_inicial"] * ant["custo_medio"] + nota["valor"])
                        / (r["estoque_inicial"] + nota["litros"]))
            difs.append(r["custo_medio"] - esperado)
        if len(difs) >= 2 and abs(np.mean(difs)) > DIF_CUSTO_MEDIO:
            saida.append(Sinal("atencao", "custo_medio", posto, "Custo médio informado fora do que as notas dão",
                               f"{produto}: em média {format_rs_litro(abs(np.mean(difs)), 3)} "
                               f"{'acima' if np.mean(difs) > 0 else 'abaixo'} nos dias de entrega",
                               "Custo inflado faz a margem parecer menor — e esconde o dinheiro dela.", produto))
    return saida


def sinal_vendas(df: pd.DataFrame, inicio, fim, postos) -> list[Sinal]:
    saida = []
    p = _no_periodo(df, inicio, fim)
    for posto, g in p.groupby("posto"):
        if posto not in postos or len(g) < 20:
            continue
        abaixo = g[g["preco_medio"] < g["custo_medio"]]
        if len(abaixo):
            saida.append(Sinal("atencao", "abaixo_custo", posto, "Venda abaixo do custo",
                               f"{len(abaixo)} dia(s) com preço médio menor que o custo "
                               f"(ex.: {abaixo.iloc[0]['produto']} em {abaixo.iloc[0]['data']:%d/%m})",
                               "Desconto não autorizado ou venda a conhecido."))
        redondos = (g["vendas_l"] > 0) & (g["vendas_l"] % 100 == 0)
        pct = redondos.mean() * 100
        if pct >= REDONDOS_PCT:
            saida.append(Sinal("atencao", "redondos", posto, "Números redondos demais",
                               f"{format_pct_simples(pct, 0)} das vendas diárias terminam em 00 L",
                               "Venda digitada de cabeça, e não lida do encerrante da bomba."))
    return saida


def sinais(df: pd.DataFrame, compras: pd.DataFrame, aud: pd.DataFrame, postos: list[str],
           per: an.Periodo | None = None) -> list[Sinal]:
    """Todos os sinais, do mês em foco; crítico primeiro, depois por posto."""
    if df is None or df.empty:
        return []
    if per is None:
        ref = df["data"].max().date()
        per = an.periodo(df, ref.year, ref.month)
    inicio, fim = per.inicio, per.fim
    lista = (sinal_alteracoes(aud, postos) + sinal_lmc(df, per, postos)
             + sinal_compras(df, compras, inicio, fim, postos)
             + sinal_custo_informado(df, compras, inicio, fim, postos)
             + sinal_vendas(df, inicio, fim, postos))
    ordem = {p: i for i, p in enumerate(postos)}
    lista.sort(key=lambda s: (s.nivel != "critico", s.tipo != "alteracao", ordem.get(s.posto, 99)))
    return lista
