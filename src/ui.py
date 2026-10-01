"""Peças visuais do painel — só desenham; recebem os números prontos.

Nenhuma conta de negócio aqui. Tudo que vira HTML passa por `html.escape`
quando o texto vem da planilha (nome de distribuidora, descrição de despesa).

**Armadilha herdada do Painel de Finanças:** no `st.markdown`, linha em
branco seguida de linha recuada vira BLOCO DE CÓDIGO e o HTML aparece cru na
tela. Por isso todo HTML daqui é montado em uma linha só (`"".join`).
"""
from __future__ import annotations

import base64
import html
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import streamlit as st

from src import theme
from src.formatting import (
    format_brl, format_brl_curto, format_decimal, format_litros, format_pct, format_pct_simples, format_pp,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@lru_cache(maxsize=4)
def logo_base64(nome: str = "logo_180.png") -> str:
    return base64.b64encode((ASSETS / nome).read_bytes()).decode()


def visual() -> str:
    """"novo" (padrão) ou "classico" — o botão do menu lateral troca. Só a
    APARÊNCIA muda: os números e as telas são os mesmos nos dois."""
    try:
        return "classico" if st.session_state.get("visual") == "classico" else "novo"
    except Exception:
        return "classico"


def novo() -> bool:
    return visual() == "novo"


def injetar_css():
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    if novo():
        css += "\n" + (ASSETS / "style_novo.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{theme.css_root_variables()}\n{css}</style>", unsafe_allow_html=True)


def md(texto: str):
    st.markdown(texto, unsafe_allow_html=True)


def esc(texto) -> str:
    return html.escape(str(texto))


# ------------------------------------------------------------- cabeçalho ---
def sem_emoji(texto: str) -> str:
    """Tira o emoji do começo do título ("🎯 Central" -> "Central")."""
    return re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", texto)


def topo(titulo: str, subtitulo: str = "", selo: str | None = None):
    if novo():
        titulo = sem_emoji(titulo)
    selo_html = f'<span class="selo">{selo}</span>' if selo else ""
    md(
        '<div class="topo-marca-movel">'
        f'<img src="data:image/png;base64,{logo_base64()}"><span>B2 Gestão</span></div>'
        f'<div class="topo"><div><h1>{titulo}</h1>'
        f'<div class="sub">{subtitulo}</div></div><div>{selo_html}</div></div>'
    )


def secao(titulo: str, sub: str = ""):
    if novo():
        titulo = sem_emoji(titulo)
    md(f'<div class="secao">{titulo}</div>' + (f'<div class="secao-sub">{sub}</div>' if sub else ""))


def bloco_titulo(titulo: str, sub: str = "", pergunta: str = ""):
    p = f'<div class="pergunta">{pergunta}</div>' if pergunta else ""
    s = f'<div class="bloco-sub">{sub}</div>' if sub else ""
    md(f'{p}<div class="bloco-titulo">{titulo}</div>{s}')


def nota(texto: str):
    md(f'<div class="nota">{texto}</div>')


# ---------------------------------------------------------------- cartões ---
def delta_html(valor: float | None, sentido: str = "auto", tipo: str = "pct", sufixo: str = "") -> str:
    """Selo de variação. `sentido`: auto (subir é bom), inversa, neutra."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return ""
    casas = 1
    arred = round(valor, casas if tipo != "brl" else 0)
    if arred == 0:
        classe, seta = "neutro", "="
    else:
        subiu = valor > 0
        seta = "▲" if subiu else "▼"
        if sentido == "neutra":
            classe = "neutro"
        else:
            bom = subiu if sentido == "auto" else not subiu
            classe = "bom" if bom else "ruim"
    if tipo == "pct":
        texto = format_pct(valor, 1)
    elif tipo == "pp":
        texto = format_pp(valor, 1)
    elif tipo == "rs_litro":
        texto = ("+" if valor > 0 else "") + format_brl(valor).replace("R$ ", "R$ ") + "/L"
    else:
        texto = ("+" if valor > 0 else "") + format_brl_curto(valor)
    return f'<span class="delta {classe}">{seta} {texto.lstrip("+") if seta == "=" else texto}</span>{sufixo}'


def sparkline(valores, cor: str = "currentColor", largura: int = 240, altura: int = 34) -> str:
    """Tendência em miniatura (SVG inline) — só aparece no visual novo."""
    v = [float(x) for x in valores if x == x]
    if len(v) < 3:
        return ""
    menor, maior = min(v), max(v)
    faixa = (maior - menor) or 1.0
    pad = 3
    xs = [pad + i * (largura - 2 * pad) / (len(v) - 1) for i in range(len(v))]
    ys = [altura - pad - (x - menor) / faixa * (altura - 2 * pad) for x in v]
    pontos = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"{xs[0]:.1f},{altura} {pontos} {xs[-1]:.1f},{altura}"
    return (f'<svg class="spark" viewBox="0 0 {largura} {altura}" width="{largura}" height="{altura}" '
            f'preserveAspectRatio="none" style="color:{cor}"><polygon points="{area}" fill="currentColor" '
            f'opacity=".12"/><polyline points="{pontos}" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>')


def kpi(rotulo: str, valor: str, sub: str = "", icone: str = "", classe: str = "", spark=None) -> str:
    ic = f'<div class="kpi-icone">{icone}</div>' if icone else ""
    sp = ""
    if spark is not None and novo():
        cor = "#ff8a57" if "destaque" in classe else theme.COLORS["navy_ui"]
        sp = f'<div class="kpi-spark">{sparkline(spark, cor)}</div>'
    return (f'<div class="kpi {classe}">{ic}<div class="kpi-rotulo">{rotulo}</div>'
            f'<div class="kpi-valor">{valor}</div><div class="kpi-sub">{sub}</div>{sp}</div>')


def grade_kpis(cartoes: list[str], grande: bool = False, compacto: bool = False):
    classe = ("grande" if grande else "") + (" compacto" if compacto else "")
    md(f'<div class="kpi-grid {classe}">{"".join(cartoes)}</div>')


def pill(status: str, texto: str | None = None) -> str:
    cfg = theme.STATUS.get(status)
    if cfg is None:
        return f'<span class="pill neutro">{texto or status}</span>'
    return f'<span class="pill {status}">{cfg["icone"]} {texto or cfg["rotulo"]}</span>'


def nome_combustivel(produto: str, curto: bool = False) -> str:
    cor = theme.CORES_COMBUSTIVEL.get(produto, "#999")
    icone = theme.ICONES_COMBUSTIVEL.get(produto, "")
    nome = theme.ROTULO_CURTO[produto] if curto else produto
    return (f'<span style="display:inline-flex;align-items:center;gap:.4rem">'
            f'<span class="comb-ponto" style="background:{cor}"></span>{icone} {nome}</span>')


# ---------------------------------------------------------------- tanques ---
def tanques_html(estoque_df) -> str:
    """Um tanque por combustível: nível na cor do produto, marca do mínimo
    (2,5 dias de venda) e a autonomia com a situação em palavra."""
    cards = []
    for _, r in estoque_df.iterrows():
        prod = str(r["produto"])
        cor = theme.CORES_COMBUSTIVEL[prod]
        pct = float(np.clip(r["pct"], 0, 100)) if r["pct"] == r["pct"] else 0
        minimo = (r["media_dia"] * 2.5 / r["capacidade"] * 100) if r["capacidade"] else 0
        minimo = float(np.clip(minimo, 0, 100))
        st_cfg = theme.STATUS[r["status"]]
        dias = r["autonomia"]
        dias_txt = f"{format_decimal(dias, 1)} dia{'s' if dias >= 2 else ''}" if dias == dias else "—"
        cards.append(
            '<div class="tanque-card">'
            f'<div class="tanque-nome"><span class="comb-ponto" style="background:{cor}"></span>'
            f'{theme.ICONES_COMBUSTIVEL[prod]} {prod}</div>'
            '<div class="tanque-corpo">'
            f'<div class="tanque" title="{format_pct_simples(pct, 0)} do tanque">'
            f'<div class="tanque-nivel" style="height:{pct:.1f}%;background:{cor}"></div>'
            f'<div class="tanque-min" style="bottom:{minimo:.1f}%" title="mínimo: 2,5 dias de venda"></div></div>'
            '<div class="tanque-info">'
            f'<div><div class="tanque-litros">{format_litros(r["estoque"])}</div>'
            f'<div class="tanque-pct">{format_pct_simples(pct, 0)} de {format_litros(r["capacidade"])}</div></div>'
            f'<div class="tanque-aut" style="color:{st_cfg["cor"]}">⏱ {dias_txt}<small>de autonomia</small></div>'
            f'<div>{pill(r["status"])}</div>'
            '</div></div></div>'
        )
    return f'<div class="tanques">{"".join(cards)}</div>'


# ---------------------------------------------------------------- alertas ---
def alerta_html(a, mostrar_posto: bool = True) -> str:
    det = "<br>".join(esc(d) for d in a.detalhes)
    if novo():
        # Linha enxuta: o título e o resumo à mostra; o detalhe abre num toque.
        posto = f'<span class="al-posto">{esc(a.posto.replace("B2 ", ""))}</span>' if mostrar_posto else ""
        return (f'<details class="alerta-linha {a.nivel}"><summary><span class="al-ponto"></span>'
                f'<span class="al-corpo"><span class="al-titulo">{esc(a.titulo.capitalize())}</span>'
                f'<span class="al-resumo">{esc(a.resumo[0].upper() + a.resumo[1:])}</span></span>{posto}</summary>'
                f'<div class="al-det">{det}</div></details>')
    posto = f'<span class="a-posto">{esc(a.posto)}</span>' if mostrar_posto else ""
    return (f'<div class="alerta {a.nivel}"><div class="a-topo">'
            f'<span class="a-titulo">{a.icone} {esc(a.titulo)}</span>{posto}</div>'
            f'<div class="a-resumo">{esc(a.resumo[0].upper() + a.resumo[1:])}</div>'
            f'<div class="a-det">{det}</div></div>')


# ---------------------------------------------------------------- tabelas ---
def tabela_html(colunas: list[tuple[str, bool]], linhas: list[list[str]], total: list[str] | None = None,
                classe: str = "tabela") -> str:
    """colunas = [(título, é_número)], linhas já formatadas (HTML permitido)."""
    th = "".join(f'<th class="{"num" if n else ""}">{t}</th>' for t, n in colunas)
    corpo = []
    for l in linhas:
        corpo.append("<tr>" + "".join(
            f'<td class="{"num" if colunas[i][1] else ""}">{v}</td>' for i, v in enumerate(l)) + "</tr>")
    if total:
        corpo.append('<tr class="total">' + "".join(
            f'<td class="{"num" if colunas[i][1] else ""}">{v}</td>' for i, v in enumerate(total)) + "</tr>")
    return f'<div class="tabela-wrap"><table class="{classe}"><thead><tr>{th}</tr></thead><tbody>{"".join(corpo)}</tbody></table></div>'


def barra_celula(texto: str, proporcao: float, cor: str) -> str:
    p = float(np.clip(proporcao, 0, 1)) * 100 if proporcao == proporcao else 0
    return (f'<span class="barra-cel">{texto}<span class="fundo">'
            f'<span class="frente" style="display:block;width:{p:.1f}%;background:{cor}"></span></span></span>')


def var_html(valor: float | None, tipo: str = "pct", sentido: str = "auto") -> str:
    if valor is None or valor != valor:
        return '<span class="var-neu">—</span>'
    if round(valor, 1) == 0:
        return '<span class="var-neu">= 0</span>'
    bom = (valor > 0) if sentido == "auto" else (valor < 0)
    classe = "var-neu" if sentido == "neutra" else ("var-pos" if bom else "var-neg")
    seta = "▲" if valor > 0 else "▼"
    texto = format_pct(valor, 1) if tipo == "pct" else format_pp(valor, 1)
    return f'<span class="{classe}">{seta} {texto}</span>'
