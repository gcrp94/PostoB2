"""B2 Assistente — as respostas que chegam ao celular.

Recebe um texto ("resumo b2 centro", "estoque candói", "⛽ Índio",
"alertas") e devolve uma `Resposta` curta, pensada para a tela do celular:
emoji no começo da linha, número grande primeiro, a data do dado sempre
visível. Sem rede, sem efeitos colaterais, sem IA: é consulta à MESMA base e
às MESMAS regras de alerta do painel (`src/alertas.py`) — o celular nunca
diz algo que a Central não diz.

O entendimento é tolerante de propósito (maiúsculas, acentos, "b2" e
palavras de ligação são opcionais): quem demonstra digita rápido no celular.

* só o posto ("candói", "⛽ Candói")          -> resumo do posto
* resumo | estoque | vendas | margem + posto -> a consulta
* resumo | estoque | vendas | margem sozinho -> a rede inteira
* alertas                                    -> o que exige ação e atenção
* ajuda | menu | oi | /start                 -> o menu

Texto que não se entende vira `ValueError` com a ajuda: os transportes
(Telegram, ntfy) respondem com ela.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from src import alertas as al
from src import analytics as an
from src.formatting import (
    format_brl, format_brl_curto, format_decimal, format_litros, format_pct, format_pct_simples,
    format_rs_litro, nome_mes,
)
from src.theme import COMBUSTIVEIS, ICONES_COMBUSTIVEL

# Ordem = prioridade: "como está o estoque do Candói" é estoque, não resumo.
ACOES = ("alertas", "auditoria", "pendencias", "reuniao", "estoque", "vendas", "margem", "resumo", "ajuda")
SINONIMOS = {
    "auditoria": ("auditoria", "fraude", "fraudes", "alteracoes", "alterados", "alterado", "desvio"),
    "pendencias": ("pendencias", "pendentes", "pendente", "atrasados", "atrasado", "cobranca"),
    "reuniao": ("reuniao", "placar", "gerentes", "gerencia", "gerencias", "ranking"),
    "resumo": ("resumo", "como esta", "como vai", "situacao", "painel", "visao"),
    "estoque": ("estoque", "tanque", "tanques", "autonomia", "combustivel", "reposicao"),
    "vendas": ("vendas", "venda", "vendeu", "faturamento", "faturou", "litros"),
    "margem": ("margem", "lucro", "ganho", "ganhamos"),
    "alertas": ("alertas", "alerta", "atencao", "problemas", "problema", "riscos", "risco"),
    "ajuda": ("ajuda", "menu", "oi", "ola", "bom dia", "boa tarde", "boa noite", "start", "comandos"),
}
PALAVRAS_REDE = ("rede", "geral", "todos", "todas", "postos")
ICONE_SITUACAO = {"critico": "🔴", "atencao": "🟡", "ok": "🟢"}


@dataclass(frozen=True)
class Resposta:
    titulo: str
    mensagem: str
    # (rótulo do botão, comando) — o Telegram vira botões embaixo da resposta.
    sugestoes: tuple = field(default=())


# --------------------------------------------------------------- entender ---
def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto).casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)          # tira emoji e pontuação
    return " ".join(texto.split())


def _curto(posto: str) -> str:
    return posto.replace("B2 ", "")


def entender(comando: str, postos: list[str]) -> tuple[str, str | None]:
    """(ação, posto ou None = rede). Levanta ValueError se não entender."""
    texto = f" {_normalizar(comando)} "
    posto = None
    for p in postos:
        nome = _normalizar(_curto(p))
        if f" {nome} " in texto:
            posto = p
            break
    acao = None
    for a in ACOES:
        if any(f" {s} " in texto for s in SINONIMOS[a]):
            acao = a
            break
    if acao is None:
        if posto:
            acao = "resumo"                  # "⛽ Candói" = resumo do Candói
        elif any(f" {r} " in texto for r in PALAVRAS_REDE):
            acao = "resumo"
        else:
            raise ValueError(_texto_ajuda(postos, entendeu=False))
    return acao, posto


# --------------------------------------------------------------- formatos ---
def _data_curta(d) -> str:
    return f"{pd.Timestamp(d):%d/%m}"


def _variacao(atual: float, anterior: float) -> str:
    if not anterior:
        return ""
    v = (atual - anterior) / anterior * 100
    if round(v, 1) == 0:
        return " (= estável)"
    return f" ({'▲' if v > 0 else '▼'} {format_pct_simples(abs(v), 1)})"


def _cabecalho_periodo(per: an.Periodo, simulado: bool) -> str:
    mes = nome_mes(per.mes)
    txt = f"📅 {mes} até {per.fim:%d/%m}" if per.parcial else f"📅 {mes}/{per.ano}"
    return txt + (" · dados simulados" if simulado else "")


def _linhas_estoque(est: pd.DataFrame) -> list[str]:
    linhas = []
    for _, r in est.iterrows():
        prod = str(r["produto"])
        dias = r["autonomia"]
        dias_txt = (f"{format_decimal(dias, 1)} dia{'s' if dias >= 2 else ''}"
                    if dias == dias else "sem venda recente")
        marca = {"critico": " 🔴", "atencao": " 🟡"}.get(r["status"], "")
        linhas.append(f"{ICONES_COMBUSTIVEL[prod]} {prod}: {format_litros(r['estoque'])} — {dias_txt}{marca}")
    return linhas


def _linhas_alertas(alertas: list[al.Alerta], posto: str | None = None, com_posto: bool = False) -> list[str]:
    lista = [a for a in alertas if a.nivel in ("critico", "atencao") and (posto is None or a.posto == posto)]
    saida = []
    for a in lista:
        onde = f"{_curto(a.posto)}: " if com_posto else ""
        texto = a.resumo[0].upper() + a.resumo[1:]
        saida.append(f"{a.icone} {onde}{texto}")
    return saida


# --------------------------------------------------------------- respostas ---
def _posto_resumo(df, tanques, posto, alertas, simulado) -> Resposta:
    dp = df[df["posto"] == posto]
    ref = an.ultima_data(df, posto)
    per = an.periodo(dp, ref.year, ref.month)
    ind = an.indicadores(df, per, posto)
    ant = ind["anterior"]
    dia = dp[dp["data"] == pd.Timestamp(ref)]
    est = an.estoque_atual(df, tanques, None, posto)
    linhas = [
        _cabecalho_periodo(per, simulado),
        "",
        f"💰 Vendas no mês: {format_brl_curto(ind['faturamento'])}{_variacao(ind['faturamento'], ant['faturamento'])}",
        f"⛽ Litros: {format_litros(ind['litros'])}{_variacao(ind['litros'], ant['litros'])}",
        f"📈 Margem bruta: {format_brl_curto(ind['margem'])} · {format_pct_simples(ind['margem_pct'], 1)} · "
        f"{format_rs_litro(ind['margem_litro'])}",
        f"🗓️ Dia {_data_curta(ref)}: {format_brl_curto(float(dia['faturamento'].sum()))} · "
        f"{format_litros(float(dia['vendas_l'].sum()))}",
        "",
        f"📦 Estoque (medição de {_data_curta(ref)})",
        *_linhas_estoque(est),
        "",
    ]
    problemas = _linhas_alertas(alertas, posto)
    linhas += problemas or ["🟢 Sem alertas neste posto."]
    if per.parcial:
        linhas.append(f"Comparação: mesmos dias de {nome_mes(per.anterior_inicio.month).lower()}.")
    return Resposta(f"📊 Resumo — {posto}", "\n".join(linhas), _sugestoes_posto(posto, "resumo"))


def _posto_estoque(df, tanques, posto, alertas, simulado) -> Resposta:
    ref = an.ultima_data(df, posto)
    est = an.estoque_atual(df, tanques, None, posto)
    total, cap = est["estoque"].sum(), est["capacidade"].sum()
    linhas = [f"📅 Medição de {_data_curta(ref)}" + (" · dados simulados" if simulado else ""),
              "⏱️ Autonomia pela venda média dos últimos 7 dias", "", *_linhas_estoque(est), "",
              f"Total: {format_litros(total)} · {format_pct_simples(total / cap * 100, 0)} da capacidade"]
    pior = est.sort_values("autonomia").iloc[0]
    if pior["status"] == "critico":
        linhas += ["", f"🔴 {pior['produto']} acaba em cerca de {format_decimal(pior['autonomia'], 1)} dia. "
                   "Confirme hoje a entrega com a distribuidora."]
    elif pior["status"] == "atencao":
        linhas += ["", f"🟡 Programe a reposição de {pior['produto']} "
                   f"({format_decimal(pior['autonomia'], 1)} dias)."]
    else:
        linhas += ["", "🟢 Todos os tanques com folga."]
    return Resposta(f"📦 Estoque — {posto}", "\n".join(linhas), _sugestoes_posto(posto, "estoque"))


def _posto_vendas(df, tanques, posto, alertas, simulado) -> Resposta:
    dp = df[df["posto"] == posto]
    ref = an.ultima_data(df, posto)
    per = an.periodo(dp, ref.year, ref.month)
    ind = an.indicadores(df, per, posto)
    comb = an.por_combustivel(df, per, posto)
    dia = dp[dp["data"] == pd.Timestamp(ref)]
    linhas = [_cabecalho_periodo(per, simulado), "",
              f"💰 Faturamento: {format_brl(ind['faturamento'], 0)}"
              f"{_variacao(ind['faturamento'], ind['anterior']['faturamento'])}",
              f"⛽ Litros: {format_litros(ind['litros'])}{_variacao(ind['litros'], ind['anterior']['litros'])}",
              f"🏷️ Preço médio: {format_rs_litro(ind['preco_medio'], 3)}",
              f"🗓️ Dia {_data_curta(ref)}: {format_brl(float(dia['faturamento'].sum()), 0)} · "
              f"{format_litros(float(dia['vendas_l'].sum()))}", "", "Por combustível no mês:"]
    for _, r in comb.iterrows():
        linhas.append(f"{ICONES_COMBUSTIVEL[r['produto']]} {r['produto']}: {format_litros(r['litros'])} · "
                      f"{format_pct_simples(r['participacao'], 0)}")
    return Resposta(f"💰 Vendas — {posto}", "\n".join(linhas), _sugestoes_posto(posto, "vendas"))


def _posto_margem(df, tanques, posto, alertas, simulado) -> Resposta:
    dp = df[df["posto"] == posto]
    ref = an.ultima_data(df, posto)
    per = an.periodo(dp, ref.year, ref.month)
    ind = an.indicadores(df, per, posto)
    hist = an.media_12_meses(df, per, posto)
    comb = an.por_combustivel(df, per, posto)
    dif = ind["margem_pct"] - hist["margem_pct"]
    comparacao = ("= na média dos 12 meses" if abs(dif) < 0.05 else
                  f"{'▲' if dif > 0 else '▼'} {format_decimal(abs(dif), 1)} p.p. vs média de 12 meses "
                  f"({format_pct_simples(hist['margem_pct'], 1)})")
    linhas = [_cabecalho_periodo(per, simulado), "",
              f"📈 Margem bruta: {format_brl(ind['margem'], 0)}",
              f"％ {format_pct_simples(ind['margem_pct'], 1)} do faturamento · {comparacao}",
              f"🧮 Por litro: {format_rs_litro(ind['margem_litro'])} "
              f"(preço {format_rs_litro(ind['preco_medio'])} − custo {format_rs_litro(ind['custo_medio'])})",
              "", "Margem por litro:"]
    for _, r in comb.iterrows():
        linhas.append(f"{ICONES_COMBUSTIVEL[r['produto']]} {r['produto']}: {format_rs_litro(r['margem_litro'])} · "
                      f"{format_pct_simples(r['margem_pct'], 1)}")
    problemas = [l for l in _linhas_alertas(alertas, posto) if "margem" in l.lower()]
    if problemas:
        linhas += ["", *problemas]
    return Resposta(f"📈 Margem — {posto}", "\n".join(linhas), _sugestoes_posto(posto, "margem"))


def _rede_resumo(df, tanques, postos, alertas, simulado) -> Resposta:
    ref = df["data"].max().date()
    per = an.periodo(df, ref.year, ref.month)
    ind = an.indicadores(df, per)
    ant = ind["anterior"]
    est = an.estoque_atual(df, tanques)
    linhas = [_cabecalho_periodo(per, simulado), "",
              f"💰 Vendas no mês: {format_brl_curto(ind['faturamento'])}{_variacao(ind['faturamento'], ant['faturamento'])}",
              f"⛽ Litros: {format_litros(ind['litros'])}{_variacao(ind['litros'], ant['litros'])}",
              f"📈 Margem bruta: {format_brl_curto(ind['margem'])} · {format_pct_simples(ind['margem_pct'], 1)} · "
              f"{format_rs_litro(ind['margem_litro'])}",
              f"🛢️ Estoque: {format_litros(est['estoque'].sum())} · "
              f"{format_decimal(est['estoque'].sum() / est['media_dia'].sum(), 1)} dias", "", "Por posto:"]
    t = an.por_posto(df, per, postos)
    for _, r in t.iterrows():
        situ = al.situacao_posto(alertas, r["posto"])
        linhas.append(f"{ICONE_SITUACAO[situ]} {_curto(r['posto'])}: {format_brl_curto(r['faturamento'])} · "
                      f"margem {format_pct_simples(r['margem_pct'], 1)}")
    criticos = [a for a in alertas if a.nivel == "critico"]
    if criticos:
        linhas += ["", f"🔴 {len(criticos)} ponto{'s' if len(criticos) > 1 else ''} exige"
                   f"{'m' if len(criticos) > 1 else ''} ação — toque em 🚨 Alertas."]
    sug = (("📦 Estoque da rede", "estoque rede"), ("🚨 Alertas", "alertas"))
    return Resposta("🏪 Rede B2 — resumo", "\n".join(linhas), sug)


def _rede_estoque(df, tanques, postos, alertas, simulado) -> Resposta:
    est = an.estoque_atual(df, tanques)
    linhas = [f"📅 Última medição de cada posto" + (" · dados simulados" if simulado else ""), ""]
    g = est.groupby("produto", observed=True).agg(estoque=("estoque", "sum"), media=("media_dia", "sum"))
    for prod, r in g.iterrows():
        linhas.append(f"{ICONES_COMBUSTIVEL[str(prod)]} {prod}: {format_litros(r['estoque'])} — "
                      f"{format_decimal(r['estoque'] / r['media'], 1)} dias")
    risco = est[est["status"] != "ok"].sort_values("autonomia")
    linhas += ["", "Tanques em risco:" if len(risco) else "🟢 Nenhum tanque em risco."]
    for _, r in risco.iterrows():
        linhas.append(f"{ICONE_SITUACAO[r['status']]} {_curto(r['posto'])} · {r['produto']}: "
                      f"{format_decimal(r['autonomia'], 1)} dia{'s' if r['autonomia'] >= 2 else ''}")
    sug = tuple((f"📦 {_curto(p)}", f"estoque {p}") for p in risco["posto"].unique()[:3]) + (("🚨 Alertas", "alertas"),)
    return Resposta("📦 Estoque — Rede B2", "\n".join(linhas), sug)


def _rede_vendas(df, tanques, postos, alertas, simulado) -> Resposta:
    ref = df["data"].max().date()
    per = an.periodo(df, ref.year, ref.month)
    t = an.por_posto(df, per, postos).sort_values("faturamento", ascending=False)
    ind = an.indicadores(df, per)
    linhas = [_cabecalho_periodo(per, simulado), "",
              f"💰 Rede: {format_brl_curto(ind['faturamento'])} · {format_litros(ind['litros'])}", "",
              "Ranking de faturamento:"]
    for i, (_, r) in enumerate(t.iterrows(), 1):
        linhas.append(f"{i}º {_curto(r['posto'])}: {format_brl_curto(r['faturamento'])} · "
                      f"{format_litros(r['litros'])}{_variacao(r['litros'], r['litros_ant'])}")
    return Resposta("💰 Vendas — Rede B2", "\n".join(linhas), (("📈 Margem da rede", "margem rede"),))


def _rede_margem(df, tanques, postos, alertas, simulado) -> Resposta:
    ref = df["data"].max().date()
    per = an.periodo(df, ref.year, ref.month)
    t = an.por_posto(df, per, postos).sort_values("margem_litro", ascending=False)
    ind = an.indicadores(df, per)
    linhas = [_cabecalho_periodo(per, simulado), "",
              f"📈 Rede: {format_brl_curto(ind['margem'])} · {format_pct_simples(ind['margem_pct'], 1)} · "
              f"{format_rs_litro(ind['margem_litro'])}", "", "Onde ganhamos mais (por litro):"]
    for i, (_, r) in enumerate(t.iterrows(), 1):
        linhas.append(f"{i}º {_curto(r['posto'])}: {format_rs_litro(r['margem_litro'])} · "
                      f"{format_brl_curto(r['margem'])}")
    caidas = [l for l in _linhas_alertas(alertas, com_posto=True) if "margem" in l.lower()]
    if caidas:
        linhas += ["", "Onde a margem caiu:", *caidas]
    return Resposta("📈 Margem — Rede B2", "\n".join(linhas), (("🚨 Alertas", "alertas"),))


def _alertas(df, tanques, postos, alertas, simulado, posto: str | None = None) -> Resposta:
    if posto:
        alertas = [a for a in alertas if a.posto == posto]
    ref = df["data"].max().date()
    criticos = _linhas_alertas([a for a in alertas if a.nivel == "critico"], com_posto=True)
    atencao = _linhas_alertas([a for a in alertas if a.nivel == "atencao"], com_posto=True)
    destaques = [a for a in alertas if a.nivel == "destaque"]
    linhas = [f"📅 Dados até {_data_curta(ref)}" + (" · dados simulados" if simulado else ""), ""]
    if not (criticos or atencao):
        linhas.append("🟢 Rede sem pontos de atenção.")
    if criticos:
        linhas += ["EXIGE AÇÃO", *criticos, ""]
    if atencao:
        linhas += ["MERECE ATENÇÃO", *atencao, ""]
    if destaques:
        linhas += ["DESTAQUES", *[f"🟢 {_curto(a.posto)}: {a.resumo[0].upper() + a.resumo[1:]}" for a in destaques]]
    postos_criticos = list(dict.fromkeys(a.posto for a in alertas if a.nivel == "critico"))
    sug = tuple((f"⛽ {_curto(p)}", f"resumo {p}") for p in postos_criticos[:3]) + (("🏪 Rede", "resumo rede"),)
    return Resposta(f"🚨 Alertas — {posto or 'Rede B2'}", "\n".join(linhas).strip(), sug)


def _texto_ajuda(postos: list[str], entendeu: bool = True) -> str:
    nomes = ", ".join(_curto(p) for p in postos)
    abertura = "Oi! Sou o assistente da Rede B2." if entendeu else "Não entendi. 🙂 Tente assim:"
    return "\n".join([
        abertura, "",
        "📊 resumo centro", "📦 estoque candói", "💰 vendas primavera", "📈 margem bonsucesso",
        "🏪 resumo rede   ·   🚨 alertas",
        "📋 reunião   ·   🛡️ auditoria   ·   ⏳ pendências", "",
        f"Postos: {nomes}.", "Ou toque nos botões abaixo.",
    ])


def _sugestoes_posto(posto: str, atual: str) -> tuple:
    opcoes = (("📊 Resumo", "resumo"), ("📦 Estoque", "estoque"), ("💰 Vendas", "vendas"), ("📈 Margem", "margem"))
    return tuple((rotulo, f"{acao} {posto}") for rotulo, acao in opcoes if acao != atual)


RESPOSTAS_POSTO = {"resumo": _posto_resumo, "estoque": _posto_estoque, "vendas": _posto_vendas,
                   "margem": _posto_margem}
RESPOSTAS_REDE = {"resumo": _rede_resumo, "estoque": _rede_estoque, "vendas": _rede_vendas,
                  "margem": _rede_margem, "alertas": _alertas}


def pendencias(df: pd.DataFrame, postos: list[str], referencia=None) -> list[tuple[str, object, int]]:
    """Postos cujo último dado está antes de `referencia` (padrão: o posto mais
    adiantado da rede). Devolve (posto, último dia, dias de atraso)."""
    ref = pd.Timestamp(referencia) if referencia is not None else df["data"].max()
    saida = []
    for p in postos:
        g = df[df["posto"] == p]
        ultima = g["data"].max() if len(g) else None
        atraso = (ref - ultima).days if ultima is not None else 99
        if atraso >= 1:
            saida.append((p, ultima, atraso))
    return saida


def _pendencias(df, postos, simulado, referencia=None) -> Resposta:
    pend = pendencias(df, postos, referencia)
    ref = pd.Timestamp(referencia) if referencia is not None else df["data"].max()
    linhas = [f"📅 Esperado: dados até {ref:%d/%m}" + (" · dados simulados" if simulado else ""), ""]
    if not pend:
        linhas.append("🟢 Todos os postos estão em dia.")
    for p, ultima, atraso in pend:
        quando = f"último dado de {ultima:%d/%m}" if ultima is not None else "nenhuma planilha"
        linhas.append(f"{'🔴' if atraso >= 2 else '🟡'} {_curto(p)}: {quando} ({atraso} dia{'s' if atraso > 1 else ''})")
    em_dia = [_curto(p) for p in postos if p not in {x[0] for x in pend}]
    if pend and em_dia:
        linhas += ["", f"🟢 Em dia: {', '.join(em_dia)}."]
    return Resposta("⏳ Planilhas pendentes" if pend else "✅ Planilhas em dia", "\n".join(linhas))


def _reuniao(df, postos, simulado, extras) -> Resposta:
    from src import reuniao
    ref = df["data"].max().date()
    per = an.periodo(df, ref.year, ref.month)
    p = reuniao.placar(df, extras.get("despesas"), extras.get("envios"), extras.get("auditoria"), per, postos)
    texto = reuniao.texto_placar(p, per) + ("\n\nDados simulados." if simulado else "")
    return Resposta("📋 Placar das gerências", texto, (("🚨 Alertas", "alertas"), ("🛡️ Auditoria", "auditoria")))


def _auditoria(df, postos, simulado, extras, posto=None) -> Resposta:
    from src import antifraude
    sinais = antifraude.sinais(df, extras.get("compras"), extras.get("auditoria"), postos)
    if posto:
        sinais = [s for s in sinais if s.posto == posto]
    linhas = [f"📅 Mês em foco até {df['data'].max():%d/%m}" + (" · dados simulados" if simulado else ""), ""]
    if not sinais:
        linhas.append("🟢 Nenhum sinal de fraude para conferir.")
    for s in sinais[:8]:
        linhas.append(f"{s.icone} {_curto(s.posto)} — {s.titulo}")
        linhas.append(f"    {s.detalhe}")
    if len(sinais) > 8:
        linhas += ["", f"… e mais {len(sinais) - 8} no painel (🛡️ Auditoria)."]
    return Resposta(f"🛡️ Auditoria — {posto or 'Rede B2'}", "\n".join(linhas), (("🚨 Alertas", "alertas"),))


def responder(comando: str, df: pd.DataFrame, tanques: pd.DataFrame, postos: list[str],
              simulado: bool = True, alertas: list[al.Alerta] | None = None,
              extras: dict | None = None) -> Resposta:
    """Consulta a base sem modificá-la. Texto não entendido -> ValueError com a ajuda.

    `extras` traz o que só algumas respostas usam: despesas, envios, compras e
    a trilha de auditoria (placar da reunião, auditoria)."""
    acao, posto = entender(comando, postos)
    extras = extras or {}
    if acao == "ajuda":
        return Resposta("🤖 B2 Gestão", _texto_ajuda(postos),
                        (("🏪 Resumo da rede", "resumo rede"), ("🚨 Alertas", "alertas")))
    if df is None or df.empty:
        return Resposta("🤖 B2 Gestão", "Ainda não há dados na base. Envie as planilhas dos postos.")
    if posto is not None and df[df["posto"] == posto].empty:
        return Resposta(f"⛽ {posto}", f"{posto}: ainda não há planilha deste posto na base.")
    if acao == "pendencias":
        return _pendencias(df, postos, simulado, extras.get("referencia"))
    if acao == "reuniao":
        return _reuniao(df, postos, simulado, extras)
    if acao == "auditoria":
        return _auditoria(df, postos, simulado, extras, posto)
    if alertas is None:
        alertas = al.gerar(df, tanques, postos, auditoria=extras.get("auditoria"))
    if acao == "alertas":
        return _alertas(df, tanques, postos, alertas, simulado, posto)
    if posto is None:
        return RESPOSTAS_REDE[acao](df, tanques, postos, alertas, simulado)
    return RESPOSTAS_POSTO[acao](df, tanques, posto, alertas, simulado)
