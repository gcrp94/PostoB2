"""As contas do painel — só calcula, não desenha nem lê Excel.

Vocabulário (e por que ele importa):

* **Margem bruta** = faturamento − custo do combustível vendido
  (litros × custo médio). É o que a planilha sustenta sozinha, e é o número
  principal de todas as telas. Nunca se escreve "lucro" para ele.
* **Margem por litro** = margem bruta ÷ litros. É a moeda do posto.
* **Perda/Sobra do LMC** = estoque final medido − (inicial + compras − vendas).
  Negativo é perda. Entra à parte, não dentro da margem bruta, para que a
  margem por litro continue sendo "preço − custo".
* **Resultado depois das despesas** = margem bruta − perdas − despesas
  lançadas. Só existe onde a aba DESPESAS foi preenchida; é antes de IR/CSLL.
* **Autonomia** = estoque de hoje ÷ média de venda diária dos últimos 7 dias.

Todo comparativo com o mês anterior usa os MESMOS DIAS: setembro até o dia 27
se compara com agosto até o dia 27 — mês incompleto contra mês fechado
pareceria queda (lição do Painel de Finanças).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.theme import COMBUSTIVEIS

DIAS_MEDIA_AUTONOMIA = 7
AUTONOMIA_CRITICA = 1.5          # dias
AUTONOMIA_ATENCAO = 2.5
TOLERANCIA_PERDA = 0.6           # % do vendido — referência usual do LMC
ALERTA_PERDA = 0.4


# ------------------------------------------------------------------ base ---
MODOS_CUSTO = {"planilha": "Preço planilha", "sistema": "Preço sistema"}


def preparar(mov: pd.DataFrame, compras: pd.DataFrame | None = None, descontos: pd.DataFrame | None = None,
             custo: str = "planilha") -> pd.DataFrame:
    """As colunas de conta (faturamento, CMV, margem, perda).

    `custo` escolhe QUAL custo entra na conta: "planilha" (o que o posto paga, já com o desconto do boleto — o
    `custo_medio` enviado) ou "sistema" (o preço cheio da nota: planilha + desconto). Sem `compras` e `descontos` os dois
    são iguais. `custo_planilha`, `desconto_litro` e `custo_sistema` ficam sempre na tabela, qualquer que seja o modo.
    """
    from src import descontos as desc

    if custo not in MODOS_CUSTO:
        raise ValueError(f"custo deve ser um de {list(MODOS_CUSTO)}")
    df = mov.copy()
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    df["custo_planilha"] = df["custo_medio"]
    df["desconto_litro"] = desc.desconto_diario(df, compras, descontos)
    df["custo_sistema"] = df["custo_planilha"] + df["desconto_litro"]
    if custo == "sistema":
        df["custo_medio"] = df["custo_sistema"]
    df["faturamento"] = df["vendas_l"] * df["preco_medio"]
    df["cmv"] = df["vendas_l"] * df["custo_medio"]
    df["margem"] = df["faturamento"] - df["cmv"]
    df["escritural"] = df["estoque_inicial"] + df["compras_l"] - df["vendas_l"]
    df["perda_l"] = df["estoque_final"] - df["escritural"]
    df["perda_rs"] = df["perda_l"] * df["custo_medio"]
    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    df["produto"] = pd.Categorical(df["produto"], categories=COMBUSTIVEIS, ordered=True)
    return df


@dataclass(frozen=True)
class Periodo:
    ano: int
    mes: int
    inicio: date
    fim: date                    # último dia COM dado dentro do mês
    parcial: bool
    anterior_inicio: date
    anterior_fim: date

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1


def meses_disponiveis(df: pd.DataFrame) -> list[tuple[int, int]]:
    pares = df[["ano", "mes"]].drop_duplicates().sort_values(["ano", "mes"])
    return [tuple(map(int, x)) for x in pares.values]


def periodo(df: pd.DataFrame, ano: int, mes: int) -> Periodo:
    do_mes = df[(df["ano"] == ano) & (df["mes"] == mes)]
    inicio = date(ano, mes, 1)
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fim = do_mes["data"].max().date() if len(do_mes) else date(ano, mes, ultimo_dia)
    parcial = fim.day < ultimo_dia
    a_ano, a_mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    a_ultimo = calendar.monthrange(a_ano, a_mes)[1]
    a_fim = date(a_ano, a_mes, min(fim.day, a_ultimo) if parcial else a_ultimo)
    return Periodo(ano, mes, inicio, fim, parcial, date(a_ano, a_mes, 1), a_fim)


def recorte(df: pd.DataFrame, inicio: date, fim: date, postos=None) -> pd.DataFrame:
    m = (df["data"] >= pd.Timestamp(inicio)) & (df["data"] <= pd.Timestamp(fim))
    if postos is not None:
        m &= df["posto"].isin([postos] if isinstance(postos, str) else postos)
    return df[m]


# ------------------------------------------------------------ indicadores ---
def _somas(g: pd.DataFrame) -> dict:
    litros = float(g["vendas_l"].sum())
    fat = float(g["faturamento"].sum())
    margem = float(g["margem"].sum())
    cmv = float(g["cmv"].sum())
    perda_l = float(g["perda_l"].sum())
    return {
        "litros": litros,
        "faturamento": fat,
        "cmv": cmv,
        "margem": margem,
        "margem_pct": margem / fat * 100 if fat else np.nan,
        "margem_litro": margem / litros if litros else np.nan,
        "preco_medio": fat / litros if litros else np.nan,
        "custo_medio": cmv / litros if litros else np.nan,
        "compras_l": float(g["compras_l"].sum()),
        "perda_l": perda_l,
        "perda_rs": float(g["perda_rs"].sum()),
        "perda_pct": -perda_l / litros * 100 if litros else np.nan,
        "dias": int(g["data"].nunique()),
    }


def _lista_postos(df: pd.DataFrame, postos) -> list[str]:
    if postos is None:
        return list(df["posto"].unique())
    return [postos] if isinstance(postos, str) else list(postos)


def fatias(df: pd.DataFrame, per: Periodo, postos=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """O mês atual e o mesmo trecho do mês anterior, POSTO A POSTO.

    Cada posto envia a planilha num dia: se a Primavera parou no dia 24, o
    agosto dela se compara até o dia 24 — e não até o 27 dos outros, o que
    faria o atraso do envio parecer queda de venda.
    """
    atuais, anteriores = [], []
    for posto in _lista_postos(df, postos):
        dp = df[df["posto"] == posto]
        if dp.empty:
            continue
        pp = periodo(dp, per.ano, per.mes)
        atuais.append(recorte(dp, pp.inicio, pp.fim))
        anteriores.append(recorte(dp, pp.anterior_inicio, pp.anterior_fim))
    vazio = df.iloc[0:0]
    return (pd.concat(atuais) if atuais else vazio, pd.concat(anteriores) if anteriores else vazio)


def ultima_data(df: pd.DataFrame, posto: str | None = None) -> date:
    g = df if posto is None else df[df["posto"] == posto]
    return g["data"].max().date()


def indicadores(df: pd.DataFrame, per: Periodo, postos=None) -> dict:
    atual_df, ant_df = fatias(df, per, postos)
    atual = _somas(atual_df)
    atual["anterior"] = _somas(ant_df)
    return atual


def por_combustivel(df: pd.DataFrame, per: Periodo, postos=None) -> pd.DataFrame:
    atual, ant = fatias(df, per, postos)
    linhas = []
    total_l = atual["vendas_l"].sum()
    for p in COMBUSTIVEIS:
        s = _somas(atual[atual["produto"] == p])
        a = _somas(ant[ant["produto"] == p])
        s.update(produto=p, participacao=s["litros"] / total_l * 100 if total_l else np.nan,
                 litros_ant=a["litros"], margem_litro_ant=a["margem_litro"],
                 margem_pct_ant=a["margem_pct"])
        linhas.append(s)
    return pd.DataFrame(linhas)


def por_posto(df: pd.DataFrame, per: Periodo, postos_ordem: list[str]) -> pd.DataFrame:
    linhas = []
    for posto in postos_ordem:
        s = indicadores(df, per, posto)
        a = s.pop("anterior")
        s.update(posto=posto, litros_ant=a["litros"], faturamento_ant=a["faturamento"],
                 margem_ant=a["margem"], margem_pct_ant=a["margem_pct"],
                 margem_litro_ant=a["margem_litro"])
        linhas.append(s)
    return pd.DataFrame(linhas)


def media_12_meses(df: pd.DataFrame, per: Periodo, posto=None) -> dict:
    """Margem dos 12 meses FECHADOS antes do período (a régua do 'normal')."""
    fim = per.inicio - timedelta(days=1)
    inicio = (pd.Timestamp(per.inicio) - pd.DateOffset(months=12)).date()
    s = _somas(recorte(df, inicio, fim, posto))
    return {"margem_pct": s["margem_pct"], "margem_litro": s["margem_litro"],
            "meses": recorte(df, inicio, fim, posto)[["ano", "mes"]].drop_duplicates().shape[0]}


# ---------------------------------------------------------------- estoque ---
def estoque_atual(df: pd.DataFrame, tanques: pd.DataFrame, data_ref: date | None = None,
                  postos=None) -> pd.DataFrame:
    """A última medição de cada tanque (até `data_ref`) e quantos dias ela cobre."""
    partes = []
    for posto in _lista_postos(df, postos):
        dp = df[df["posto"] == posto]
        if data_ref is not None:
            dp = dp[dp["data"] <= pd.Timestamp(data_ref)]
        if dp.empty:
            continue
        ref = dp["data"].max().date()
        base = recorte(dp, ref - timedelta(days=DIAS_MEDIA_AUTONOMIA - 1), ref)
        hoje = base[base["data"] == pd.Timestamp(ref)][["posto", "produto", "estoque_final", "data"]]
        media = base.groupby(["posto", "produto"], observed=True)["vendas_l"].mean().rename("media_dia")
        partes.append(hoje.merge(media.reset_index(), on=["posto", "produto"], how="left"))
    if not partes:
        return pd.DataFrame(columns=["posto", "produto", "estoque", "data", "media_dia", "capacidade",
                                     "pct", "autonomia", "status"])
    t = pd.concat(partes, ignore_index=True)
    t["produto"] = t["produto"].astype(str)
    t = t.merge(tanques, on=["posto", "produto"], how="left")
    t = t.rename(columns={"estoque_final": "estoque"})
    t["pct"] = t["estoque"] / t["capacidade"] * 100
    t["autonomia"] = t["estoque"] / t["media_dia"].replace(0, np.nan)
    t["status"] = np.select(
        [t["autonomia"] < AUTONOMIA_CRITICA, t["autonomia"] < AUTONOMIA_ATENCAO],
        ["critico", "atencao"], default="ok")
    t["produto"] = pd.Categorical(t["produto"], categories=COMBUSTIVEIS, ordered=True)
    return t.sort_values(["posto", "produto"]).reset_index(drop=True)


def serie_estoque(df: pd.DataFrame, tanques: pd.DataFrame, inicio: date, fim: date, posto: str) -> pd.DataFrame:
    g = recorte(df, inicio, fim, posto)[["data", "produto", "estoque_final", "vendas_l", "compras_l"]]
    g = g.merge(tanques[tanques["posto"] == posto][["produto", "capacidade"]], on="produto", how="left")
    g["pct"] = g["estoque_final"] / g["capacidade"] * 100
    return g


# ----------------------------------------------------------------- séries ---
def serie_mensal(df: pd.DataFrame, postos=None, por_produto: bool = False) -> pd.DataFrame:
    g = df if postos is None else df[df["posto"].isin([postos] if isinstance(postos, str) else postos)]
    chaves = ["ano", "mes", "produto"] if por_produto else ["ano", "mes"]
    s = g.groupby(chaves, observed=True).agg(
        litros=("vendas_l", "sum"), faturamento=("faturamento", "sum"), margem=("margem", "sum"),
        cmv=("cmv", "sum"), perda_l=("perda_l", "sum"), dias=("data", "nunique")).reset_index()
    s["margem_pct"] = s["margem"] / s["faturamento"] * 100
    s["margem_litro"] = s["margem"] / s["litros"]
    s["preco_medio"] = s["faturamento"] / s["litros"]
    s["custo_medio"] = s["cmv"] / s["litros"]
    s["litros_dia"] = s["litros"] / s["dias"]
    return s


def serie_diaria(df: pd.DataFrame, inicio: date, fim: date, postos=None, por_produto: bool = True) -> pd.DataFrame:
    g = recorte(df, inicio, fim, postos)
    chaves = ["data", "produto"] if por_produto else ["data"]
    s = g.groupby(chaves, observed=True).agg(
        litros=("vendas_l", "sum"), faturamento=("faturamento", "sum"), margem=("margem", "sum"),
        cmv=("cmv", "sum")).reset_index()
    s["preco_medio"] = s["faturamento"] / s["litros"]
    s["custo_medio"] = s["cmv"] / s["litros"]
    s["margem_litro"] = s["margem"] / s["litros"]
    return s


# --------------------------------------------------- compras e despesas ---
def compras_periodo(compras: pd.DataFrame, per: Periodo, posto: str) -> pd.DataFrame:
    if compras.empty:
        return compras
    c = compras.copy()
    c["data"] = pd.to_datetime(c["data"])
    m = (c["posto"] == posto) & (c["data"] >= pd.Timestamp(per.inicio)) & (c["data"] <= pd.Timestamp(per.fim))
    c = c[m].copy()
    c["produto"] = pd.Categorical(c["produto"], categories=COMBUSTIVEIS, ordered=True)
    return c.sort_values(["data", "produto"])


def custo_por_distribuidora(compras: pd.DataFrame, inicio: date, fim: date, posto=None) -> pd.DataFrame:
    """Custo médio ponderado por distribuidora e produto — onde comprar mais barato."""
    if compras.empty:
        return compras
    c = compras.copy()
    c["data"] = pd.to_datetime(c["data"])
    m = (c["data"] >= pd.Timestamp(inicio)) & (c["data"] <= pd.Timestamp(fim))
    if posto:
        m &= c["posto"] == posto
    g = c[m].groupby(["produto", "distribuidora"]).agg(
        litros=("litros", "sum"), valor=("valor", "sum"), notas=("nota_fiscal", "count")).reset_index()
    g["custo"] = g["valor"] / g["litros"]
    g["produto"] = pd.Categorical(g["produto"], categories=COMBUSTIVEIS, ordered=True)
    return g.sort_values(["produto", "custo"])


def despesas_periodo(despesas: pd.DataFrame, inicio: date, fim: date, posto=None) -> pd.DataFrame:
    if despesas.empty:
        return despesas
    d = despesas.copy()
    d["data"] = pd.to_datetime(d["data"])
    m = (d["data"] >= pd.Timestamp(inicio)) & (d["data"] <= pd.Timestamp(fim))
    if posto:
        m &= d["posto"].isin([posto] if isinstance(posto, str) else posto)
    return d[m]


def resultado(df: pd.DataFrame, despesas: pd.DataFrame, per: Periodo, posto=None) -> dict:
    """Margem bruta → perdas → despesas → resultado (antes de IR/CSLL)."""
    ind = indicadores(df, per, posto)
    atuais, anteriores = [], []
    for p in _lista_postos(df, posto):
        pp = periodo(df[df["posto"] == p], per.ano, per.mes)
        atuais.append(despesas_periodo(despesas, pp.inicio, pp.fim, p))
        anteriores.append(despesas_periodo(despesas, pp.anterior_inicio, pp.anterior_fim, p))
    d = pd.concat(atuais) if atuais else despesas.iloc[0:0]
    d_ant = pd.concat(anteriores) if anteriores else despesas.iloc[0:0]
    por_cat = (d.groupby("categoria")["valor"].sum().sort_values(ascending=False)
               if len(d) else pd.Series(dtype=float))
    total_desp = float(por_cat.sum())
    res = ind["margem"] + ind["perda_rs"] - total_desp
    ant = ind["anterior"]
    res_ant = ant["margem"] + ant["perda_rs"] - float(d_ant["valor"].sum() if len(d_ant) else 0)
    return {
        "faturamento": ind["faturamento"], "margem": ind["margem"], "perda_rs": ind["perda_rs"],
        "despesas": total_desp, "por_categoria": por_cat, "resultado": res,
        "resultado_pct": res / ind["faturamento"] * 100 if ind["faturamento"] else np.nan,
        "resultado_ant": res_ant, "tem_despesas": len(d) > 0,
    }


def serie_resultado_mensal(df: pd.DataFrame, despesas: pd.DataFrame, posto=None) -> pd.DataFrame:
    s = serie_mensal(df, posto)
    perdas = (df if posto is None else df[df["posto"] == posto]).groupby(["ano", "mes"])["perda_rs"].sum()
    s = s.merge(perdas.reset_index(), on=["ano", "mes"], how="left")
    if len(despesas):
        d = despesas if posto is None else despesas[despesas["posto"] == posto]
        d = d.assign(ano=pd.to_datetime(d["data"]).dt.year, mes=pd.to_datetime(d["data"]).dt.month)
        s = s.merge(d.groupby(["ano", "mes"])["valor"].sum().rename("despesas").reset_index(),
                    on=["ano", "mes"], how="left")
    else:
        s["despesas"] = 0.0
    s["despesas"] = s["despesas"].fillna(0)
    s["resultado"] = s["margem"] + s["perda_rs"] - s["despesas"]
    s["resultado_pct"] = s["resultado"] / s["faturamento"] * 100
    return s


# ----------------------------------------------------- ponto de equilíbrio ---
EQ_MESES_HISTORICO = 6          # quantos meses fechados entram na "média do posto"
EQ_JANELA_RITMO = 7             # dias usados para projetar quando o equilíbrio chega
EQ_MESES_CUSTO = 3              # mês em andamento: custo estimado = média dos últimos 3 meses fechados


def _ganho_diario(dp: pd.DataFrame, inicio: date, fim: date) -> pd.Series:
    """O que sobra por dia ANTES das despesas: margem bruta + perda/sobra do LMC (a mesma base do resultado).

    Dia sem dado vale zero: o acumulado não "pula" um dia.
    """
    g = recorte(dp, inicio, fim)
    por_dia = g.groupby("data")[["margem", "perda_rs"]].sum().sum(axis=1)
    return por_dia.reindex(pd.date_range(inicio, fim, freq="D"), fill_value=0.0)


def _despesas_do_mes(despesas: pd.DataFrame, posto: str, ano: int, mes: int) -> float:
    if despesas.empty:
        return 0.0
    ultimo = calendar.monthrange(ano, mes)[1]
    d = despesas_periodo(despesas, date(ano, mes, 1), date(ano, mes, ultimo), posto)
    return float(d["valor"].sum()) if len(d) else 0.0


def equilibrio_mes(df: pd.DataFrame, despesas: pd.DataFrame, posto: str, ano: int, mes: int) -> dict:
    """O ponto de equilíbrio de UM posto em UM mês: o dia em que o acumulado cobriu os custos do mês.

    * **Acumulado** = soma diária de (margem bruta + perda/sobra), do dia 1 em diante.
    * **Custos do mês** = as despesas lançadas. Mês em andamento: o maior entre o já lançado e a média dos
      últimos meses fechados (aluguel e folha podem ainda não ter caído) — e o resultado diz que é estimativa.
    * **Dia do equilíbrio** = o 1º dia em que o acumulado ≥ custos. Dali em diante, cada real é resultado
      (antes de IR/CSLL).
    * Não atingiu: **quanto falta** em R$ e **em quantos dias**, no ritmo dos últimos 7 dias.
    """
    dp = df[df["posto"] == posto]
    do_mes = dp[(dp["ano"] == ano) & (dp["mes"] == mes)]
    if do_mes.empty:
        return {"disponivel": False, "motivo": "sem vendas neste mês"}
    per = periodo(dp, ano, mes)
    dias_mes = calendar.monthrange(ano, mes)[1]

    lancado = _despesas_do_mes(despesas, posto, ano, mes)
    anteriores = [(a, m) for a, m in meses_disponiveis(dp) if (a, m) < (ano, mes)]
    medias = [v for v in (_despesas_do_mes(despesas, posto, a, m) for a, m in anteriores[-EQ_MESES_CUSTO:]) if v > 0]
    media_custos = float(np.mean(medias)) if medias else 0.0
    custos = max(lancado, media_custos) if per.parcial else lancado
    if custos <= 0:
        return {"disponivel": False, "motivo": "sem despesas lançadas (aba DESPESAS)"}

    ganho = _ganho_diario(dp, per.inicio, per.fim)
    acum = ganho.cumsum()
    atingiu = acum >= custos
    dia_eq = int(atingiu.idxmax().day) if bool(atingiu.any()) else None
    litros = float(recorte(dp, per.inicio, per.fim)["vendas_l"].sum())
    total = float(acum.iloc[-1])
    margem_litro = total / litros if litros else np.nan
    litros_eq_mes = custos / margem_litro if margem_litro and margem_litro > 0 else None

    out = {
        "disponivel": True, "posto": posto, "ano": ano, "mes": mes, "parcial": per.parcial,
        "dia_final": per.fim.day, "dias_mes": dias_mes,
        "custos": custos, "custos_lancados": lancado, "custos_estimados": per.parcial and custos > lancado,
        "acumulado": total, "pct_coberto": total / custos * 100,
        "dia_equilibrio": dia_eq, "falta": max(custos - total, 0.0), "resultado_ate_agora": total - custos,
        "ritmo": None, "dias_faltam": None, "previsto_dia": None, "fecha_no_mes": None,
        "dias_acima": None, "litros": litros, "litros_equilibrio_mes": litros_eq_mes,
        "litros_dia_equilibrio": litros_eq_mes / dias_mes if litros_eq_mes else None,
        "litros_dia_atual": litros / per.dias if per.dias else None,
        "margem_litro": margem_litro,
        "curva": pd.Series(acum.values, index=acum.index.day, name="acumulado"),
    }
    if dia_eq is not None:
        out["dias_acima"] = per.fim.day - dia_eq
    elif per.parcial:
        ritmo = float(ganho.tail(EQ_JANELA_RITMO).mean())
        out["ritmo"] = ritmo
        if ritmo > 0:
            out["dias_faltam"] = int(np.ceil(out["falta"] / ritmo))
            out["previsto_dia"] = per.fim.day + out["dias_faltam"]
            out["fecha_no_mes"] = out["previsto_dia"] <= dias_mes
        else:
            out["fecha_no_mes"] = False
    return out


def equilibrio(df: pd.DataFrame, despesas: pd.DataFrame, posto: str, ano: int, mes: int) -> dict:
    """`equilibrio_mes` + "como está em relação às médias": os últimos meses do próprio posto e a rede no mesmo mês."""
    eq = equilibrio_mes(df, despesas, posto, ano, mes)
    if not eq["disponivel"]:
        return eq
    dp = df[df["posto"] == posto]
    anteriores = [(a, m) for a, m in meses_disponiveis(dp) if (a, m) < (ano, mes)][-EQ_MESES_HISTORICO:]
    hist = [h for h in (equilibrio_mes(df, despesas, posto, a, m) for a, m in anteriores)
            if h["disponivel"] and not h["parcial"]]
    dias = [h["dia_equilibrio"] for h in hist if h["dia_equilibrio"] is not None]
    curvas = [h["curva"] for h in hist]
    eq["historico"] = {
        "meses": [(h["ano"], h["mes"], h["dia_equilibrio"]) for h in hist], "n": len(hist), "n_cobriu": len(dias),
        "media_dia": float(np.mean(dias)) if dias else None,
        "curva_media": (pd.concat(curvas, axis=1).mean(axis=1).rename("media") if curvas else None),
    }
    rede = {}
    for p in df["posto"].unique():
        e = eq if p == posto else equilibrio_mes(df, despesas, p, ano, mes)
        if not e["disponivel"]:
            continue
        dia = e["dia_equilibrio"] if e["dia_equilibrio"] is not None else e["previsto_dia"]
        rede[p] = {"dia": dia, "cobriu": e["dia_equilibrio"] is not None,
                   "previsto": e["dia_equilibrio"] is None and e["previsto_dia"] is not None,
                   "pct_coberto": e["pct_coberto"]}
    dias_rede = [v["dia"] for v in rede.values() if v["dia"] is not None]
    eq["rede"] = {"postos": rede, "media_dia": float(np.mean(dias_rede)) if dias_rede else None}
    return eq


def perdas_lmc(df: pd.DataFrame, per: Periodo, posto: str) -> pd.DataFrame:
    g = recorte(df, per.inicio, per.fim, posto)
    t = g.groupby("produto", observed=True).agg(
        vendido=("vendas_l", "sum"), perda_l=("perda_l", "sum"), perda_rs=("perda_rs", "sum")).reset_index()
    t["perda_pct"] = -t["perda_l"] / t["vendido"] * 100
    t["status"] = np.select([t["perda_pct"] > TOLERANCIA_PERDA, t["perda_pct"] > ALERTA_PERDA],
                            ["critico", "atencao"], default="ok")
    return t


def media_dia_semana(df: pd.DataFrame, fim: date, semanas: int, posto=None) -> pd.DataFrame:
    inicio = fim - timedelta(days=7 * semanas - 1)
    g = recorte(df, inicio, fim, posto).groupby("data")["vendas_l"].sum().reset_index()
    g["dia"] = g["data"].dt.weekday
    return g.groupby("dia")["vendas_l"].mean().reindex(range(7)).reset_index()
