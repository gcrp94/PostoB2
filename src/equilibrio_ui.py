"""O destaque do Resumo do posto: o PONTO DE EQUILÍBRIO do mês.

Pedido do dono (reunião de 05/10/2026): ver o dia em que o posto passou a cobrir todos os custos, quanto falta (em
R$ e em dias) quando ainda não cobriu, e como isso está contra as médias. As contas moram em
`analytics.equilibrio`; aqui só se desenha — e de forma enxuta (06/10/2026): um cartão com UM número grande, uma
barra de progresso, uma linha de comparações e um gráfico. A comparação com a rede abre num toque.

Palavras: o dono diz "lucro". No painel é "resultado" (margem bruta + perdas − despesas, antes de IR/CSLL): a mesma
conta da aba Compras e Custos. "Lucro" só vira palavra de tela quando houver IR/CSLL na conta.
"""
from __future__ import annotations

import streamlit as st

from src import analytics as an
from src import charts, ui
from src.formatting import format_brl_curto, format_decimal, format_litros, nome_mes


def _dias(n: float) -> str:
    n = int(round(n))
    return f"{n} dia" + ("" if abs(n) == 1 else "s")


def _contra(dia: float, ref: float | None) -> str:
    """"1 dia antes": menor é melhor — cobrir os custos mais cedo."""
    if ref is None:
        return ""
    d = round(dia - ref)
    return "igual" if d == 0 else f"{_dias(abs(d))} {'antes' if d < 0 else 'depois'}"


def _principal(eq: dict) -> tuple[str, str, str, str]:
    """(situação do selo, texto do selo, o número grande, uma frase CURTA ou vazia) conforme o mês."""
    dia = eq["dia_equilibrio"]
    if dia is not None:
        return "ok", "Custos cobertos", f"Dia {dia}", ""
    if not eq["parcial"]:
        return "critico", "Abaixo do equilíbrio", format_brl_curto(eq["falta"]), "faltaram"
    if eq["fecha_no_mes"]:
        return "atencao", f"Faltam ≈ {_dias(eq['dias_faltam'])}", format_brl_curto(eq["falta"]),             f"faltam · previsto dia {eq['previsto_dia']}"
    return "critico", "Não fecha no mês", format_brl_curto(eq["falta"]), "faltam"


def _regua(eq: dict) -> str:
    """A régua do LB: da origem até o LB acumulado, com um traço nos custos do mês.

    Azul = o LB que cobre os custos; laranja = o que passa deles (resultado, antes de IR/CSLL); listrado = o que falta.
    Os rótulos ficam em cima (LB, quanto falta) e embaixo (custos, quanto passou), cada um encostado no seu ponto.
    """
    lb, custos = max(eq["acumulado"], 0.0), eq["custos"]
    escala = max(lb, custos)
    pos_lb, pos_custos = lb / escala * 100, custos / escala * 100
    cobre = min(lb, custos) / escala * 100
    trilho = f'<i class="eq-lb" style="width:{cobre:.2f}%"></i>'
    cima = f'<span style="right:{100 - pos_lb:.2f}%">LB <b>{format_brl_curto(eq["acumulado"])}</b></span>'
    baixo = f'<span style="right:{100 - pos_custos:.2f}%">Custos <b>{format_brl_curto(custos)}</b></span>'
    if lb > custos:                                            # passou dos custos: o que sobra, em laranja
        trilho += f'<i class="eq-extra" style="width:{pos_lb - pos_custos:.2f}%"></i>'
        baixo += f'<span style="left:{pos_custos:.2f}%" class="eq-mais">+ <b>{format_brl_curto(lb - custos)}</b></span>'
    elif lb < custos:                                          # ainda falta: o vazio, listrado
        trilho += f'<i class="eq-falta" style="width:{pos_custos - pos_lb:.2f}%"></i>'
        cima += f'<span style="left:{pos_lb:.2f}%" class="eq-mais">faltam <b>{format_brl_curto(custos - eq["acumulado"])}</b></span>'
    return (f'<div class="eq-regua" title="Lucro Bruto (LB) acumulado do mês contra os custos do mês">'
            f'<div class="eq-lin">{cima}</div>'
            f'<div class="eq-pista"><div class="eq-trilho">{trilho}</div><b class="eq-tique" style="left:{pos_custos:.2f}%"></b></div>'
            f'<div class="eq-lin">{baixo}</div></div>')


def _cartao(eq: dict, per: an.Periodo) -> str:
    situacao, selo, numero, frase = _principal(eq)
    ate = f" · até {eq['dia_final']:02d}/{per.mes:02d}" if eq["parcial"] else ""
    dia = eq["dia_equilibrio"] if eq["dia_equilibrio"] is not None else eq["previsto_dia"]
    prev = "" if eq["dia_equilibrio"] is not None else " (previsto)"
    rodape = []
    h = eq["historico"]["media_dia"]
    if h is not None and dia is not None:
        rodape.append(f"Média do posto <b>dia {format_decimal(h, 0)}</b> · {_contra(dia, h)}{prev}")
    r = eq["rede"]["media_dia"]
    if r is not None and dia is not None and len(eq["rede"]["postos"]) > 1:
        rodape.append(f"Média da rede <b>dia {format_decimal(r, 0)}</b> · {_contra(dia, r)}{prev}")
    rodape.append(f"Custos <b>{format_brl_curto(eq['custos'])}</b>{' (est.)' if eq['custos_estimados'] else ''}")
    if eq["litros_dia_equilibrio"] and eq["litros_dia_atual"]:
        rodape.append(f"Empata com <b>{format_litros(eq['litros_dia_equilibrio'])}/dia</b> · vende "
                      f"{format_litros(eq['litros_dia_atual'])}")
    txt_frase = f'<span class="eq-frase">{frase}</span>' if frase else ""
    return (f'<div class="eq"><div class="eq-topo"><span class="eq-rotulo">Ponto de equilíbrio · '
            f'{nome_mes(per.mes, per.ano)}{ate}</span>{ui.pill(situacao, selo)}</div>'
            f'<div class="eq-principal"><span class="eq-numero">{numero}</span>{txt_frase}</div>'
            f'{_regua(eq)}'
            f'<div class="eq-rodape">{"".join(f"<span>{x}</span>" for x in rodape)}</div></div>')


def bloco(df, despesas, posto: str, per: an.Periodo, custo: str = "planilha"):   # `custo`: o botão ao lado das abas já o mostra
    """O destaque: o cartão, o gráfico e (aberto num toque) a comparação com a rede."""
    eq = an.equilibrio(df, despesas, posto, per.ano, per.mes)
    if not eq["disponivel"]:
        ui.md(f'<div class="eq"><div class="eq-topo"><span class="eq-rotulo">Ponto de equilíbrio</span></div>'
              f'<div class="eq-frase" style="margin-top:.4rem">Indisponível: {ui.esc(eq["motivo"])}. Com as despesas '
              f'do mês lançadas, o painel mostra em que dia o posto cobriu todos os custos.</div></div>')
        return
    ui.md(_cartao(eq, per))
    with st.container(border=True):
        st.plotly_chart(charts.equilibrio_curva(eq), width="stretch", config=charts.CFG)
    with st.expander("Comparar com os outros postos e ver como é calculado"):
        ui.bloco_titulo("Dia em que cada posto cobre os custos", "listrado = previsto")
        st.plotly_chart(charts.equilibrio_rede(eq), width="stretch", config=charts.CFG)
        sem = [p for p, v in eq["rede"]["postos"].items() if v["dia"] is None]
        if sem:
            ui.nota(f"{', '.join(sem)}: sem previsão no mês.")
        ui.nota("LB + perdas/sobras do LMC acumulados até cobrir as despesas do mês (antes de IR/CSLL). est. = custos pela média dos 3 últimos meses.")
