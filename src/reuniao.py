"""Indicadores para a reunião com os gerentes — o placar e a pauta.

O que o gerente controla de verdade, e por isso vai para a mesa:

* **volume** contra os mesmos dias do mês anterior — atendimento e pista;
* **margem por litro** contra a média da rede — preço e compra;
* **mix de aditivada** (% da gasolina vendida como aditivada) — é venda
  ativa do frentista: cada ponto a mais é margem que não depende de preço;
* **perda no LMC** — cuidado com o tanque (e o primeiro sinal de desvio);
* **despesa por litro** e **resultado por litro** — o posto como negócio;
* **pontualidade da planilha** — dia com dado até as 10h do dia seguinte;
* **dias em risco de estoque** — pedido feito tarde;
* **alterações em dias já enviados** — da trilha de auditoria.

Metas fixas onde há régua de mercado (perda, pontualidade, aditivada);
contra a média da rede onde depende do perfil do posto (margem, despesa).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src import analytics as an
from src import auditoria
from src.formatting import (
    format_decimal, format_litros_curto, format_pct, format_pct_simples, format_rs_litro, nome_mes,
)

META_MIX_ADITIVADA = 20.0     # % da gasolina
META_PERDA = 0.30             # % do vendido
META_PONTUALIDADE = 90.0      # % dos dias
HORA_LIMITE_ENVIO = 10        # dado do dia d até 10h do dia d+1
FOLGA_REDE = 0.03             # R$/L abaixo da média da rede antes de virar pauta


def mix_aditivada(df: pd.DataFrame) -> float:
    g = df[df["produto"].astype(str).isin(["Gasolina Comum", "Gasolina Aditivada"])]
    tot = g["vendas_l"].sum()
    adit = g[g["produto"].astype(str) == "Gasolina Aditivada"]["vendas_l"].sum()
    return adit / tot * 100 if tot else np.nan


def pontualidade(envios: pd.DataFrame, posto: str, inicio, fim) -> float:
    """% dos dias cujo dado chegou até as 10h do dia seguinte. Sem histórico
    diário de envios no período (mês enviado de uma vez), não há como medir."""
    if envios is None or envios.empty:
        return np.nan
    e = envios[(envios["posto"] == posto) & envios["data_hora"].notna()]
    e = e[(e["data_hora"] >= pd.Timestamp(inicio)) & (e["data_hora"] <= pd.Timestamp(fim) + timedelta(days=2))]
    if len(e) < 5:
        return np.nan
    chegadas = []
    for _, r in e.iterrows():
        m = re.search(r"até (\d{2})/(\d{2})", str(r["detalhe"]))
        if m:
            ate = datetime(pd.Timestamp(inicio).year, int(m.group(2)), int(m.group(1)))
            chegadas.append((r["data_hora"].to_pydatetime(), ate))
    if not chegadas:
        return np.nan
    dias = pd.date_range(inicio, fim, freq="D")
    no_prazo = 0
    for d in dias:
        prazo = (d + timedelta(days=1)).to_pydatetime().replace(hour=HORA_LIMITE_ENVIO)
        if any(ate >= d.to_pydatetime() and quando <= prazo for quando, ate in chegadas):
            no_prazo += 1
    return no_prazo / len(dias) * 100


def dias_em_risco(df: pd.DataFrame, posto: str, inicio, fim) -> int:
    """Dias em que algum tanque ficou com menos de 1,5 dia de venda."""
    datas = set()
    dp = df[df["posto"] == posto].sort_values("data")
    for _, g in dp.groupby("produto", observed=True):
        media = g["vendas_l"].rolling(7, min_periods=3).mean()
        risco = g[(g["estoque_final"] / media) < an.AUTONOMIA_CRITICA]
        risco = risco[(risco["data"] >= pd.Timestamp(inicio)) & (risco["data"] <= pd.Timestamp(fim))]
        datas.update(risco["data"])
    return len(datas)


def placar(df: pd.DataFrame, despesas: pd.DataFrame, envios: pd.DataFrame, aud: pd.DataFrame,
           per: an.Periodo, postos: list[str]) -> pd.DataFrame:
    sus = auditoria.suspeitas(aud, dias=3650) if aud is not None and len(aud) else pd.DataFrame()
    linhas = []
    for posto in postos:
        dp = df[df["posto"] == posto]
        if dp.empty:
            continue
        pp = an.periodo(dp, per.ano, per.mes)
        ind = an.indicadores(df, per, posto)
        res = an.resultado(df, despesas, per, posto)
        atual, _ = an.fatias(df, per, posto)
        alteracoes = 0
        if len(sus):
            s = sus[(sus["posto"] == posto) & (sus["data"] >= pd.Timestamp(per.inicio))
                    & (sus["data"] <= pd.Timestamp(per.fim))]
            alteracoes = int(s["data"].nunique())
        litros = ind["litros"]
        linhas.append({
            "posto": posto,
            "ate": pp.fim,
            "litros": litros,
            "litros_ant": ind["anterior"]["litros"],
            "var_litros":(litros / ind["anterior"]["litros"] - 1) * 100 if ind["anterior"]["litros"] else np.nan,
            "margem_litro": ind["margem_litro"],
            "margem_pct": ind["margem_pct"],
            "mix_aditivada": mix_aditivada(atual),
            "perda_pct": ind["perda_pct"],
            "despesa_litro": res["despesas"] / litros if litros and res["tem_despesas"] else np.nan,
            "resultado_litro": res["resultado"] / litros if litros and res["tem_despesas"] else np.nan,
            "pontualidade": pontualidade(envios, posto, per.inicio, per.fim),
            "dias_risco": dias_em_risco(df, posto, per.inicio, per.fim),
            "alteracoes": alteracoes,
        })
    return pd.DataFrame(linhas)


def situacao(coluna: str, valor: float, rede: pd.Series) -> str:
    """ok | atencao | critico — a cor do número no placar."""
    if valor is None or valor != valor:
        return "neutro"
    if coluna == "var_litros":
        return "ok" if valor >= -2 else ("critico" if valor <= -10 else "atencao")
    if coluna == "margem_litro":
        return "ok" if valor >= rede["margem_litro"] - FOLGA_REDE else "atencao"
    if coluna == "mix_aditivada":
        return "ok" if valor >= META_MIX_ADITIVADA else "atencao"
    if coluna == "perda_pct":
        return "ok" if valor <= META_PERDA else ("critico" if valor > an.TOLERANCIA_PERDA else "atencao")
    if coluna == "despesa_litro":
        return "ok" if valor <= rede["despesa_litro"] + FOLGA_REDE else "atencao"
    if coluna == "resultado_litro":
        return "ok" if valor > 0 else "critico"
    if coluna == "pontualidade":
        return "ok" if valor >= META_PONTUALIDADE else ("critico" if valor < 60 else "atencao")
    if coluna == "dias_risco":
        return "ok" if valor == 0 else ("critico" if valor >= 3 else "atencao")
    if coluna == "alteracoes":
        return "ok" if valor == 0 else "critico"
    return "neutro"


def medias_rede(p: pd.DataFrame) -> pd.Series:
    """A linha "Rede" do placar: por litro, ponderado pelo volume; contagens,
    somadas."""
    peso = p["litros"]

    def pond(coluna):
        ok = p[coluna].notna()
        return np.average(p.loc[ok, coluna], weights=peso[ok]) if ok.any() else np.nan

    ant = p["litros_ant"].sum() if "litros_ant" in p else 0
    return pd.Series({
        "litros": peso.sum(),
        "var_litros": (peso.sum() / ant - 1) * 100 if ant else np.nan,
        "margem_litro": pond("margem_litro"),
        "margem_pct": pond("margem_pct"),
        "mix_aditivada": pond("mix_aditivada"),
        "perda_pct": pond("perda_pct"),
        "despesa_litro": pond("despesa_litro"),
        "resultado_litro": pond("resultado_litro"),
        "pontualidade": p["pontualidade"].mean(),
        "dias_risco": p["dias_risco"].sum(),
        "alteracoes": p["alteracoes"].sum(),
    })


def _pct0(v):
    return format_pct_simples(v, 0)


def _pct1(v):
    return format_pct_simples(v, 1)


def _pct2(v):
    return format_pct_simples(v, 2)


def _inteiro(v):
    return f"{int(v)}"


# coluna, rótulo, régua, formatação — a ordem do placar e da ficha
INDICADORES = [
    ("var_litros", "Volume vs mês anterior", "−2% ou mais", lambda v: format_pct(v, 1)),
    ("margem_litro", "Margem bruta por litro", "média da rede", format_rs_litro),
    ("mix_aditivada", "Aditivada na gasolina", f"meta {format_pct_simples(META_MIX_ADITIVADA, 0)}", _pct1),
    ("perda_pct", "Perda no LMC", f"meta até {format_pct_simples(META_PERDA, 2)}", _pct2),
    ("despesa_litro", "Despesa por litro", "média da rede", format_rs_litro),
    ("resultado_litro", "Resultado por litro", "positivo", format_rs_litro),
    ("pontualidade", f"Planilha até as {HORA_LIMITE_ENVIO}h", f"meta {format_pct_simples(META_PONTUALIDADE, 0)}",
     _pct0),
    ("dias_risco", "Dias com estoque crítico", "zero", _inteiro),
    ("alteracoes", "Dias alterados depois de enviados", "zero", _inteiro),
]


def formatar(coluna: str, valor) -> str:
    if valor is None or valor != valor:
        return "—"
    return next(f for c, _, _, f in INDICADORES if c == coluna)(valor)


def ficha_html(linha: pd.Series, rede: pd.Series, p: pd.DataFrame, per: an.Periodo, simulado: bool = False) -> str:
    """A ficha da reunião com um gerente — HTML para abrir e imprimir."""
    cor = {"ok": "#1f7a4d", "atencao": "#a05f0a", "critico": "#c53030", "neutro": "#5b6475"}
    palavra = {"ok": "● dentro", "atencao": "▲ atenção", "critico": "■ crítico", "neutro": "—"}
    periodo = f"{nome_mes(per.mes)} de {per.ano}" + (f", até {linha['ate']:%d/%m}" if per.parcial else "")
    linhas = []
    for coluna, rotulo, regua, _ in INDICADORES:
        s = situacao(coluna, linha[coluna], rede)
        linhas.append(f"<tr><td>{rotulo}</td><td class='n'><b>{formatar(coluna, linha[coluna])}</b></td>"
                      f"<td class='n'>{formatar(coluna, rede[coluna])}</td><td>{regua}</td>"
                      f"<td style='color:{cor[s]};font-weight:700'>{palavra[s]}</td></tr>")
    itens = "".join(f"<li>{i}</li>" for i in pauta(linha, rede, p))
    combinados = "".join("<tr><td>&nbsp;</td><td></td><td></td></tr>" for _ in range(4))
    aviso = "<p class='aviso'>Dados simulados para apresentação.</p>" if simulado else ""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Reunião — {linha['posto']} — {periodo}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;color:#1b2333;max-width:820px;margin:28px auto;padding:0 18px}}
h1{{color:#041243;font-size:22px;margin:0}} .sub{{color:#5b6475;margin:4px 0 18px}}
h2{{color:#041243;font-size:15px;border-bottom:2px solid #e4612a;padding-bottom:4px;margin-top:26px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{border-bottom:1px solid #e3e7ef;padding:7px 6px;text-align:left}}
th{{background:#f3f5f9;font-size:12px}} .n{{text-align:right}} li{{margin:6px 0;font-size:14px}}
.aviso{{color:#a05f0a;font-size:12px}} @media print{{body{{margin:0}}}}
</style></head><body>
<h1>Reunião de gerência — {linha['posto']}</h1>
<div class="sub">{periodo} · comparação com os mesmos dias do mês anterior · B2 Gestão</div>
<h2>Placar do mês</h2>
<table><tr><th>Indicador</th><th class="n">Posto</th><th class="n">Rede</th><th>Régua</th><th>Situação</th></tr>
{''.join(linhas)}</table>
<h2>Pauta sugerida</h2><ul>{itens}</ul>
<h2>Combinados</h2>
<table><tr><th style="width:60%">Ação</th><th>Responsável</th><th>Prazo</th></tr>{combinados}</table>
{aviso}</body></html>"""


def pauta(linha: pd.Series, rede: pd.Series, p: pd.DataFrame) -> list[str]:
    """A pauta sugerida para a conversa com o gerente — do mais grave ao elogio."""
    itens = []
    if linha["alteracoes"]:
        itens.append(f"🔴 {linha['alteracoes']} dia(s) já enviado(s) foram alterados depois — pedir a "
                     "justificativa por escrito e conferir com os encerrantes.")
    if linha["perda_pct"] > an.TOLERANCIA_PERDA:
        itens.append(f"🔴 Perda de {format_pct_simples(linha['perda_pct'], 2)} no LMC — conferir aferição das "
                     "bombas, medição dos tanques e possível vazamento.")
    elif linha["perda_pct"] > META_PERDA:
        itens.append(f"🟡 Perda de {format_pct_simples(linha['perda_pct'], 2)} no LMC, acima da meta de "
                     f"{format_pct_simples(META_PERDA, 2)} — acompanhar a medição dos tanques.")
    if linha["resultado_litro"] == linha["resultado_litro"] and linha["resultado_litro"] <= 0:
        itens.append(f"🔴 Resultado de {format_rs_litro(linha['resultado_litro'])} depois das despesas — a "
                     "margem não está pagando o posto.")
    if linha["var_litros"] == linha["var_litros"] and linha["var_litros"] <= -5:
        itens.append(f"🟡 Volume {format_pct(linha['var_litros'], 1)} contra os mesmos dias do mês anterior — "
                     "o que mudou na pista (concorrência, obras, atendimento)?")
    if linha["margem_litro"] < rede["margem_litro"] - FOLGA_REDE:
        itens.append(f"🟡 Margem de {format_rs_litro(linha['margem_litro'])}, abaixo da média da rede "
                     f"({format_rs_litro(rede['margem_litro'])}) — revisar preço de bomba e compras.")
    if linha["despesa_litro"] == linha["despesa_litro"] and \
            linha["despesa_litro"] > rede["despesa_litro"] + FOLGA_REDE:
        itens.append(f"🟡 Despesa de {format_rs_litro(linha['despesa_litro'])}, acima da média da rede "
                     f"({format_rs_litro(rede['despesa_litro'])}) — revisar folha, energia e manutenção.")
    if linha["mix_aditivada"] < META_MIX_ADITIVADA:
        itens.append(f"🟡 Aditivada é {format_pct_simples(linha['mix_aditivada'], 1)} da gasolina "
                     f"(meta {format_pct_simples(META_MIX_ADITIVADA, 0)}) — treinar a oferta na bomba.")
    if linha["pontualidade"] == linha["pontualidade"] and linha["pontualidade"] < META_PONTUALIDADE:
        itens.append(f"🟡 Planilha no prazo em {format_pct_simples(linha['pontualidade'], 0)} dos dias — "
                     f"combinar o envio até as {HORA_LIMITE_ENVIO}h do dia seguinte.")
    if linha["dias_risco"]:
        itens.append(f"🟡 {linha['dias_risco']} dia(s) com combustível para menos de 1,5 dia — antecipar "
                     "os pedidos à distribuidora.")
    for coluna, texto in (("margem_litro", "a melhor margem por litro da rede"),
                          ("mix_aditivada", "o melhor mix de aditivada da rede"),
                          ("var_litros", "o maior crescimento de volume da rede")):
        if p[coluna].notna().any() and linha["posto"] == p.loc[p[coluna].idxmax(), "posto"]:
            itens.append(f"🟢 Tem {texto} — reconhecer a equipe.")
    if not any(i.startswith(("🔴", "🟡")) for i in itens):
        itens.insert(0, "🟢 Mês dentro das metas.")
    return itens


def texto_placar(p: pd.DataFrame, per: an.Periodo) -> str:
    """O placar em texto, para o celular."""
    rede = medias_rede(p)
    cab = f"{nome_mes(per.mes)} até {per.fim:%d/%m}" if per.parcial else f"{nome_mes(per.mes)}/{per.ano}"
    linhas = [f"📅 {cab}", ""]
    for _, r in p.iterrows():
        situacoes = [situacao(c, r[c], rede) for c, *_ in INDICADORES]
        marca = "🔴" if "critico" in situacoes else ("🟡" if "atencao" in situacoes else "🟢")
        envio = (f" · envio {format_pct_simples(r['pontualidade'], 0)}"
                 if r["pontualidade"] == r["pontualidade"] else "")
        linhas.append(f"{marca} {r['posto'].replace('B2 ', '')}: {format_litros_curto(r['litros'])}"
                      f" ({format_pct(r['var_litros'], 0)}) · {format_rs_litro(r['margem_litro'])}"
                      f" · aditivada {format_pct_simples(r['mix_aditivada'], 0)}"
                      f" · perda {format_pct_simples(r['perda_pct'], 2)}{envio}")
    linhas += ["", "🏆 Destaques"]
    for coluna, rotulo, fmt in (("margem_litro", "Margem/L", lambda v: format_rs_litro(v)),
                                ("mix_aditivada", "Aditivada", lambda v: format_pct_simples(v, 0)),
                                ("var_litros", "Crescimento", lambda v: format_pct(v, 1))):
        if p[coluna].notna().any():
            melhor = p.loc[p[coluna].idxmax()]
            linhas.append(f"• {rotulo}: {melhor['posto'].replace('B2 ', '')} ({fmt(melhor[coluna])})")
    return "\n".join(linhas)
