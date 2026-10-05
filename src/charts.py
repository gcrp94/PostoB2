"""Gráficos Plotly — limpos, em português, e sempre com a mesma gramática.

* marcas finas, grade quase invisível, sem eixo duplo;
* cor do combustível é identidade (a mesma em todo lugar); o azul-marinho é
  a cor de "série única"; o laranja da marca só marca o período em foco;
* rótulo de valor SELETIVO: nas barras de poucos itens, sim; em série longa,
  só o ponto em foco — o resto fica no hover;
* todo texto de número é montado em Python (`formatting`) e passado por
  `customdata`/`text`: o Plotly sozinho escreve "6.39" e "1.2M".
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src import theme
from src.formatting import (
    format_brl, format_brl_curto, format_decimal, format_litros, format_litros_curto,
    format_pct_simples, format_rs_litro, nome_mes,
)

C = theme.COLORS
CFG = {"displayModeBar": False, "responsive": True, "locale": "pt-BR"}
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
NOVO = False        # o app.py liga no "Painel novo": grade pontilhada, dica escura, barras arredondadas


def _base(fig: go.Figure, altura: int = 300, legenda: bool = False) -> go.Figure:
    fig.update_layout(
        height=altura, margin=dict(l=4, r=8, t=8 if not legenda else 34, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=theme.FONTE_FAMILIA, size=12, color=C["text_secondary"]),
        separators=",.", hovermode="closest", bargap=0.28,
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=C["border"],
                        font=dict(family=theme.FONTE_FAMILIA, size=12, color=C["text_primary"])),
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(size=11.5, color=C["text_secondary"]), itemclick="toggleothers",
                    traceorder="normal"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=C["border"], ticks="",
                     tickfont=dict(size=11.5, color=C["text_secondary"]), fixedrange=True, tickangle=0)
    fig.update_yaxes(showgrid=True, gridcolor=C["grid"], gridwidth=1, zeroline=False, ticks="",
                     tickfont=dict(size=11, color=C["text_muted"]), fixedrange=True)
    if NOVO:
        fig.update_layout(
            barcornerradius=6,
            hoverlabel=dict(bgcolor="#0b1646", bordercolor="#0b1646",
                            font=dict(family=theme.FONTE_FAMILIA, size=12, color="#ffffff")))
        fig.update_yaxes(gridcolor="#e9edf5", griddash="dot")
        fig.update_xaxes(linecolor="rgba(0,0,0,0)")
    return fig


def _eixo_reais(fig: go.Figure, valores, eixo: str = "y"):
    """Ticks em "R$ 2,5 mi" em vez de "2.5M" (M em contabilidade é MILHAR)."""
    maximo = float(np.nanmax(np.abs(valores))) if len(valores) else 0
    if maximo <= 0:
        return
    passo = _passo(maximo)
    ticks = np.arange(0, maximo * 1.15 + passo, passo)
    textos = [format_brl_curto(t) if t else "0" for t in ticks]
    getattr(fig, f"update_{eixo}axes")(tickvals=ticks, ticktext=textos)


def _eixo_litros(fig: go.Figure, valores, eixo: str = "y"):
    maximo = float(np.nanmax(np.abs(valores))) if len(valores) else 0
    if maximo <= 0:
        return
    passo = _passo(maximo)
    ticks = np.arange(0, maximo * 1.15 + passo, passo)
    textos = [format_litros_curto(t) if t else "0" for t in ticks]
    getattr(fig, f"update_{eixo}axes")(tickvals=ticks, ticktext=textos)


def _passo(maximo: float) -> float:
    bruto = maximo / 4
    potencia = 10 ** np.floor(np.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        if bruto <= m * potencia:
            return m * potencia
    return 10 * potencia


def rotulos_meses(pares, parcial: tuple[int, int] | None = None) -> list[str]:
    """Eixo de 12 meses que cabe no celular: o ano só no primeiro mês e em
    janeiro ("out/25 nov dez jan/26 fev..."); o mês em andamento leva "*"."""
    saida = []
    for i, (a, m) in enumerate(pares):
        a, m = int(a), int(m)
        r = nome_mes(m, a, curto=True) if (i == 0 or m == 1) else nome_mes(m, curto=True)
        saida.append(r + ("*" if parcial == (a, m) else ""))
    return saida


# ------------------------------------------------------- por combustível ---
def barras_combustivel(df: pd.DataFrame, coluna: str, formato: str, altura: int = 260) -> go.Figure:
    """4 barras, uma por combustível, na cor dele, com o valor em cima."""
    fmt = {"litros": format_litros, "brl": lambda v: format_brl_curto(v),
           "rs_litro": format_rs_litro, "pct": lambda v: format_pct_simples(v, 1)}[formato]
    d = df.copy()
    rotulos = [f"{theme.ICONES_COMBUSTIVEL[p]}<br>{theme.ROTULO_CURTO[p]}" for p in d["produto"]]
    textos = [fmt(v) for v in d[coluna]]
    fig = go.Figure(go.Bar(
        x=rotulos, y=d[coluna], marker=dict(color=[theme.CORES_COMBUSTIVEL[p] for p in d["produto"]],
                                             cornerradius=6),
        text=textos, textposition="outside", cliponaxis=False, constraintext="none",
        textfont=dict(size=12.5, color=C["text_primary"], family=theme.FONTE_FAMILIA),
        customdata=[[p, t] for p, t in zip(d["produto"], textos)],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    ))
    _base(fig, altura)
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, float(d[coluna].max()) * 1.22])
    fig.update_xaxes(automargin=True, tickfont=dict(size=11.5, color=C["text_primary"]))
    fig.update_layout(bargap=0.38, margin=dict(b=10))
    return fig


# ------------------------------------------------------------ por posto ----
def barras_postos(df: pd.DataFrame, coluna: str, texto_col: str, altura: int = 250,
                  destaque: str | None = None) -> go.Figure:
    """Barras deitadas, ordenadas; a cor única é o azul da marca."""
    d = df.sort_values(coluna)
    cores = [C["orange"] if p == destaque else C["navy_ui"] for p in d["posto"]]
    fig = go.Figure(go.Bar(
        y=d["posto"], x=d[coluna], orientation="h", marker=dict(color=cores, cornerradius=5),
        text=d[texto_col], textposition="outside", cliponaxis=False, constraintext="none",
        textfont=dict(size=12, color=C["text_primary"]),
        customdata=d[[texto_col]].values,
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<extra></extra>",
    ))
    _base(fig, altura)
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, float(d[coluna].max()) * 1.45])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12.5, color=C["text_primary"]))
    fig.update_layout(bargap=0.35)
    return fig


def halteres_margem(df: pd.DataFrame, altura: int = 250) -> go.Figure:
    """Margem por litro: média dos 12 meses (cinza) × mês atual (cor da
    situação). A linha entre os dois É a variação — sem eixo duplo."""
    d = df.sort_values("posto", key=lambda s: s.map({p: i for i, p in enumerate(theme.POSTOS)}),
                       ascending=False)
    fig = go.Figure()
    for _, r in d.iterrows():
        fig.add_trace(go.Scatter(x=[r["hist"], r["atual"]], y=[r["posto"]] * 2, mode="lines",
                                 line=dict(color="#cfd6e4", width=3), hoverinfo="skip", showlegend=False))
    dif = d["atual"] - d["hist"]
    cores = [C["critico"] if v < -0.03 else (C["ok"] if v > 0.03 else C["navy_ui"]) for v in dif]
    fig.add_trace(go.Scatter(
        x=d["hist"], y=d["posto"], mode="markers", name="Média 12 meses",
        marker=dict(size=12, color="#aab4c8", line=dict(color="#ffffff", width=2)),
        customdata=[format_rs_litro(v) for v in d["hist"]],
        hovertemplate="<b>%{y}</b><br>Média 12 meses: %{customdata}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["atual"], y=d["posto"], mode="markers", name="Mês atual",
        marker=dict(size=15, color=cores, line=dict(color="#ffffff", width=2)),
        customdata=[format_rs_litro(v) for v in d["atual"]],
        hovertemplate="<b>%{y}</b><br>Mês atual: %{customdata}<extra></extra>"))
    _base(fig, altura, legenda=True)
    lo = float(min(d["hist"].min(), d["atual"].min()))
    hi = float(max(d["hist"].max(), d["atual"].max()))
    # Valor e variação numa coluna própria à direita — nunca em cima dos pontos
    # (rótulo ao lado da marca colide justamente quando os números se aproximam).
    col_x = hi + 0.05
    for (_, r), v, cor in zip(d.iterrows(), dif, cores):
        centavos = v * 100
        var_txt = (f"  {'+' if centavos > 0 else '−'}{format_decimal(abs(centavos), 0)} ¢"
                   if abs(centavos) >= 0.5 else "  =")
        fig.add_annotation(x=col_x, y=r["posto"], xanchor="left", showarrow=False,
                           text=f"<b>{format_rs_litro(r['atual'])}</b><span style='color:{cor}'>{var_txt}</span>",
                           font=dict(size=12, color=C["text_primary"]))
    passo = 0.1 if hi - lo > 0.25 else 0.05
    ticks = np.round(np.arange(np.floor(lo / passo) * passo, hi + 0.001, passo), 2)
    fig.update_xaxes(range=[lo - 0.04, hi + 0.21], tickvals=ticks, ticktext=[format_brl(t) for t in ticks],
                     showgrid=True, gridcolor=C["grid"], tickangle=0)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12.5, color=C["text_primary"]))
    return fig


# ---------------------------------------------------------------- mensal ---
def mensal_barras(s: pd.DataFrame, coluna: str, formato: str, foco: tuple[int, int] | None = None,
                  parcial: tuple[int, int] | None = None, altura: int = 250) -> go.Figure:
    fmt = {"litros": format_litros_curto, "brl": format_brl_curto,
           "pct": lambda v: format_pct_simples(v, 1), "rs_litro": format_rs_litro}[formato]
    rot = rotulos_meses(zip(s["ano"], s["mes"]), parcial)
    em_foco = [(a, m) == foco for a, m in zip(s["ano"], s["mes"])]
    cores = [C["navy_ui"] if f else "#c9d1e3" for f in em_foco]
    textos = [fmt(v) if f else "" for v, f in zip(s[coluna], em_foco)]
    fig = go.Figure(go.Bar(
        x=rot, y=s[coluna], marker=dict(color=cores, cornerradius=4), text=textos,
        textposition="outside", cliponaxis=False, constraintext="none", textfont=dict(size=12, color=C["text_primary"]),
        customdata=[fmt(v) for v in s[coluna]],
        hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>"))
    _base(fig, altura)
    if formato == "brl":
        _eixo_reais(fig, s[coluna])
    elif formato == "litros":
        _eixo_litros(fig, s[coluna])
    fig.update_yaxes(range=[0, float(s[coluna].max()) * 1.18])
    return fig


def mensal_empilhado(s: pd.DataFrame, parcial: tuple[int, int] | None = None, altura: int = 290) -> go.Figure:
    fig = go.Figure()
    meses = s[["ano", "mes"]].drop_duplicates().sort_values(["ano", "mes"])
    rot = dict(zip(map(tuple, meses.values), rotulos_meses(meses.values, parcial)))
    for p in theme.COMBUSTIVEIS:
        g = s[s["produto"] == p]
        fig.add_trace(go.Bar(
            x=[rot[(a, m)] for a, m in zip(g["ano"], g["mes"])], y=g["litros"], name=theme.ROTULO_CURTO[p],
            marker=dict(color=theme.CORES_COMBUSTIVEL[p], line=dict(color="#ffffff", width=1.5)),
            customdata=[format_litros(v) for v in g["litros"]],
            hovertemplate=f"<b>{p}</b><br>%{{x}}: %{{customdata}}<extra></extra>"))
    _base(fig, altura, legenda=True)
    fig.update_layout(barmode="stack", bargap=0.3)
    tot = s.groupby(["ano", "mes"])["litros"].sum()
    _eixo_litros(fig, tot.values)
    return fig


def mensal_linhas_combustivel(s: pd.DataFrame, coluna: str, formato: str, altura: int = 290) -> go.Figure:
    fmt = {"rs_litro": format_rs_litro, "brl": format_brl, "pct": lambda v: format_pct_simples(v, 1)}[formato]
    fig = go.Figure()
    for p in theme.COMBUSTIVEIS:
        g = s[s["produto"] == p]
        x = rotulos_meses(zip(g["ano"], g["mes"]))
        fig.add_trace(go.Scatter(
            x=x, y=g[coluna], name=theme.ROTULO_CURTO[p], mode="lines+markers",
            line=dict(color=theme.CORES_COMBUSTIVEL[p], width=2.4),
            marker=dict(size=7, color=theme.CORES_COMBUSTIVEL[p], line=dict(color="#fff", width=1.5)),
            customdata=[fmt(v) for v in g[coluna]],
            hovertemplate=f"<b>{p}</b><br>%{{x}}: %{{customdata}}<extra></extra>"))
        if len(g):
            fig.add_annotation(x=x[-1], y=float(g[coluna].iloc[-1]), text=fmt(float(g[coluna].iloc[-1])),
                               showarrow=False, xanchor="left", xshift=8,
                               font=dict(size=11, color=theme.CORES_COMBUSTIVEL[p]))
    _base(fig, altura, legenda=True)
    fig.update_layout(margin=dict(r=70))
    if formato == "rs_litro":
        vals = s[coluna].dropna()
        ticks = np.round(np.arange(np.floor(vals.min() * 10) / 10, vals.max() + 0.1, 0.1), 2)
        fig.update_yaxes(tickvals=ticks, ticktext=[format_rs_litro(t) for t in ticks])
    return fig


def margem_pct_mensal(s: pd.DataFrame, media12: float, foco, parcial, altura: int = 260) -> go.Figure:
    fig = mensal_barras(s, "margem_pct", "pct", foco, parcial, altura)
    fig.add_hline(y=media12, line=dict(color=C["orange"], width=1.5))
    fig.update_yaxes(range=[0, float(max(s["margem_pct"].max(), media12)) * 1.2],
                     ticksuffix="%")
    return fig


# ----------------------------------------------------------------- diário ---
def diario_empilhado(s: pd.DataFrame, altura: int = 290) -> go.Figure:
    fig = go.Figure()
    for p in theme.COMBUSTIVEIS:
        g = s[s["produto"] == p]
        fig.add_trace(go.Bar(
            x=g["data"], y=g["litros"], name=theme.ROTULO_CURTO[p],
            marker=dict(color=theme.CORES_COMBUSTIVEL[p], line=dict(color="#ffffff", width=1)),
            customdata=[[format_litros(v), f"{d:%d/%m} ({DIAS_SEMANA[d.weekday()]})"]
                        for v, d in zip(g["litros"], g["data"])],
            hovertemplate=f"<b>{p}</b><br>%{{customdata[1]}}: %{{customdata[0]}}<extra></extra>"))
    _base(fig, altura, legenda=True)
    fig.update_layout(barmode="stack", bargap=0.18)
    datas = sorted(s["data"].unique())
    marcas = datas[::max(1, len(datas) // 8)]
    fig.update_xaxes(tickvals=marcas, ticktext=[pd.Timestamp(d).strftime("%d/%m") for d in marcas])
    _eixo_litros(fig, s.groupby("data")["litros"].sum().values)
    return fig


def preco_custo(s: pd.DataFrame, produto: str, altura: int = 280) -> go.Figure:
    """Duas linhas — preço de venda e custo médio. A faixa entre elas é a margem."""
    g = s[s["produto"] == produto].sort_values("data")
    cor = theme.CORES_COMBUSTIVEL[produto]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=g["data"], y=g["custo_medio"], name="Custo médio", mode="lines",
        line=dict(color="#8a93a8", width=2),
        customdata=[format_rs_litro(v, 3) for v in g["custo_medio"]],
        hovertemplate="Custo médio: %{customdata}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=g["data"], y=g["preco_medio"], name="Preço de venda", mode="lines",
        line=dict(color=cor, width=2.6), fill="tonexty", fillcolor=_alfa(cor, .10),
        customdata=[[format_rs_litro(p, 3), format_rs_litro(p - c, 3)] for p, c in zip(g["preco_medio"], g["custo_medio"])],
        hovertemplate="Preço de venda: %{customdata[0]}<br>Margem: %{customdata[1]}<extra></extra>"))
    _base(fig, altura, legenda=True)
    fig.update_layout(hovermode="x unified", margin=dict(r=80))
    ult = g.iloc[-1] if len(g) else None
    if ult is not None:
        fig.add_annotation(x=ult["data"], y=ult["preco_medio"], text=format_rs_litro(ult["preco_medio"]),
                           showarrow=False, xanchor="left", xshift=6, font=dict(size=11.5, color=cor))
        fig.add_annotation(x=ult["data"], y=ult["custo_medio"], text=format_rs_litro(ult["custo_medio"]),
                           showarrow=False, xanchor="left", xshift=6, font=dict(size=11.5, color="#6b7489"))
    lo, hi = float(g["custo_medio"].min()), float(g["preco_medio"].max())
    ticks = np.round(np.arange(np.floor(lo * 10) / 10, hi + 0.15, 0.1 if hi - lo < 1.2 else 0.2), 2)
    fig.update_yaxes(range=[lo - 0.08, hi + 0.08], tickvals=ticks, ticktext=[format_brl(t) for t in ticks])
    meses = pd.to_datetime(g["data"]).dt.to_period("M").unique()
    marcas = [p.to_timestamp() for p in meses]
    fig.update_xaxes(tickvals=marcas, ticktext=[nome_mes(p.month, p.year, curto=True) for p in meses])
    return fig


def _alfa(hex_cor: str, a: float) -> str:
    h = hex_cor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


# ---------------------------------------------------------------- estoque ---
def estoque_linhas(s: pd.DataFrame, altura: int = 280) -> go.Figure:
    fig = go.Figure()
    for p in theme.COMBUSTIVEIS:
        g = s[s["produto"] == p].sort_values("data")
        fig.add_trace(go.Scatter(
            x=g["data"], y=g["pct"], name=theme.ROTULO_CURTO[p], mode="lines",
            line=dict(color=theme.CORES_COMBUSTIVEL[p], width=2.2, shape="hv"),
            customdata=[[format_litros(e), format_pct_simples(v, 0)] for e, v in zip(g["estoque_final"], g["pct"])],
            hovertemplate=f"<b>{p}</b><br>%{{x|%d/%m}}: %{{customdata[0]}} (%{{customdata[1]}})<extra></extra>"))
    _base(fig, altura, legenda=True)
    fig.update_yaxes(range=[0, 105], ticksuffix="%")
    datas = sorted(s["data"].unique())
    marcas = datas[::max(1, len(datas) // 7)]
    fig.update_xaxes(tickvals=marcas, ticktext=[pd.Timestamp(d).strftime("%d/%m") for d in marcas])
    return fig


def autonomia_barras(est: pd.DataFrame, altura: int = 220) -> go.Figure:
    d = est.copy()
    d["rot"] = [f"{theme.ICONES_COMBUSTIVEL[str(p)]} {theme.ROTULO_CURTO[str(p)]}" for p in d["produto"]]
    d = d.iloc[::-1]
    cores = [theme.STATUS[s]["cor"] if s != "ok" else C["navy_ui"] for s in d["status"]]
    textos = [f"{format_decimal(v, 1)} dia{'s' if v >= 2 else ''} · {theme.STATUS[s]['rotulo']}"
              for v, s in zip(d["autonomia"], d["status"])]
    fig = go.Figure(go.Bar(
        y=d["rot"], x=d["autonomia"], orientation="h", marker=dict(color=cores, cornerradius=5),
        text=textos, textposition="outside", cliponaxis=False, constraintext="none", textfont=dict(size=12, color=C["text_primary"]),
        hovertemplate="%{y}: %{text}<extra></extra>"))
    _base(fig, altura)
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, float(d["autonomia"].max()) * 1.6])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12.5, color=C["text_primary"]))
    return fig


def estoque_rede(est: pd.DataFrame, altura: int = 230) -> go.Figure:
    g = est.groupby("produto", observed=True).agg(estoque=("estoque", "sum"), media=("media_dia", "sum")).reset_index()
    g["aut"] = g["estoque"] / g["media"]
    g = g.iloc[::-1]
    textos = [f"{format_litros(e)} · {format_decimal(a, 1)} dias" for e, a in zip(g["estoque"], g["aut"])]
    fig = go.Figure(go.Bar(
        y=[f"{theme.ICONES_COMBUSTIVEL[str(p)]} {theme.ROTULO_CURTO[str(p)]}" for p in g["produto"]],
        x=g["estoque"], orientation="h",
        marker=dict(color=[theme.CORES_COMBUSTIVEL[str(p)] for p in g["produto"]], cornerradius=5),
        text=textos, textposition="outside", cliponaxis=False, constraintext="none", textfont=dict(size=12, color=C["text_primary"]),
        hovertemplate="%{y}: %{text}<extra></extra>"))
    _base(fig, altura)
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, float(g["estoque"].max()) * 1.75])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12.5, color=C["text_primary"]))
    return fig


# ---------------------------------------------------- custos e resultado ---
def despesas_categoria(serie: pd.Series, altura: int = 300) -> go.Figure:
    s = serie.sort_values()
    total = s.sum()
    textos = [f"{format_brl_curto(v)} · {format_pct_simples(v / total * 100, 0)}" for v in s.values]
    fig = go.Figure(go.Bar(
        y=list(s.index), x=s.values, orientation="h", marker=dict(color=C["navy_ui"], cornerradius=4),
        text=textos, textposition="outside", cliponaxis=False, constraintext="none", textfont=dict(size=11.5, color=C["text_primary"]),
        customdata=[format_brl(v) for v in s.values],
        hovertemplate="%{y}: %{customdata}<extra></extra>"))
    _base(fig, altura)
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, float(s.max()) * 1.55])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12, color=C["text_primary"]))
    return fig


def cascata_resultado(res: dict, altura: int = 330) -> go.Figure:
    """Da margem bruta ao resultado: o que cada despesa come."""
    cats = res["por_categoria"]
    grandes = cats.head(5)
    resto = cats.iloc[5:].sum()
    nomes = ["Margem bruta"]
    valores = [res["margem"]]
    medidas = ["absolute"]
    if abs(res["perda_rs"]) > 0.5:
        nomes.append("Perdas no LMC")
        valores.append(res["perda_rs"])
        medidas.append("relative")
    for n, v in grandes.items():
        nomes.append(n)
        valores.append(-v)
        medidas.append("relative")
    if resto > 0:
        nomes.append("Demais despesas")
        valores.append(-resto)
        medidas.append("relative")
    nomes.append("Resultado")
    valores.append(0)
    medidas.append("total")
    textos = [format_brl_curto(v) for v in valores[:-1]] + [format_brl_curto(res["resultado"])]
    fig = go.Figure(go.Waterfall(
        x=nomes, y=valores, measure=medidas, text=textos, textposition="outside", cliponaxis=False, constraintext="none",
        textfont=dict(size=11.5, color=C["text_primary"]),
        connector=dict(line=dict(color="#d5dbe7", width=1)),
        increasing=dict(marker=dict(color=C["ok"])),
        decreasing=dict(marker=dict(color="#aab4c8")),
        totals=dict(marker=dict(color=C["navy_ui"])),
        hovertemplate="%{x}: %{text}<extra></extra>"))
    _base(fig, altura)
    fig.update_yaxes(showticklabels=False, showgrid=False)
    fig.update_xaxes(tickfont=dict(size=11, color=C["text_primary"]), tickangle=0)
    fig.update_layout(margin=dict(t=24))
    return fig


def dia_semana(d: pd.DataFrame, altura: int = 220) -> go.Figure:
    maior = d["vendas_l"].idxmax()
    cores = [C["orange"] if i == maior else C["navy_ui"] for i in d.index]
    textos = [format_litros_curto(v) for v in d["vendas_l"]]
    fig = go.Figure(go.Bar(
        x=DIAS_SEMANA, y=d["vendas_l"], marker=dict(color=cores, cornerradius=4),
        text=textos, textposition="outside", cliponaxis=False, constraintext="none", textfont=dict(size=11, color=C["text_primary"]),
        hovertemplate="%{x}: %{text}/dia<extra></extra>"))
    _base(fig, altura)
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, float(d["vendas_l"].max()) * 1.25])
    return fig


# ------------------------------------------------------------------- radar ---
def radar_serie(s: pd.DataFrame, produto: str, nome: str, altura: int = 330) -> go.Figure:
    """Semana a semana: a faixa de preços da cidade (mín–máx), a mediana e a linha da unidade."""
    cor = theme.CORES_COMBUSTIVEL.get(produto, C["navy_ui"])
    d = s.sort_values("semana")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["semana"], y=d["maximo"], mode="lines", line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["minimo"], mode="lines", line=dict(width=0), fill="tonexty", name="Faixa da cidade (mín–máx)",
        fillcolor="rgba(29,50,120,.10)", customdata=[[format_brl(a), format_brl(b)] for a, b in zip(d["minimo"], d["maximo"])],
        hovertemplate="Faixa da cidade: %{customdata[0]} a %{customdata[1]}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["mediana"], mode="lines", name="Mediana da cidade", line=dict(color="#8a93a8", width=1.8, dash="dot"),
        customdata=[format_brl(v) for v in d["mediana"]], hovertemplate="Mediana: %{customdata}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["b2"], mode="lines", name=nome, line=dict(color=cor, width=2.8),
        customdata=[[format_brl(p), f"{int(pos)}º de {int(n)}"] for p, pos, n in zip(d["b2"], d["posicao"], d["n"])],
        hovertemplate=f"{nome}: %{{customdata[0]}} (%{{customdata[1]}} mais barato)<extra></extra>"))
    _base(fig, altura, legenda=True)
    fig.update_layout(hovermode="x unified", margin=dict(r=70))
    if len(d):
        ult = d.iloc[-1]
        fig.add_annotation(x=ult["semana"], y=ult["b2"], text=format_brl(ult["b2"]), showarrow=False, xanchor="left",
                           xshift=6, font=dict(size=11.5, color=cor))
        lo, hi = float(d["minimo"].min()), float(d["maximo"].max())
        passo = 0.2 if hi - lo > 1.2 else 0.1
        ticks = np.round(np.arange(np.floor(lo / passo) * passo, hi + passo, passo), 2)
        fig.update_yaxes(range=[lo - 0.06, hi + 0.06], tickvals=ticks, ticktext=[format_brl(t) for t in ticks])
        meses = pd.to_datetime(d["semana"]).dt.to_period("M").unique()
        fig.update_xaxes(tickvals=[p.to_timestamp() for p in meses],
                         ticktext=[nome_mes(p.month, p.year, curto=True) for p in meses])
    return fig


def radar_variacao(v: pd.DataFrame, rotulos: list[str], altura: int = 330) -> go.Figure:
    """Barras deitadas: quanto cada posto mexeu no preço entre duas datas; o B2 em laranja."""
    d = v.assign(rotulo=rotulos).sort_values("variacao")
    sinal = lambda x: ("+" if x > 0 else "") + format_brl(x)
    fig = go.Figure(go.Bar(
        y=d["rotulo"], x=d["variacao"], orientation="h",
        marker=dict(color=[C["orange"] if b else C["navy_ui"] for b in d["eh_b2"]], cornerradius=4),
        text=[sinal(x) for x in d["variacao"]], textposition="outside", cliponaxis=False, constraintext="none",
        textfont=dict(size=11.5, color=C["text_primary"]),
        customdata=[[format_brl(a), format_brl(b)] for a, b in zip(d["preco_a"], d["preco_b"])],
        hovertemplate="<b>%{y}</b><br>%{customdata[0]} → %{customdata[1]}<extra></extra>"))
    _base(fig, altura)
    fig.update_xaxes(showticklabels=False, showgrid=False, zeroline=True, zerolinecolor=C["border"],
                     range=[min(0, float(d["variacao"].min())) - 0.05, float(d["variacao"].max()) + 0.35])
    fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(size=11.5, color=C["text_primary"]))
    mediana = float(d["variacao"].median())
    fig.add_vline(x=mediana, line_dash="dot", line_color="#8a93a8", line_width=1.5,
                  annotation_text=f"mediana {sinal(mediana)}", annotation_position="top", annotation_font_size=11,
                  annotation_font_color="#6b7489")
    fig.update_layout(bargap=0.3, margin=dict(t=26))
    return fig


def radar_dia(h: pd.DataFrame, produto: str, nome: str, altura: int = 330) -> go.Figure:
    """Dia a dia (Menor Preço): a faixa da cidade, a mediana e a linha da unidade. `h` vem de `nota_parana.historico_diario`."""
    cor = theme.CORES_COMBUSTIVEL.get(produto, C["navy_ui"])
    d = h.sort_values("dia")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["dia"], y=d["maximo"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=d["dia"], y=d["minimo"], mode="lines", line=dict(width=0), fill="tonexty", name="Faixa da cidade (mín–máx)",
        fillcolor="rgba(29,50,120,.10)", customdata=[[format_brl(a), format_brl(b)] for a, b in zip(d["minimo"], d["maximo"])],
        hovertemplate="Faixa da cidade: %{customdata[0]} a %{customdata[1]}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["dia"], y=d["mediana"], mode="lines", name="Mediana da cidade", line=dict(color="#8a93a8", width=1.8, dash="dot"),
        customdata=[format_brl(v) for v in d["mediana"]], hovertemplate="Mediana: %{customdata}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["dia"], y=d[nome], mode="lines+markers", name=nome, line=dict(color=cor, width=2.8), marker=dict(size=6),
        connectgaps=True, customdata=[format_brl(p) for p in d[nome]],
        hovertemplate=f"{nome}: %{{customdata}}<extra></extra>"))
    _base(fig, altura, legenda=True)
    fig.update_layout(hovermode="x unified", margin=dict(r=70))
    ult = d.dropna(subset=[nome]).iloc[-1]
    fig.add_annotation(x=ult["dia"], y=ult[nome], text=format_brl(ult[nome]), showarrow=False, xanchor="left", xshift=6,
                       font=dict(size=11.5, color=cor))
    lo, hi = float(d["minimo"].min()), float(d["maximo"].max())
    passo = 0.2 if hi - lo > 1.2 else 0.1
    ticks = np.round(np.arange(np.floor(lo / passo) * passo, hi + passo, passo), 2)
    fig.update_yaxes(range=[lo - 0.06, hi + 0.06], tickvals=ticks, ticktext=[format_brl(t) for t in ticks])
    dias = pd.to_datetime(d["dia"])
    passo_dias = max(1, len(dias) // 8)
    fig.update_xaxes(tickvals=list(dias[::passo_dias]), ticktext=[f"{x:%d/%m}" for x in dias[::passo_dias]])
    return fig


def radar_mapa(f: pd.DataFrame, rotulos: list[str], altura: int = 440) -> go.Figure:
    """Os postos de Guarapuava no mapa, com o preço: o B2 em laranja, os demais em azul. `f` tem lat, lon, preco, unidade_b2.

    A posição vem de um geohash aproximado (alguns postos têm só ~150 m de precisão): quem cai no mesmo ponto é afastado
    um pouquinho para não ficar um em cima do outro.
    """
    d = f.assign(rotulo=rotulos).dropna(subset=["lat", "lon"]).copy()
    d["_k"] = d["lat"].round(4).astype(str) + "|" + d["lon"].round(4).astype(str)
    ordem = d.groupby("_k").cumcount()
    ang = ordem * 2.4
    raio = 0.0007 * (d.groupby("_k")["_k"].transform("size") > 1) * (1 + ordem // 6)
    d["lat"] = d["lat"] + raio * np.sin(ang)
    d["lon"] = d["lon"] + raio * np.cos(ang)
    eh_b2 = d["unidade_b2"] != ""
    menor = d["preco"] == d["preco"].min()
    rot = [format_brl(p) if (b or m) else "" for p, b, m in zip(d["preco"], eh_b2, menor)]
    fig = go.Figure(go.Scattermap(
        lat=d["lat"], lon=d["lon"], mode="markers+text", text=rot, textposition="top center",
        textfont=dict(size=12, color=C["text_primary"]),
        marker=dict(size=[19 if b else 14 for b in eh_b2], color=[C["orange"] if b else C["navy_ui"] for b in eh_b2], opacity=0.92),
        customdata=[[r, format_brl(p)] for r, p in zip(d["rotulo"], d["preco"])],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>"))
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
                      map=dict(style="carto-positron", zoom=12.1,
                               center=dict(lat=float(d["lat"].mean()), lon=float(d["lon"].mean()))),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor=C["border"],
                                      font=dict(family=theme.FONTE_FAMILIA, size=12, color=C["text_primary"])))
    return fig
