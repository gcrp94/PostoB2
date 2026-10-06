"""B2 Gestão — painel da Rede B2 Postos.

    streamlit run app.py        (ou duplo clique em "Abrir Painel.bat")

Este arquivo só ORQUESTRA: login, menu e o corpo de cada tela. As contas
estão em `src/analytics.py`, as regras de alerta em `src/alertas.py`, os
gráficos em `src/charts.py` e as peças visuais em `src/ui.py` — a mesma
separação do Painel de Finanças.

O painel lê a base Parquet (`data/base/`), nunca o Excel direto.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent
st.set_page_config(page_title="B2 Gestão — Rede B2 Postos", page_icon=str(RAIZ / "assets" / "favicon.png"),
                   layout="wide", initial_sidebar_state="auto")   # "auto": recolhida no celular

# Atualização na nuvem: o Streamlit Cloud troca os arquivos mas mantém o processo vivo, e os módulos `src.*` da versão
# anterior ficam na memória — o app.py novo quebrava com "AttributeError: ... has no attribute" (06/10/2026). Quando algum
# src/*.py mudou (ou na 1ª rodada deste arquivo), os módulos são descartados e reimportados já da versão nova.
ESTAMPA_SRC = max((p.stat().st_mtime_ns for p in (RAIZ / "src").glob("*.py")), default=0)
if getattr(sys, "_b2_estampa_src", None) != ESTAMPA_SRC:
    for _nome in [n for n in sys.modules if n == "src" or n.startswith("src.")]:
        del sys.modules[_nome]
    sys._b2_estampa_src = ESTAMPA_SRC

from src import alertas as al  # noqa: E402
from src import analytics as an  # noqa: E402
from src import armazenamento as arm  # noqa: E402
from src import assistente_ui  # noqa: E402
from src import equilibrio_ui, radar_ui  # noqa: E402
from src import antifraude, auditoria, auth, base, charts, descontos, notificacoes, reuniao, theme, ui, validacao  # noqa: E402
from src.formatting import (  # noqa: E402
    format_brl, format_brl_curto, format_decimal, format_int, format_litros, format_litros_curto, format_pct,
    format_pct_simples, format_rs_litro, nome_mes,
)

ui.injetar_css()      # visual único (o "painel antigo" foi removido em 06/10/2026)

# Botão "Preço planilha | Preço sistema" (menu lateral): qual custo do combustível entra em TODAS as contas.
# Planilha = o que o posto paga, com o desconto do boleto (padrão); sistema = o preço cheio da nota (planilha + desconto).
CUSTO = st.session_state.get("custo_modo", "planilha")
if CUSTO not in an.MODOS_CUSTO:
    CUSTO = "planilha"

# O robô do celular (Telegram/ntfy) liga ANTES do login: basta o Abrir App.bat
# abrir o navegador uma vez para ele começar a responder — o apresentador não
# precisa entrar no painel para a conversa pelo celular funcionar.
try:
    assistente_ui.iniciar_configurado()
except Exception:
    pass  # A tela do assistente mostra o problema; o painel nunca cai por causa dele.

usuario = auth.usuario_atual()
if usuario is None:
    auth.tela_login()
    st.stop()


# =============================================================== dados ======
@st.cache_data(show_spinner="Carregando a base da rede…")
def carregar(assinatura: tuple, custo: str) -> dict:
    b = base.carregar()
    tabela = descontos.carregar()
    df = an.preparar(b.movimento, b.compras, tabela, custo)
    ordem = [p for p in theme.POSTOS if p in set(b.postos["posto"])] + \
            [p for p in b.postos["posto"] if p not in theme.POSTOS]
    aud = auditoria.ler()
    return {"df": df, "compras": b.compras, "despesas": b.despesas, "descontos": tabela, "postos": b.postos.set_index("posto"),
            "tanques": b.tanques, "info": b.info, "ordem": ordem, "auditoria": aud,
            "envios": arm.ler_envios(), "alertas": al.gerar(df, b.tanques, ordem, auditoria=aud)}


if not (base.PASTA_BASE / "movimento.parquet").exists():
    ui.topo("B2 Gestão", "A base ainda não foi montada.")
    st.warning("Rode o **Atualizar Dados.bat** (ou `python gerar_base.py`) para montar a base a partir "
               "das planilhas. Para a apresentação, o **Gerar Dados Simulados.bat** cria tudo.")
    st.stop()

D = carregar((assistente_ui.assinatura_dados(), descontos.assinatura(), ESTAMPA_SRC), CUSTO)
DF: pd.DataFrame = D["df"]
POSTOS: list[str] = D["ordem"]
ALERTAS: list[al.Alerta] = D["alertas"]
ULTIMA = DF["data"].max().date()
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def grafico(fig):
    st.plotly_chart(fig, width="stretch", config=charts.CFG)


def tendencia(coluna: str, posto: str | None = None, dias: int = 30):
    """Série diária dos últimos `dias` — a miniatura dos cartões."""
    fim = an.ultima_data(DF, posto) if posto else ULTIMA
    inicio = fim - timedelta(days=dias - 1)
    if coluna == "estoque":
        g = an.recorte(DF, inicio, fim, posto)
        return g.groupby("data")["estoque_final"].sum().tolist()
    s = an.serie_diaria(DF, inicio, fim, posto, por_produto=False)
    return s[coluna].tolist()


ICONES_MENU = {"🎯": "dashboard", "🏠": "monitoring", "📋": "groups", "⛽": "local_gas_station",
               "📤": "upload_file", "🔔": "notifications", "🛡": "shield", "📑": "history", "📡": "radar",
               "💬": "smart_toy", "⚙": "settings"}


POSTO_EM_FOCO = "B2 Centro"      # o 1º a ser construído com os dados do Linx: vai ao topo do menu


def rotulo_menu(item: str, etiquetas: bool = False) -> str:
    """O emoji do menu vira ícone de traço único. `etiquetas`: o grupo Painéis marca o que ainda será construído."""
    icone = ICONES_MENU.get(item.split(" ", 1)[0].replace("️", ""))
    texto = f":material/{icone}: {ui.sem_emoji(item)}" if icone else item
    if etiquetas:
        # "(construir)" vai em itálico: o CSS do menu lateral o deixa claro e miúdo (o cinza do Streamlit some no fundo azul).
        texto += " :orange[(Em Construção)]" if item == f"⛽ {POSTO_EM_FOCO}" else " *(construir)*"
    return texto


def grade_alertas(lista, prefixo: str, acao, mostrar_posto: bool = True):
    """Os cartões de alerta com o botão de ação. `acao(a)` devolve
    (rótulo, função, argumentos) — rótulo None = sem botão. Linhas que abrem, com o botão ao lado."""
    for i, a in enumerate(lista):
        rotulo, funcao, args = acao(a)
        chave = f"{prefixo}_{i}_{a.chave}"
        with st.container():
            if rotulo:
                c1, c2 = st.columns([5, 1.5], vertical_alignment="center")
                with c1:
                    ui.md(ui.alerta_html(a, mostrar_posto))
                with c2:
                    st.button(rotulo, key=chave, type="tertiary", on_click=funcao, args=args)
            else:
                ui.md(ui.alerta_html(a, mostrar_posto))


def acao_abrir_posto(a):
    return rotulo_abrir(a), ir_para, (f"⛽ {a.posto}", a.aba, a.posto)


PAGINA_AUDITORIA = "🛡️ Auditoria"
PAGINA_REUNIAO = "📋 Reunião de Gerentes"
PAGINA_RADAR = "📡 Radar de Mercado"


def rotulo_abrir(a) -> str:
    if a.aba == "Auditoria":
        return "Ver na Auditoria →" if usuario.ve_rede else "Avisado ao proprietário"
    return f"Abrir {a.posto} · {a.aba} →"


def ir_para(pagina: str, aba: str | None = None, posto: str | None = None):
    """Callback dos botões "Abrir →": troca o menu e a aba antes do rerun.
    Alerta de auditoria não abre o posto: abre a tela de Auditoria."""
    if aba == "Auditoria" and usuario.ve_rede:
        st.session_state["menu_gestao"] = PAGINA_AUDITORIA
        st.session_state["menu_paineis"] = None
        return
    if usuario.ve_rede:
        st.session_state["menu_paineis"] = pagina
        st.session_state["menu_gestao"] = None
    else:
        st.session_state["menu_gerente"] = pagina
    if aba and posto:
        st.session_state[f"aba_{posto}"] = aba


def rotulo_comparacao(per: an.Periodo) -> str:
    mes_ant = nome_mes(per.anterior_inicio.month, curto=True)
    if per.parcial:
        return f"vs 1–{per.anterior_fim.day} de {mes_ant}"
    return f"vs {nome_mes(per.anterior_inicio.month, per.anterior_inicio.year, curto=True)}"


def texto_periodo(per: an.Periodo) -> str:
    base_txt = nome_mes(per.mes, per.ano)
    return f"{base_txt} até {per.fim:%d/%m}" if per.parcial else base_txt


def seletor_periodo(df: pd.DataFrame, chave: str = "periodo") -> an.Periodo:
    meses = an.meses_disponiveis(df)[::-1]
    rotulos = {}
    for a, m in meses:
        p = an.periodo(df, a, m)
        rotulos[(a, m)] = nome_mes(m, a) + (f" · até {p.fim:%d/%m}" if p.parcial else "")
    atual = st.session_state.get("_periodo", meses[0])
    if atual not in meses:
        atual = meses[0]
    escolha = st.selectbox("Período", meses, index=meses.index(atual), format_func=lambda x: rotulos[x],
                           key=chave)
    st.session_state["_periodo"] = escolha
    return an.periodo(df, *escolha)


def botao_custo():
    """"(●) Preço planilha  ( ) Preço sistema": seletor de bolinhas, sem legenda. O que está marcado vale para TODA conta de
    custo e LB do painel (margens, equilíbrio, perdas, alertas, notas de compra…)."""
    def _mudou():
        escolha = st.session_state.get("_rad_custo")
        if escolha in an.MODOS_CUSTO:
            st.session_state["custo_modo"] = escolha

    st.session_state["_rad_custo"] = CUSTO
    with st.container(key="botao_custo"):
        st.radio("Custo do combustível", list(an.MODOS_CUSTO), key="_rad_custo", horizontal=True,
                 format_func=lambda m: an.MODOS_CUSTO[m], on_change=_mudou, label_visibility="collapsed")


def cabecalho(titulo: str, sub: str, com_periodo: bool = True, selo: str | None = None,
              df: pd.DataFrame | None = None, botao: bool = True) -> an.Periodo | None:
    """O alto da tela. `botao`: o "Preço planilha | Preço sistema" (o posto o põe ao lado das abas, não aqui)."""
    if not com_periodo:
        ui.topo(titulo, sub, selo)
        if botao:
            botao_custo()
        return None
    c1, c2 = st.columns([3.2, 1], vertical_alignment="bottom")
    with c1:
        ui.topo(titulo, sub, selo)
    with c2:
        per = seletor_periodo(DF if df is None else df)
    if botao:
        botao_custo()
    return per


def quando_txt(momento) -> str:
    if momento is None or pd.isna(momento):
        return "—"
    m = pd.Timestamp(momento)
    hoje = date.today()
    if m.date() == hoje:
        return f"hoje às {m:%H:%M}"
    if (hoje - m.date()).days == 1:
        return f"ontem às {m:%H:%M}"
    return f"{m:%d/%m} às {m:%H:%M}"


# ============================================================ lateral =======
def lateral():
    with st.sidebar:
        ui.md('<div class="lateral-marca">'
              f'<img src="data:image/png;base64,{ui.logo_base64()}">'
              '<div><div class="t1">B2 Gestão</div><div class="t2">REDE B2 POSTOS</div></div></div>')
        onde = "toda a rede" if usuario.ve_rede else usuario.posto
        ui.md(f'<div class="lateral-usuario"><div class="ola">Olá, {ui.esc(usuario.nome)}</div>'
              f'<div class="perfil">{usuario.perfil_nome} · <b>{ui.esc(onde)}</b></div></div>')

        if usuario.ve_rede:
            # O posto em foco (B2 Centro) abre a lista: é por ele que o painel está sendo construído com o Linx.
            em_foco = [f"⛽ {p}" for p in POSTOS if p == POSTO_EM_FOCO]
            paineis = em_foco + ["🎯 Central do Proprietário", "🏠 Visão da Rede", PAGINA_REUNIAO] + \
                      [f"⛽ {p}" for p in POSTOS if p != POSTO_EM_FOCO]
            n_alertas = sum(a.nivel in ("critico", "atencao") for a in ALERTAS)
            gestao = ["📤 Alimentar dados", f"🔔 Alertas ({n_alertas})", PAGINA_AUDITORIA, PAGINA_RADAR, "📑 Atualizações",
                      "💬 B2 Assistente", "⚙️ Administração"]
            st.session_state.setdefault("menu_paineis", paineis[0])
            st.session_state.setdefault("menu_gestao", None)
            # O rótulo dos alertas muda com a contagem: realinha a escolha salva.
            if st.session_state["menu_gestao"] and st.session_state["menu_gestao"].startswith("🔔"):
                st.session_state["menu_gestao"] = gestao[1]
            # Item que mudou de grupo (o B2 Assistente saiu de "Painéis"): a
            # escolha guardada na sessão vai junto, senão o rádio recebe um
            # valor que não está nas opções dele.
            if st.session_state["menu_paineis"] not in paineis + [None]:
                antigo = st.session_state["menu_paineis"]
                st.session_state["menu_paineis"] = None if antigo in gestao else paineis[0]
                if antigo in gestao:
                    st.session_state["menu_gestao"] = antigo
            if st.session_state["menu_gestao"] not in gestao + [None]:
                st.session_state["menu_gestao"] = None
                if st.session_state["menu_paineis"] is None:
                    st.session_state["menu_paineis"] = paineis[0]
            ui.md('<div class="lateral-rotulo">Painéis</div>')
            st.radio("Painéis", paineis, key="menu_paineis", label_visibility="collapsed",
                     format_func=lambda i: rotulo_menu(i, etiquetas=True),
                     on_change=lambda: st.session_state.update(menu_gestao=None))
            ui.md('<div class="lateral-rotulo">Gestão</div>')
            st.radio("Gestão", gestao, key="menu_gestao", label_visibility="collapsed",
                     format_func=rotulo_menu, on_change=lambda: st.session_state.update(menu_paineis=None))
            pagina = st.session_state["menu_paineis"] or st.session_state["menu_gestao"] or paineis[0]
        else:
            opcoes = ["⛽ Meu Posto", "📤 Enviar Planilha", "📑 Meus Envios"]
            st.session_state.setdefault("menu_gerente", opcoes[0])
            ui.md('<div class="lateral-rotulo">Menu</div>')
            st.radio("Menu", opcoes, key="menu_gerente", label_visibility="collapsed", format_func=rotulo_menu)
            pagina = st.session_state["menu_gerente"]

        st.divider()
        gerado = D["info"].get("gerado_em", "")
        gerado_txt = f"<br>base montada em {datetime.fromisoformat(gerado):%d/%m às %H:%M}" if gerado else ""
        demo = "<br><b style='color:#ffb48f'>Dados simulados para apresentação</b>" if auth.modo_demo() else ""
        ui.md(f'<div class="lateral-rodape">Dados até <b>{ULTIMA:%d/%m/%Y}</b>{gerado_txt}{demo}</div>')
        if st.button("Sair", use_container_width=True):
            auth.sair()
    return pagina


# ============================================================ central =======
def pagina_central():
    hoje = date.today()
    ui.topo("🎯 Central do Proprietário",
            f"{DIAS_SEMANA[hoje.weekday()].capitalize()}, {hoje:%d/%m/%Y} · dados da rede até "
            f"<b>{ULTIMA:%d/%m/%Y}</b>")
    botao_custo()
    criticos = [a for a in ALERTAS if a.nivel == "critico"]
    atencao = [a for a in ALERTAS if a.nivel == "atencao"]
    destaques = [a for a in ALERTAS if a.nivel == "destaque"]
    if criticos:
        frase = f"Hoje sua rede pede ação em {len(criticos)} ponto{'s' if len(criticos) > 1 else ''}."
    elif atencao:
        frase = f"Hoje sua rede está normal, com {len(atencao)} ponto{'s' if len(atencao) > 1 else ''} de atenção."
    else:
        frase = "Hoje sua rede está normal."
    postos_alerta = {a.posto for a in criticos + atencao}
    ui.md('<div class="central-hero">'
          f'<div class="h-data">Rede B2 · {len(POSTOS)} postos</div><div class="h-frase">{frase}</div>'
          '<div class="h-cont">'
          f'<div class="h-item"><b>{len(criticos)}</b> 🔴 exigem ação</div>'
          f'<div class="h-item"><b>{len(atencao)}</b> 🟡 merecem atenção</div>'
          f'<div class="h-item"><b>{len(destaques)}</b> 🟢 destaques</div>'
          f'<div class="h-item"><b>{len(POSTOS) - len(postos_alerta)}</b> de {len(POSTOS)} postos sem alerta</div>'
          '</div></div>')

    per = an.periodo(DF, ULTIMA.year, ULTIMA.month)
    ind = an.indicadores(DF, per)
    ant = ind["anterior"]
    est = an.estoque_atual(DF, D["tanques"])
    comp = rotulo_comparacao(per)
    aut_rede = est["estoque"].sum() / est["media_dia"].sum()
    ui.secao("O mês até agora", f"{texto_periodo(per)} · comparação com os mesmos dias do mês anterior")
    ui.grade_kpis([
        ui.kpi("Faturamento", format_brl_curto(ind["faturamento"]),
               ui.delta_html(_var(ind["faturamento"], ant["faturamento"])) + comp, "💰",
               spark=tendencia("faturamento")),
        ui.kpi("Litros vendidos", format_litros_curto(ind["litros"]),
               ui.delta_html(_var(ind["litros"], ant["litros"])) + comp, "⛽", spark=tendencia("litros")),
        ui.kpi("LB · Lucro Bruto", format_brl_curto(ind["margem"]),
               f"{format_pct_simples(ind['margem_pct'], 1)} · {format_rs_litro(ind['margem_litro'])}", "📈",
               "destaque", spark=tendencia("margem")),
        ui.kpi("Estoque na rede", format_litros_curto(est["estoque"].sum()),
               f"≈ {format_decimal(aut_rede, 1)} dias de venda", "🛢️", spark=tendencia("estoque")),
    ])

    def lista(alertas_n, titulo, sub):
        if not alertas_n:
            return
        ui.secao(titulo, sub)
        grade_alertas(alertas_n, f"central_{titulo[:3]}", acao_abrir_posto)

    lista(criticos, "🔴 Exige ação", "Resolver hoje.")
    lista(atencao, "🟡 Merece atenção", "Olhar nesta semana.")
    lista(destaques, "🟢 Destaques", "O que está indo bem.")
    if not (criticos or atencao):
        st.success("Nenhum ponto de atenção na rede. 👏")

    ui.secao("📤 Envio das planilhas", "Quando cada posto mandou os dados pela última vez.")
    envio_cards()


def _var(atual, anterior):
    return (atual - anterior) / anterior * 100 if anterior else None


def envio_cards(postos: list[str] | None = None):
    envios = arm.ler_envios()
    status = arm.status_postos(envios, postos or POSTOS)
    cards = []
    for p, s in status.items():
        ultima = an.ultima_data(DF, p)
        atraso = (ULTIMA - ultima).days
        if s:
            classe = "ok" if atraso < al.DIAS_SEM_ENVIO else "atencao"
            icone = "✅" if classe == "ok" else "⚠️"
            det = f"por {ui.esc(s['usuario'])} · dados até {ultima:%d/%m}"
            linha = f"{icone} Atualizado {quando_txt(s['data_hora'])}"
            if classe == "atencao":
                linha = f"⚠️ Há {atraso} dias sem enviar"
                det = f"último envio {quando_txt(s['data_hora'])} · dados até {ultima:%d/%m}"
        else:
            classe, linha, det = "atencao", "⚠️ Nenhum envio registrado", f"dados até {ultima:%d/%m}"
        cards.append(f'<div class="envio"><div class="e-posto">⛽ {p}</div>'
                     f'<div class="e-status {classe}">{linha}</div><div class="e-det">{det}</div></div>')
    ui.md(f'<div class="envio-grid">{"".join(cards)}</div>')


# ============================================================ rede ==========
def pagina_rede():
    per = cabecalho("🏠 Visão da Rede",
                    f"{len(POSTOS)} postos · Guarapuava e Candói")
    ind = an.indicadores(DF, per)
    ant = ind["anterior"]
    comp = rotulo_comparacao(per)
    est = an.estoque_atual(DF, D["tanques"], per.fim)
    aut = est["estoque"].sum() / est["media_dia"].sum()
    pior = est.sort_values("autonomia").iloc[0]
    postos_alerta = sorted({a.posto for a in ALERTAS if a.nivel in ("critico", "atencao")},
                           key=POSTOS.index)
    tem_critico = any(a.nivel == "critico" for a in ALERTAS)
    ui.md(f'<div class="secao-sub">{texto_periodo(per)} · variações comparadas com os mesmos dias do mês '
          'anterior</div>')
    cartoes = {
        "volume": ui.kpi("Volume vendido no mês", format_litros(ind["litros"]),
                         ui.delta_html(_var(ind["litros"], ant["litros"])) + comp, "⛽",
                         spark=tendencia("litros")),
        "faturamento": ui.kpi("Faturamento", format_brl_curto(ind["faturamento"]),
                              ui.delta_html(_var(ind["faturamento"], ant["faturamento"])) + comp, "💰",
                              spark=tendencia("faturamento")),
        "margem": ui.kpi("LB · Lucro Bruto", format_brl_curto(ind["margem"]),
                         ui.delta_html(_var(ind["margem"], ant["margem"])) + comp, "📈", "destaque",
                         spark=tendencia("margem")),
        "margem_pct": ui.kpi("LB %", format_pct_simples(ind["margem_pct"], 2),
                             ui.delta_html(ind["margem_pct"] - ant["margem_pct"], tipo="pp") + comp, "％"),
        "margem_litro": ui.kpi("LB médio por litro", format_rs_litro(ind["margem_litro"]),
                               ui.delta_html(_var(ind["margem_litro"], ant["margem_litro"])) + comp, "🧮"),
        "estoque": ui.kpi("Estoque atual", format_litros(est["estoque"].sum()),
                          f"{len(est)} tanques · medição de {per.fim:%d/%m}", "🛢️", spark=tendencia("estoque")),
        "autonomia": ui.kpi("Autonomia estimada", f"{format_decimal(aut, 1)} dias",
                            f"menor: {pior['posto'].replace('B2 ', '')} · {pior['produto']} "
                            f"({format_decimal(pior['autonomia'], 1)} dia{'s' if pior['autonomia'] >= 2 else ''})",
                            "⏱️"),
        "atencao": ui.kpi("Postos em atenção", f"{len(postos_alerta)} de {len(POSTOS)}",
                          ", ".join(p.replace("B2 ", "") for p in postos_alerta) or "nenhum", "🚦",
                          "alerta-critico" if tem_critico else ("alerta-atencao" if postos_alerta else "")),
    }
    # Os quatro que o dono olha primeiro, grandes; o resto, leve, embaixo.
    ui.grade_kpis([cartoes[k] for k in ("faturamento", "volume", "margem", "atencao")])
    ui.grade_kpis([cartoes[k] for k in ("margem_pct", "margem_litro", "estoque", "autonomia")], compacto=True)

    # ---- quadro por unidade
    t = an.por_posto(DF, per, POSTOS)
    est_p = est.groupby("posto").agg(estoque=("estoque", "sum"), media=("media_dia", "sum"),
                                     cap=("capacidade", "sum"), pior=("autonomia", "min"))
    max_l = t["litros"].max()
    linhas = []
    for _, r in t.iterrows():
        p = r["posto"]
        e = est_p.loc[p]
        situ = al.situacao_posto(ALERTAS, p)
        info_p = D["postos"].loc[p]
        dias_txt = f"{format_decimal(e['estoque'] / e['media'], 1)} dias"
        linhas.append([
            f'<span class="unidade">{p}</span><span class="mini">{ui.esc(info_p["bairro"])} · '
            f'{ui.esc(info_p["cidade"])}</span>',
            ui.barra_celula(format_litros_curto(r["litros"]), r["litros"] / max_l, theme.COLORS["navy_ui"]),
            format_brl_curto(r["faturamento"]),
            format_brl_curto(r["margem"]),
            f'{format_pct_simples(r["margem_pct"], 1)}<span class="mini">'
            f'{ui.var_html(r["margem_pct"] - r["margem_pct_ant"], "pp")}</span>',
            format_rs_litro(r["margem_litro"]),
            f'{format_litros_curto(e["estoque"])}<span class="mini">{dias_txt}</span>',
            ui.pill(situ),
        ])
    tot_e = est_p["estoque"].sum()
    total = ["Rede", format_litros_curto(t["litros"].sum()), format_brl_curto(t["faturamento"].sum()),
             format_brl_curto(t["margem"].sum()), format_pct_simples(ind["margem_pct"], 1),
             format_rs_litro(ind["margem_litro"]), format_litros_curto(tot_e), ""]
    with st.container(border=True):
        ui.bloco_titulo("Quadro das unidades", f"{texto_periodo(per)} · LB % com a variação em pontos "
                        f"percentuais {rotulo_comparacao(per)}")
        ui.md(ui.tabela_html(
            [("Unidade", False), ("Litros vendidos", True), ("Faturamento", True), ("LB R$", True),
             ("LB %", True), ("LB/L", True), ("Estoque", True), ("Situação", False)],
            linhas, total))

    # ---- as quatro perguntas
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        melhor = t.loc[t["margem"].idxmax(), "posto"]
        ui.bloco_titulo("LB por posto", f"{texto_periodo(per)} · em laranja, o maior",
                        pergunta="Onde estamos ganhando mais?")
        t2 = t.assign(txt=[f"{format_brl_curto(m)} · {format_rs_litro(l)}" for m, l in zip(t["margem"], t["margem_litro"])])
        grafico(charts.barras_postos(t2, "margem", "txt", 260, destaque=melhor))
    with c2, st.container(border=True):
        ui.bloco_titulo("LB por litro: mês × média de 12 meses",
                        "Ponto cinza = média dos 12 meses anteriores · ponto colorido = mês atual",
                        pergunta="Onde o LB caiu?")
        hal = pd.DataFrame([{"posto": p, "hist": an.media_12_meses(DF, per, p)["margem_litro"],
                             "atual": t.set_index("posto").loc[p, "margem_litro"]} for p in POSTOS])
        grafico(charts.halteres_margem(hal, 260))
    c3, c4 = st.columns(2)
    with c3, st.container(border=True):
        ui.bloco_titulo("Estoque da rede por combustível", f"Medição de {per.fim:%d/%m} · em dias da venda média",
                        pergunta="Quanto combustível temos?")
        grafico(charts.estoque_rede(est, 230))
    with c4, st.container(border=True):
        ui.bloco_titulo("Autonomia de cada tanque, em dias",
                        f"Crítico abaixo de {format_decimal(an.AUTONOMIA_CRITICA, 1)} dia · atenção abaixo de "
                        f"{format_decimal(an.AUTONOMIA_ATENCAO, 1)} dias",
                        pergunta="Qual posto corre risco de ficar sem produto?")
        ui.md(matriz_autonomia(est))

    # ---- evolução
    ui.secao("Evolução da rede — últimos 12 meses",
             "* mês em andamento · clique na legenda para isolar um combustível")
    s_prod = an.serie_mensal(DF, por_produto=True)
    s = an.serie_mensal(DF)
    parcial = (ULTIMA.year, ULTIMA.month) if an.periodo(DF, ULTIMA.year, ULTIMA.month).parcial else None
    c5, c6 = st.columns(2)
    with c5, st.container(border=True):
        ui.bloco_titulo("Volume vendido por combustível", "Litros por mês")
        grafico(charts.mensal_empilhado(s_prod, parcial, 300))
    with c6, st.container(border=True):
        ui.bloco_titulo("LB por mês", f"Em destaque, {nome_mes(per.mes, per.ano)}")
        grafico(charts.mensal_barras(s, "margem", "brl", (per.ano, per.mes), parcial, 300))


def matriz_autonomia(est: pd.DataFrame) -> str:
    cab = "".join(f'<th style="text-align:center">{theme.ICONES_COMBUSTIVEL[p]} {theme.ROTULO_CURTO[p]}</th>'
                  for p in theme.COMBUSTIVEIS)
    corpo = []
    for p in POSTOS:
        g = est[est["posto"] == p].set_index("produto")
        celulas = []
        for prod in theme.COMBUSTIVEIS:
            if prod not in g.index:
                celulas.append("<td></td>")
                continue
            r = g.loc[prod]
            dias = r["autonomia"]
            celulas.append(f'<td class="cel {r["status"]}" title="{format_litros(r["estoque"])}">'
                           f'{format_decimal(dias, 1)} d<small>{format_pct_simples(r["pct"], 0)} do tanque</small></td>')
        corpo.append(f'<tr><td class="unidade" style="white-space:nowrap;font-weight:700">'
                     f'{p.replace("B2 ", "")}</td>{"".join(celulas)}</tr>')
    return (f'<div class="tabela-wrap"><table class="tabela matriz"><thead><tr><th></th>{cab}</tr></thead>'
            f'<tbody>{"".join(corpo)}</tbody></table></div>'
            f'<div class="nota" style="margin-top:.4rem">■ vermelho: crítico · ▲ âmbar: atenção · '
            f'● verde: normal. Autonomia = estoque ÷ média de venda dos últimos 7 dias.</div>')


# ============================================================ posto =========
ABAS_POSTO = ["Resumo", "Vendas", "Margens", "Estoque", "Compras e Custos", "Alertas"]


def pagina_posto(posto: str):
    dfp = DF[DF["posto"] == posto]
    info = D["postos"].loc[posto]
    situ = al.situacao_posto(ALERTAS, posto)
    per = cabecalho(f"⛽ {posto}", f"{ui.esc(info['bairro'])} · {ui.esc(info['cidade'])} — "
                    f"{ui.esc(info['perfil'])}", df=dfp, botao=False)
    status_envio = arm.status_postos(arm.ler_envios(), [posto])[posto]
    ultima_p = an.ultima_data(DF, posto)
    envio_txt = (f"📤 Última planilha {quando_txt(status_envio['data_hora'])} por "
                 f"{ui.esc(status_envio['usuario'])}" if status_envio else "📤 Nenhum envio registrado")
    ui.md(f'<div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:-.3rem 0 .2rem">'
          f'{ui.pill(situ, "Sem alertas" if situ == "ok" else None)}'
          f'<span class="nota">{envio_txt} · dados até {ultima_p:%d/%m/%Y}</span></div>')

    # O alerta de auditoria é do proprietário: o gerente já foi avisado, no
    # envio, de que a alteração fica registrada.
    meus = [a for a in ALERTAS if a.posto == posto and (usuario.ve_rede or a.aba != "Auditoria")]
    n_prob = sum(a.nivel in ("critico", "atencao") for a in meus)
    rotulos = [a if a != "Alertas" else (f"Alertas ({n_prob})" if n_prob else "Alertas") for a in ABAS_POSTO]
    # A aba escolhida mora em "aba_<posto>" — é o que os botões "Abrir →" da
    # Central escrevem. O controle só espelha esse valor: o clique passa por
    # `_mudou_aba`, e clicar na aba já marcada (que o Streamlit desmarcaria)
    # não perde a escolha.
    chave, chave_seg = f"aba_{posto}", f"_seg_{posto}"
    aba = st.session_state.get(chave, "Resumo")
    if aba not in ABAS_POSTO:
        aba = "Resumo"

    def _mudou_aba():
        valor = st.session_state.get(chave_seg)
        if valor:
            st.session_state[chave] = valor.split(" (")[0]

    st.session_state[chave_seg] = rotulos[ABAS_POSTO.index(aba)]
    st.segmented_control("Aba", rotulos, key=chave_seg, label_visibility="collapsed", on_change=_mudou_aba)
    botao_custo()

    if aba == "Resumo":
        aba_resumo(posto, per, dfp, meus)
    elif aba == "Vendas":
        aba_vendas(posto, per, dfp)
    elif aba == "Margens":
        aba_margens(posto, per, dfp)
    elif aba == "Estoque":
        aba_estoque(posto, per, dfp)
    elif aba == "Compras e Custos":
        aba_compras(posto, per, dfp)
    else:
        aba_alertas_posto(posto, meus)


def _kpis_posto(posto, per, grande=True):
    ind = an.indicadores(DF, per, posto)
    ant = ind["anterior"]
    comp = rotulo_comparacao(an.periodo(DF[DF["posto"] == posto], per.ano, per.mes))
    est = an.estoque_atual(DF, D["tanques"], per.fim, posto)
    aut = est["estoque"].sum() / est["media_dia"].sum()
    pior = est.sort_values("autonomia").iloc[0]
    cls_aut = {"critico": "alerta-critico", "atencao": "alerta-atencao"}.get(pior["status"], "")
    ui.grade_kpis([
        ui.kpi("Faturado", format_brl_curto(ind["faturamento"]),
               ui.delta_html(_var(ind["faturamento"], ant["faturamento"])) + comp, "💰", "grande",
               spark=tendencia("faturamento", posto)),
        ui.kpi("Litros vendidos", format_litros(ind["litros"]),
               ui.delta_html(_var(ind["litros"], ant["litros"])) + comp, "⛽", "grande",
               spark=tendencia("litros", posto)),
        ui.kpi("LB · Lucro Bruto", format_brl_curto(ind["margem"]),
               f"{format_pct_simples(ind['margem_pct'], 1)} do faturamento · "
               + ui.delta_html(_var(ind["margem"], ant["margem"])), "📈", "grande destaque",
               spark=tendencia("margem", posto)),
        ui.kpi("LB por litro", format_rs_litro(ind["margem_litro"]),
               ui.delta_html(_var(ind["margem_litro"], ant["margem_litro"])) + comp, "🧮", "grande"),
        ui.kpi("Em estoque", format_litros(est["estoque"].sum()),
               f"{format_pct_simples(est['estoque'].sum() / est['capacidade'].sum() * 100, 0)} da capacidade · "
               f"medição de {est['data'].max():%d/%m}", "🛢️", "grande", spark=tendencia("estoque", posto)),
        ui.kpi("Dias de autonomia", f"{format_decimal(aut, 1)} dias",
               f"o mais baixo: {pior['produto']} com {format_decimal(pior['autonomia'], 1)} "
               f"dia{'s' if pior['autonomia'] >= 2 else ''}", "⏱️", f"grande {cls_aut}"),
    ], grande=True)
    return ind, est


def aba_resumo(posto, per, dfp, meus):
    equilibrio_ui.bloco(DF, D["despesas"], posto, per, custo=CUSTO)   # o destaque pedido pelo dono: o ponto de equilíbrio
    ind, est = _kpis_posto(posto, per)
    problemas = [a for a in meus if a.nivel in ("critico", "atencao")]
    if problemas:
        itens = "".join(f'<span class="chip {a.nivel}">{ui.esc(a.resumo)}</span>' for a in problemas)
        ui.md(f'<div class="chips"><span class="chips-rotulo">Alertas deste posto</span>{itens}</div>')
        st.button("Ver os alertas deste posto →", key=f"ver_alertas_{posto}", type="tertiary",
                  on_click=lambda: st.session_state.update({f"aba_{posto}": "Alertas"}))

    ui.secao("🛢️ Estoque atual e autonomia", f"Medição de {est['data'].max():%d/%m}")
    ui.md(ui.tanques_html(est))

    comb = an.por_combustivel(DF, per, posto)
    ui.secao("Por combustível", texto_periodo(an.periodo(dfp, per.ano, per.mes)))
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        ui.bloco_titulo("Volume vendido")
        grafico(charts.barras_combustivel(comb, "litros", "litros"))
    with c2, st.container(border=True):
        ui.bloco_titulo("Faturamento")
        grafico(charts.barras_combustivel(comb, "faturamento", "brl"))
    with c3, st.container(border=True):
        ui.bloco_titulo("LB por litro")
        grafico(charts.barras_combustivel(comb, "margem_litro", "rs_litro"))

    c4, c5 = st.columns(2)
    s = an.serie_mensal(DF, posto)
    parcial = (ULTIMA.year, ULTIMA.month) if an.periodo(dfp, ULTIMA.year, ULTIMA.month).parcial else None
    with c4, st.container(border=True):
        ui.bloco_titulo("Evolução das vendas — últimos 12 meses", "* mês em andamento")
        grafico(charts.mensal_barras(s, "litros", "litros", (per.ano, per.mes), parcial, 290))
    with c5, st.container(border=True):
        ui.bloco_titulo("Preço de venda × custo médio", "Últimos 90 dias")
        prod = st.segmented_control("Combustível", theme.COMBUSTIVEIS, default=theme.COMBUSTIVEIS[0],
                                    key=f"pc_{posto}", label_visibility="collapsed",
                                    format_func=lambda p: f"{theme.ICONES_COMBUSTIVEL[p]} {theme.ROTULO_CURTO[p]}")
        prod = prod or theme.COMBUSTIVEIS[0]
        sd = an.serie_diaria(DF, per.fim - pd.Timedelta(days=89), per.fim, posto)
        grafico(charts.preco_custo(sd, prod, 262))


def aba_vendas(posto, per, dfp):
    pp = an.periodo(dfp, per.ano, per.mes)
    comb = an.por_combustivel(DF, per, posto)
    ind = an.indicadores(DF, per, posto)
    with st.container(border=True):
        ui.bloco_titulo("Vendas por dia", f"{texto_periodo(pp)} · litros por combustível")
        grafico(charts.diario_empilhado(an.serie_diaria(DF, pp.inicio, pp.fim, posto), 300))
    with st.container(border=True):
        ui.bloco_titulo("Vendas por combustível", f"{texto_periodo(pp)} · variação {rotulo_comparacao(pp)}")
        linhas = []
        for _, r in comb.iterrows():
            linhas.append([ui.nome_combustivel(r["produto"]), format_litros(r["litros"]),
                           format_pct_simples(r["participacao"], 1), format_brl(r["faturamento"]),
                           format_rs_litro(r["preco_medio"], 3), ui.var_html(_var(r["litros"], r["litros_ant"]))])
        total = ["Total", format_litros(ind["litros"]), "100,0%", format_brl(ind["faturamento"]),
                 format_rs_litro(ind["preco_medio"], 3), ui.var_html(_var(ind["litros"], ind["anterior"]["litros"]))]
        ui.md(ui.tabela_html([("Combustível", False), ("Litros", True), ("Participação", True),
                              ("Faturamento", True), ("Preço médio", True), ("Litros vs mês ant.", True)],
                             linhas, total))
    c1, c2 = st.columns([1.6, 1])
    parcial = (ULTIMA.year, ULTIMA.month) if an.periodo(dfp, ULTIMA.year, ULTIMA.month).parcial else None
    with c1, st.container(border=True):
        ui.bloco_titulo("Últimos 12 meses por combustível", "Litros por mês · * mês em andamento")
        grafico(charts.mensal_empilhado(an.serie_mensal(DF, posto, por_produto=True), parcial, 300))
    with c2, st.container(border=True):
        ui.bloco_titulo("Média por dia da semana", "Litros por dia · últimas 8 semanas · em laranja, o mais forte")
        grafico(charts.dia_semana(an.media_dia_semana(DF, pp.fim, 8, posto), 300))


def aba_margens(posto, per, dfp):
    pp = an.periodo(dfp, per.ano, per.mes)
    ind = an.indicadores(DF, per, posto)
    hist = an.media_12_meses(DF, per, posto)
    comb = an.por_combustivel(DF, per, posto)
    ui.grade_kpis([
        ui.kpi("LB · Lucro Bruto", format_brl_curto(ind["margem"]), texto_periodo(pp), "📈", "destaque"),
        ui.kpi("LB %", format_pct_simples(ind["margem_pct"], 2),
               ui.delta_html(ind["margem_pct"] - hist["margem_pct"], tipo="pp") + "vs média de 12 meses", "％"),
        ui.kpi("LB por litro", format_rs_litro(ind["margem_litro"]),
               f"média de 12 meses: {format_rs_litro(hist['margem_litro'])}", "🧮"),
        ui.kpi("Preço médio × custo médio", format_rs_litro(ind["preco_medio"]),
               f"custo médio: {format_rs_litro(ind['custo_medio'])}", "🏷️"),
    ])
    with st.container(border=True):
        ui.bloco_titulo("LB por combustível", f"{texto_periodo(pp)} · variação do LB por litro "
                        f"{rotulo_comparacao(pp)}")
        linhas = []
        for _, r in comb.iterrows():
            linhas.append([ui.nome_combustivel(r["produto"]), format_rs_litro(r["preco_medio"], 3),
                           format_rs_litro(r["custo_medio"], 3), f"<b>{format_rs_litro(r['margem_litro'])}</b>",
                           format_pct_simples(r["margem_pct"], 1), format_brl(r["margem"], 0),
                           ui.var_html(_var(r["margem_litro"], r["margem_litro_ant"]))])
        total = ["Total", format_rs_litro(ind["preco_medio"], 3), format_rs_litro(ind["custo_medio"], 3),
                 format_rs_litro(ind["margem_litro"]), format_pct_simples(ind["margem_pct"], 1),
                 format_brl(ind["margem"], 0), ui.var_html(_var(ind["margem_litro"], ind["anterior"]["margem_litro"]))]
        ui.md(ui.tabela_html([("Combustível", False), ("Preço médio", True), ("Custo médio", True),
                              ("LB/L", True), ("LB %", True), ("LB R$", True),
                              ("LB/L vs mês ant.", True)], linhas, total))
    c1, c2 = st.columns(2)
    parcial = (ULTIMA.year, ULTIMA.month) if an.periodo(dfp, ULTIMA.year, ULTIMA.month).parcial else None
    with c1, st.container(border=True):
        ui.bloco_titulo("LB por litro, mês a mês", "Os quatro combustíveis · últimos 12 meses")
        grafico(charts.mensal_linhas_combustivel(an.serie_mensal(DF, posto, por_produto=True),
                                                 "margem_litro", "rs_litro", 300))
    with c2, st.container(border=True):
        ui.bloco_titulo("LB %, mês a mês",
                        f"Linha laranja = média dos 12 meses anteriores ({format_pct_simples(hist['margem_pct'], 1)})")
        grafico(charts.margem_pct_mensal(an.serie_mensal(DF, posto), hist["margem_pct"],
                                         (per.ano, per.mes), parcial, 300))
    with st.container(border=True):
        ui.bloco_titulo("Preço de venda × custo médio, dia a dia", "Últimos 6 meses · a faixa é o LB")
        prod = st.segmented_control("Combustível", theme.COMBUSTIVEIS, default=theme.COMBUSTIVEIS[0],
                                    key=f"pcm_{posto}", label_visibility="collapsed",
                                    format_func=lambda p: f"{theme.ICONES_COMBUSTIVEL[p]} {p}")
        prod = prod or theme.COMBUSTIVEIS[0]
        sd = an.serie_diaria(DF, pp.fim - pd.Timedelta(days=182), pp.fim, posto)
        grafico(charts.preco_custo(sd, prod, 300))


def aba_estoque(posto, per, dfp):
    pp = an.periodo(dfp, per.ano, per.mes)
    est = an.estoque_atual(DF, D["tanques"], per.fim, posto)
    ui.md(ui.tanques_html(est))
    c1, c2 = st.columns([1, 1.5])
    with c1, st.container(border=True):
        ui.bloco_titulo("Autonomia estimada", "Dias que o estoque cobre, na venda média dos últimos 7 dias")
        grafico(charts.autonomia_barras(est, 250))
    with c2, st.container(border=True):
        ui.bloco_titulo("Nível dos tanques no mês", f"{texto_periodo(pp)} · % da capacidade, medição do fim do dia")
        grafico(charts.estoque_linhas(an.serie_estoque(DF, D["tanques"], pp.inicio, pp.fim, posto), 280))
    with st.container(border=True):
        ui.bloco_titulo("Perdas e sobras do LMC",
                        f"{texto_periodo(pp)} · estoque medido − (inicial + compras − vendas). "
                        f"Tolerância de referência: {format_pct_simples(an.TOLERANCIA_PERDA, 1)} do vendido")
        t = an.perdas_lmc(DF, pp, posto)
        linhas = []
        for _, r in t.iterrows():
            linhas.append([ui.nome_combustivel(str(r["produto"])), format_litros(r["vendido"]),
                           format_litros(r["perda_l"]), format_pct_simples(r["perda_pct"], 2),
                           format_brl(r["perda_rs"]), ui.pill(r["status"])])
        ui.md(ui.tabela_html([("Combustível", False), ("Vendido", True), ("Perda (−) / sobra (+)", True),
                              ("% do vendido", True), ("Em custo", True), ("Situação", False)], linhas))
        ui.nota("Evaporação e variação de temperatura explicam perdas pequenas (até ~0,3%). Acima da "
                "tolerância, verifique vazamento, aferição das bombas e a medição dos tanques.")


def bloco_desconto(posto, pp):
    """Quanto o desconto do boleto vale: o LB por litro nos dois preços (o botão ao lado das abas escolhe qual conta vale)."""
    g = an.recorte(DF, pp.inicio, pp.fim, posto)
    litros = float(g["vendas_l"].sum())
    desc_rs = float((g["desconto_litro"] * g["vendas_l"]).sum())
    if litros <= 0 or desc_rs <= 0:
        return
    planilha = float(g["margem"].sum()) + (desc_rs if CUSTO == "sistema" else 0.0)     # a margem, no preço planilha
    sistema = planilha - desc_rs                                                        # e no preço sistema (nota cheia)
    ui.secao("Desconto do boleto")
    ui.grade_kpis([
        ui.kpi("LB/L · planilha", format_rs_litro(planilha / litros, 3),
               "", "🧾", "destaque" if CUSTO == "planilha" else ""),
        ui.kpi("LB/L · sistema", format_rs_litro(sistema / litros, 3),
               "", "🖥️", "destaque" if CUSTO == "sistema" else ""),
        ui.kpi("O desconto do boleto vale", format_brl_curto(desc_rs),
               f"{format_rs_litro(desc_rs / litros, 3)} em média", "💰"),
    ])


def compras_no_preco() -> pd.DataFrame:
    """As notas no preço que vale na conta (botão do menu lateral). Sistema = a nota cheia: custo e valor + o desconto do
    boleto. SÓ para mostrar: as conferências antifraude seguem com as notas como o posto as enviou."""
    c = D["compras"]
    if CUSTO != "sistema" or c.empty:
        return c
    c = c.copy()
    d = descontos.por_compra(c, D["descontos"])
    c["custo"] = c["custo"] + d
    c["valor"] = c["valor"] + c["litros"] * d
    return c


def aba_compras(posto, per, dfp):
    pp = an.periodo(dfp, per.ano, per.mes)
    bloco_desconto(posto, pp)
    comp = an.compras_periodo(compras_no_preco(), pp, posto)
    if len(comp):
        ui.grade_kpis([
            ui.kpi("Litros comprados", format_litros(comp["litros"].sum()), f"{len(comp)} notas fiscais", "🚚"),
            ui.kpi("Valor das notas", format_brl_curto(comp["valor"].sum()), texto_periodo(pp), "🧾"),
            ui.kpi("Custo médio das compras", format_rs_litro(comp["valor"].sum() / comp["litros"].sum(), 3),
                   "todos os combustíveis", "🏷️"),
            ui.kpi("Distribuidoras", format_int(comp["distribuidora"].nunique()),
                   ", ".join(sorted(comp["distribuidora"].unique())), "🏭"),
        ])
        with st.container(border=True):
            ui.bloco_titulo("Custo por distribuidora", "Últimos 90 dias · custo médio ponderado por litro · "
                            "🏆 a mais barata em cada combustível")
            cd = an.custo_por_distribuidora(compras_no_preco(), pp.fim - pd.Timedelta(days=89), pp.fim, posto)
            ui.md(quadro_distribuidoras(cd))
        with st.container(border=True):
            ui.bloco_titulo("Notas recebidas", f"{texto_periodo(pp)} · as mais recentes primeiro")
            linhas = [[f"{r['data']:%d/%m}", ui.nome_combustivel(str(r["produto"])),
                       format_litros(r["litros"]), format_rs_litro(r["custo"], 4), format_brl(r["valor"]),
                       ui.esc(r["nota_fiscal"]), ui.esc(r["distribuidora"])]
                      for _, r in comp.sort_values("data", ascending=False).iterrows()]
            ui.md('<div style="max-height:340px;overflow-y:auto">' + ui.tabela_html(
                [("Data", False), ("Produto", False), ("Litros", True), ("Custo", True), ("Valor", True),
                 ("NF", False), ("Distribuidora", False)], linhas) + "</div>")
    else:
        st.info("A planilha deste posto não tem a aba COMPRAS preenchida neste período.")

    res = an.resultado(DF, D["despesas"], per, posto)
    ui.secao("💼 Resultado depois das despesas",
             "LB − perdas do LMC − despesas · antes de IR/CSLL")
    if not res["tem_despesas"]:
        st.info("Sem despesas lançadas neste período: o painel mostra só o LB. Preencha a aba "
                "DESPESAS da planilha para ver o resultado.")
        return
    ui.grade_kpis([
        ui.kpi("LB · Lucro Bruto", format_brl_curto(res["margem"]), "", "📈"),
        ui.kpi("Perdas no LMC", format_brl_curto(res["perda_rs"]), "combustível que sumiu da régua", "💧"),
        ui.kpi("Despesas", format_brl_curto(res["despesas"]), f"{len(res['por_categoria'])} categorias", "🧾"),
        # Resultado compara em REAIS: com base pequena ou negativa, o percentual
        # mente ("−232%" para uma queda de R$ 30 mil).
        ui.kpi("Resultado", format_brl_curto(res["resultado"]),
               f"{format_pct_simples(res['resultado_pct'], 1)} do faturamento · "
               + ui.delta_html(res["resultado"] - res["resultado_ant"], tipo="brl") + rotulo_comparacao(pp),
               "🏁", "destaque"),
    ])
    c1, c2 = st.columns([1.35, 1])
    with c1, st.container(border=True):
        ui.bloco_titulo("Do LB ao resultado", texto_periodo(pp))
        grafico(charts.cascata_resultado(res, 330))
    with c2, st.container(border=True):
        ui.bloco_titulo("Despesas por categoria", texto_periodo(pp))
        grafico(charts.despesas_categoria(res["por_categoria"], 330))
    with st.container(border=True):
        sr = an.serie_resultado_mensal(DF, D["despesas"], posto)
        parcial = (ULTIMA.year, ULTIMA.month) if an.periodo(dfp, ULTIMA.year, ULTIMA.month).parcial else None
        ui.bloco_titulo("Resultado por mês — últimos 12 meses", "* mês em andamento (as despesas fixas já "
                        "entraram; parte da venda ainda não)")
        grafico(charts.mensal_barras(sr, "resultado", "brl", (per.ano, per.mes), parcial, 260))


def quadro_distribuidoras(cd: pd.DataFrame) -> str:
    """Distribuidora × combustível, custo por litro; 🏆 na mais barata de cada coluna."""
    if cd.empty:
        return '<div class="nota">Sem compras nos últimos 90 dias.</div>'
    produtos = [p for p in theme.COMBUSTIVEIS if p in set(cd["produto"].astype(str))]
    menor = cd.groupby("produto", observed=True)["custo"].min()
    linhas = []
    for dist, g in cd.groupby("distribuidora"):
        g = g.set_index(g["produto"].astype(str))
        celulas = [f"<b>{ui.esc(dist)}</b><span class='mini'>{format_litros_curto(g['litros'].sum())} · "
                   f"{int(g['notas'].sum())} notas</span>"]
        for p in produtos:
            if p not in g.index:
                celulas.append('<span class="var-neu">—</span>')
                continue
            c = g.loc[p, "custo"]
            dif = c - menor[p]
            celulas.append(f"<b>{format_rs_litro(c, 3)}</b> 🏆" if dif < 0.0005 else
                           f"{format_rs_litro(c, 3)}<span class='mini'>+{format_rs_litro(dif, 3)}</span>")
        linhas.append(celulas)
    return ui.tabela_html([("Distribuidora", False)] + [(ui.nome_combustivel(p, curto=True), True) for p in produtos],
                          linhas)


def aba_alertas_posto(posto, meus):
    if not meus:
        st.success(f"Nenhum alerta para o {posto}. Estoques, margens e vendas dentro do normal.")
        return
    for nivel, titulo in (("critico", "🔴 Exige ação"), ("atencao", "🟡 Merece atenção"), ("destaque", "🟢 Destaques")):
        lista = [a for a in meus if a.nivel == nivel]
        if not lista:
            continue
        ui.secao(titulo)
        grade_alertas(lista, f"al_{posto}_{nivel}", acao_alerta_do_posto(posto), mostrar_posto=False)


def acao_alerta_do_posto(posto):
    def acao(a):
        if a.aba == "Auditoria":
            return "Ver na Auditoria →", ir_para, (PAGINA_AUDITORIA, "Auditoria", posto)
        if a.aba != "Alertas":
            return f"Ver {a.aba} →", lambda aba=a.aba: st.session_state.update({f"aba_{posto}": aba}), ()
        return None, None, ()
    return acao


# ============================================================ envio =========
def pagina_envio():
    if usuario.ve_rede:
        posto = st.session_state.get("_posto_envio", POSTOS[0])
        c1, c2 = st.columns([3.2, 1], vertical_alignment="bottom")
        with c2:
            posto = st.selectbox("Posto", POSTOS, index=POSTOS.index(posto), key="posto_envio")
            st.session_state["_posto_envio"] = posto
        with c1:
            ui.topo(f"📤 Atualizar dados — {posto}", "Envie a planilha do mês. Ela é conferida antes de "
                    "entrar no painel — erro na planilha nunca derruba o painel.")
    else:
        posto = usuario.posto
        ui.topo(f"📤 Atualizar dados — {posto}", "Envie a planilha do mês. Ela é conferida antes de entrar "
                "no painel — erro na planilha nunca derruba o painel.")
    pasta = D["postos"].loc[posto, "pasta"]
    status = arm.status_postos(arm.ler_envios(), [posto])[posto]
    ultima_p = an.ultima_data(DF, posto)

    c1, c2 = st.columns([1.4, 1])
    with c1:
        det = (f"<b>{quando_txt(status['data_hora'])}</b> por {ui.esc(status['usuario'])}<br>"
               f"Arquivo atual: {ui.esc(status['arquivo'])} · dados até {ultima_p:%d/%m/%Y}"
               if status else f"Nenhum envio registrado · dados até {ultima_p:%d/%m/%Y}")
        ui.md(f'<div class="bloco"><div class="bloco-sub" style="margin:0">ÚLTIMA ATUALIZAÇÃO</div>'
              f'<div style="font-size:.95rem;line-height:1.6">{det}</div></div>')
    with c2:
        modelo = RAIZ / "modelo" / "MODELO - Planilha Mensal do Posto.xlsx"
        ui.md('<div class="bloco"><div class="bloco-sub" style="margin:0">PRIMEIRA VEZ?</div>'
              '<div style="font-size:.9rem">Baixe o modelo com as abas e colunas certas.</div></div>')
        if modelo.exists():
            st.download_button("📥 Baixar modelo da planilha", modelo.read_bytes(), modelo.name,
                               use_container_width=True)

    if st.session_state.get("_envio_ok"):
        mostrar_sucesso(st.session_state["_envio_ok"])
        return

    contador = st.session_state.get("_up_n", 0)
    arquivo = st.file_uploader("Arraste a planilha gerencial aqui (ou clique para escolher)", type=["xlsx"],
                               key=f"up_{posto}_{contador}")
    if not arquivo:
        ui.nota(f"Nome sugerido: <b>{posto} MM-AAAA.xlsx</b>. Pode enviar a planilha do mês quantas vezes "
                "quiser — cada envio substitui o anterior do mesmo mês, e a versão antiga fica guardada.")
        return

    conteudo = arquivo.getvalue()
    with st.spinner("🔍 Verificando planilha…"):
        rel = validacao.validar(conteudo, arquivo.name, posto, POSTOS, D["tanques"], DF,
                                _hash_atual(pasta, posto, arquivo.name, conteudo))
    itens = "".join(f'<div class="check {s}"><span class="ic">{"✅" if s == "ok" else ("⚠️" if s == "aviso" else "❌")}'
                    f'</span><span>{ui.esc(t)}</span></div>' for s, t in rel.itens)
    if rel.erros:
        ui.md(f'<div class="resultado-erro"><div style="font-weight:800;color:var(--critico);font-size:1.05rem">'
              f'❌ PLANILHA NÃO FOI IMPORTADA</div><div style="margin:.3rem 0 .6rem">Encontramos '
              f'{len(rel.erros)} problema{"s" if len(rel.erros) > 1 else ""}. <b>O painel anterior continua '
              f'intacto.</b></div>{itens}</div>')
        return
    ui.md(f'<div class="bloco"><div class="bloco-titulo">🔍 Conferência da planilha</div>{itens}</div>')
    if rel.duplicado:
        st.info("Esta planilha é idêntica à que já está no painel — nada para atualizar.")
        return
    r = rel.resumo
    comp = rel.comparacao
    cards = [ui.kpi("Referência", nome_mes(rel.mes, rel.ano), f"{r['dias']} dias · até {r['ate']:%d/%m}", "🗓️"),
             ui.kpi("Volume vendido", format_litros(r["litros"]), f"{format_int(r['registros'])} registros", "⛽"),
             ui.kpi("Faturamento", format_brl(r["faturamento"], 0), "", "💰"),
             ui.kpi("LB · Lucro Bruto", format_brl(r["margem"], 0), "", "📈", "destaque")]
    ui.grade_kpis(cards)
    if comp:
        ui.nota(f"Substitui a versão que está no painel (dados até {comp['ate']:%d/%m}): volume "
                f"{_sinal_litros(comp['litros'])}, faturamento {_sinal_brl(comp['faturamento'])}, margem "
                f"{_sinal_brl(comp['margem'])}. A versão atual fica guardada.")
    ui.nota(f"Será salva como <b>{ui.esc(rel.nome_padrao)}</b>"
            + (" no repositório (GitHub)." if arm.modo() == "github" else " na pasta do posto."))
    if st.button("✅ Confirmar atualização", type="primary", use_container_width=False):
        with st.spinner("Atualizando o painel…"):
            ret = arm.salvar_planilha(usuario.login, posto, pasta, rel.nome_padrao, conteudo, rel.periodo,
                                      f"dados até {r['ate']:%d/%m} · {format_int(r['registros'])} registros")
        if ret["ok"]:
            st.cache_data.clear()
            st.session_state["_envio_ok"] = {"posto": posto, "periodo": nome_mes(rel.mes, rel.ano),
                                             "resumo": r, "comparacao": comp, "mensagem": ret["mensagem"]}
            st.session_state["_up_n"] = contador + 1
            st.rerun()
        else:
            ui.md(f'<div class="resultado-erro"><b>❌ Não foi possível atualizar.</b><br>{ui.esc(ret["mensagem"])}</div>')


def _hash_atual(pasta, posto, nome_enviado, conteudo) -> str | None:
    m = validacao.etl.PADRAO_ARQUIVO.search(nome_enviado)
    candidatos = []
    if m:
        candidatos.append(f"{posto} {m.group(1)}-{m.group(2)}.xlsx")
    for nome in candidatos:
        atual = arm.arquivo_atual(pasta, nome)
        if atual:
            return arm.hash_conteudo(atual.read_bytes())
    return None


def _sinal_litros(v):
    return ("+" if v > 0 else "") + format_litros(v)


def _sinal_brl(v):
    return ("+" if v > 0 else "") + format_brl(v, 0)


def mostrar_sucesso(ok: dict):
    r, comp = ok["resumo"], ok["comparacao"]
    variacao = ""
    if comp:
        variacao = (f'<div style="margin-top:.6rem"><b>Variação desde a versão anterior:</b><br>'
                    f'• Volume: <b>{_sinal_litros(comp["litros"])}</b><br>'
                    f'• Faturamento: <b>{_sinal_brl(comp["faturamento"])}</b><br>'
                    f'• Margem: <b>{_sinal_brl(comp["margem"])}</b></div>')
    ui.md(f'<div class="resultado-ok"><div style="font-weight:800;color:var(--ok);font-size:1.15rem">'
          f'✅ {ui.esc(ok["posto"])} atualizado com sucesso</div>'
          f'<div style="margin-top:.4rem;line-height:1.7">{ok["periodo"]} · dados até {r["ate"]:%d/%m}<br>'
          f'<b>{format_litros(r["litros"])}</b> · <b>{format_brl(r["faturamento"], 0)}</b> de faturamento · '
          f'<b>{format_brl(r["margem"], 0)}</b> de margem bruta</div>{variacao}'
          f'<div class="nota" style="margin-top:.6rem">{ui.esc(ok["mensagem"])}</div></div>')
    c1, c2, _ = st.columns([1, 1, 2])
    destino = f"⛽ {ok['posto']}" if usuario.ve_rede else "⛽ Meu Posto"

    def _limpar():
        st.session_state.pop("_envio_ok", None)

    c1.button("Ver painel atualizado →", type="primary", use_container_width=True,
              on_click=lambda: (_limpar(), ir_para(destino, "Resumo", ok["posto"])))
    c2.button("Enviar outra planilha", use_container_width=True, on_click=_limpar)


# ============================================================ histórico =====
def pagina_atualizacoes():
    proprio = not usuario.ve_rede
    ui.topo("📑 Meus Envios" if proprio else "📑 Atualizações",
            "Quando cada planilha chegou, quem enviou e o que aconteceu com ela.")
    postos = [usuario.posto] if proprio else POSTOS
    envio_cards(postos)
    envios = arm.ler_envios()
    if proprio:
        envios = envios[envios["posto"] == usuario.posto]
    else:
        filtro = st.segmented_control("Posto", ["Todos"] + POSTOS, default="Todos", key="hist_filtro",
                                      label_visibility="collapsed") or "Todos"
        if filtro != "Todos":
            envios = envios[envios["posto"] == filtro]
    with st.container(border=True):
        ui.bloco_titulo("Histórico de envios", f"{format_int(len(envios))} envios · os mais recentes primeiro")
        icone = {"Processado": "✅ Processado", "Substituído": "↺ Substituído", "Recusado": "❌ Recusado"}
        linhas = [[f"{r['data_hora']:%d/%m %H:%M}", ui.esc(r["posto"].replace("B2 ", "")), ui.esc(r["usuario"]),
                   r["periodo"], ui.esc(r["arquivo"]), icone.get(r["resultado"], ui.esc(r["resultado"])),
                   ui.esc(r["detalhe"])] for _, r in envios.head(80).iterrows()]
        ui.md('<div style="max-height:460px;overflow-y:auto">' + ui.tabela_html(
            [("Data", False), ("Posto", False), ("Usuário", False), ("Período", False), ("Arquivo", False),
             ("Resultado", False), ("Detalhe", False)], linhas) + "</div>")

    if usuario.ve_rede:
        ui.secao("↩ Restaurar versão anterior", "Volta uma planilha para como estava antes do último envio.")
        if arm.modo() == "github":
            ui.nota("Publicado, cada envio é um commit no GitHub: restaure pelo histórico do arquivo no "
                    "repositório (o painel se atualiza sozinho em seguida).")
            return
        c1, c2 = st.columns(2)
        posto = c1.selectbox("Posto", POSTOS, key="rest_posto")
        pasta = D["postos"].loc[posto, "pasta"]
        arquivos = sorted((base.PASTA_DADOS / pasta).glob("*.xlsx"), reverse=True)
        nome = c2.selectbox("Planilha", [a.name for a in arquivos], key="rest_arq")
        versoes = arm.listar_versoes(pasta, nome) if nome else []
        if not versoes:
            ui.nota("Esta planilha não tem versão anterior guardada.")
            return
        versao = st.selectbox("Versão", versoes, format_func=lambda v: f"guardada em {v.stem.split(' __ ')[-1]}",
                              key="rest_ver")
        if st.button("↩ Restaurar esta versão", type="primary"):
            m = validacao.etl.PADRAO_ARQUIVO.search(nome)
            ret = arm.restaurar_versao(usuario.login, posto, pasta, nome, versao, f"{m.group(1)}/{m.group(2)}")
            if ret["ok"]:
                st.cache_data.clear()
                st.success("Versão restaurada e painel atualizado.")
                st.rerun()
            st.error(ret["mensagem"])


# ============================================================ alertas =======
def pagina_alertas():
    ui.topo("🔔 Central de alertas", f"As regras rodam sobre os dados até {ULTIMA:%d/%m/%Y} — as mesmas que "
            "vão para o celular.")
    filtro = st.segmented_control("Posto", ["Toda a rede"] + POSTOS, default="Toda a rede", key="alertas_filtro",
                                  label_visibility="collapsed") or "Toda a rede"
    lista = ALERTAS if filtro == "Toda a rede" else [a for a in ALERTAS if a.posto == filtro]
    for nivel, titulo in (("critico", "🔴 Exige ação"), ("atencao", "🟡 Merece atenção"), ("destaque", "🟢 Destaques")):
        grupo = [a for a in lista if a.nivel == nivel]
        if not grupo:
            continue
        ui.secao(f"{titulo} ({len(grupo)})")
        grade_alertas(grupo, f"pa_{nivel}", acao_abrir_posto)

    ui.secao("📱 Alertas no celular", "O motor de alertas roda sozinho depois de cada atualização — o dono "
             "não precisa estar com o painel aberto.")
    cfg = notificacoes.config()
    canal, pronto, motivo = notificacoes.canal_pronto(cfg)
    nomes = {"console": "Nenhum canal (demonstração)", "ntfy": "ntfy", "pushover": "Pushover"}
    ui.md(f'<div class="bloco"><b>Canal:</b> {nomes.get(canal, canal)} — {ui.esc(motivo)}.<br>'
          f'<span class="nota">Configure em <code>config_alertas.toml</code> (ntfy ou Pushover). '
          f'Níveis enviados: {", ".join(cfg["envio"]["niveis"])}.</span></div>')
    if canal != "console" and pronto:
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("📨 Enviar notificação de teste"):
            ok, ret = notificacoes.enviar_alerta("✅ B2 Gestão — teste", "Os alertas da rede vão chegar aqui.",
                                                 cfg["envio"].get("url_painel", ""), "destaque", cfg)
            (st.success if ok else st.error)(ret)
        if c2.button("🔔 Enviar alertas novos agora"):
            r = subprocess.run([sys.executable, str(RAIZ / "motor_alertas.py")], capture_output=True,
                               text=True, encoding="utf-8", cwd=RAIZ)
            st.code(r.stdout[-3000:] or r.stderr[-3000:])
    enviados = RAIZ / "data" / "alertas_enviados.csv"
    if enviados.exists():
        h = pd.read_csv(enviados, sep=";").tail(30).iloc[::-1]
        with st.container(border=True):
            ui.bloco_titulo("Últimos alertas enviados ao celular")
            ui.md(ui.tabela_html([("Enviado em", False), ("Nível", False), ("Posto", False), ("Alerta", False),
                                  ("Canal", False)],
                                 [[r["enviado_em"], al.ICONE_NIVEL.get(r["nivel"], ""), ui.esc(r["posto"]),
                                   ui.esc(r["resumo"]), ui.esc(r["canal"])] for _, r in h.iterrows()]))


# ============================================================ auditoria =====
GRAVIDADE = {"normal": ("ok", "Correção normal"), "atencao": ("atencao", "Atenção"),
             "critico": ("critico", "Crítico")}


def sinal_html(s: antifraude.Sinal) -> str:
    return (f'<details class="alerta-linha {s.nivel}"><summary><span class="al-ponto"></span>'
            f'<span class="al-corpo"><span class="al-titulo">{ui.esc(s.titulo)}</span>'
            f'<span class="al-resumo">{ui.esc(s.detalhe)}</span></span>'
            f'<span class="al-posto">{ui.esc(s.posto.replace("B2 ", ""))}</span></summary>'
            f'<div class="al-det"><b>Por que importa:</b> {ui.esc(s.porque)}</div></details>')


def pagina_auditoria():
    per = cabecalho(PAGINA_AUDITORIA, "Cruzamentos que merecem conferência. Nenhum sinal é acusação: é "
                    "<b>confira isto</b>.")
    aud = D["auditoria"]
    sinais = antifraude.sinais(DF, D["compras"], aud, POSTOS, per)
    sus = auditoria.suspeitas(aud)
    baixadas = sus[(sus["campo"] == "Vendas") & (sus["diferenca"] < 0)] if len(sus) else sus
    dias_alt = int(sus.groupby("posto")["data"].nunique().sum()) if len(sus) else 0
    criticos = sum(s.nivel == "critico" for s in sinais)
    ui.grade_kpis([
        ui.kpi("Dias alterados depois de enviados", format_int(dias_alt),
               f"{sus['posto'].nunique()} posto(s) · últimos 30 dias" if dias_alt else "nenhum nos últimos 30 dias",
               "✏️", "alerta-critico" if dias_alt else ""),
        ui.kpi("Venda apagada depois", format_brl_curto(-baixadas["impacto_rs"].sum()) if len(baixadas) else "R$ 0",
               f"{format_litros(-baixadas['diferenca'].sum())} em dias já enviados" if len(baixadas)
               else "nenhuma venda reduzida", "💸"),
        ui.kpi("Sinais críticos", format_int(criticos), texto_periodo(per), "🔴"),
        ui.kpi("Sinais de atenção", format_int(len(sinais) - criticos), texto_periodo(per), "🟡"),
    ])

    ui.secao("O que conferir", "Do mais grave ao mais leve. Cada cartão diz o que foi achado e por que importa.")
    filtro = st.segmented_control("Posto", ["Toda a rede"] + POSTOS, default="Toda a rede", key="aud_filtro",
                                  label_visibility="collapsed") or "Toda a rede"
    lista = sinais if filtro == "Toda a rede" else [s for s in sinais if s.posto == filtro]
    if lista:
        for s in lista:
            ui.md(sinal_html(s))
    else:
        st.success("Nenhum sinal no período. 👏")

    ui.secao("Trilha de alterações", "Tudo o que mudou em dados já recebidos: quando, quem enviou, por onde e "
             "quanto mexeu.")
    with st.container(border=True):
        normais = st.toggle("Mostrar também as correções normais (dia recente)", key="aud_normais")
        trilha = aud if normais else aud[aud["gravidade"] != "normal"]
        if filtro != "Toda a rede":
            trilha = trilha[trilha["posto"] == filtro]
        if trilha.empty:
            ui.nota("Nenhuma alteração registrada." if aud.empty else
                    "Nenhuma alteração suspeita — só correções do dia a dia (ligue a chave acima para ver).")
        else:
            linhas = [[f"{r['registrado_em']:%d/%m %H:%M}", ui.esc(r["posto"].replace("B2 ", "")),
                       ui.esc(r["usuario"] or "—"), ui.esc(r["origem"]), ui.esc(auditoria.descrever(r)),
                       ui.pill(*GRAVIDADE.get(r["gravidade"], ("neutro", r["gravidade"])))]
                      for _, r in trilha.head(150).iterrows()]
            ui.md('<div style="max-height:420px;overflow-y:auto">' + ui.tabela_html(
                [("Registrado", False), ("Posto", False), ("Enviado por", False), ("Por onde", False),
                 ("O que mudou", False), ("Gravidade", False)], linhas) + "</div>")

    with st.expander("Como a auditoria funciona"):
        ui.md(f"""
* **Toda base nova é comparada com a anterior**, posto × dia × combustível. Dia novo é rotina; dia que já
  tinha chegado e mudou vai para a trilha, com o valor antes e depois.
* **Gravidade:** mexer no dia de ontem é correção normal; dia com {auditoria.DIAS_CORRECAO_NORMAL}+ dias é
  atenção; dia com {auditoria.DIAS_CRITICO}+ dias ou de **mês já fechado** é crítico — e vira alerta na
  Central e no celular.
* **O gerente é avisado no envio** de que a planilha altera dias já recebidos e que isso fica registrado. Só
  esse aviso já desencoraja o "ajuste".
* **Baixar a venda sem mexer na régua aparece como perda no LMC**: os dois sinais se confirmam.
* Os outros cruzamentos usam o que o posto já manda: notas × entradas no tanque, nota repetida, valor da
  nota, custo médio × notas, venda abaixo do custo e números redondos demais.
""")


# ============================================================ reunião =======
def placar_html(p: pd.DataFrame, rede: pd.Series, per: an.Periodo) -> str:
    marca = {"critico": "■ ", "atencao": "▲ "}
    cab = "".join(f"<th>{rot}<small>{regua}</small></th>" for _, rot, regua, _ in reuniao.INDICADORES)
    corpo = []
    for _, r in p.iterrows():
        celulas = []
        for coluna, *_ in reuniao.INDICADORES:
            s = reuniao.situacao(coluna, r[coluna], rede)
            celulas.append(f'<td class="cel {s}">{marca.get(s, "")}{reuniao.formatar(coluna, r[coluna])}</td>')
        ate = f" · até {r['ate']:%d/%m}" if r["ate"] < per.fim else ""
        corpo.append(f'<tr><td class="unidade">{ui.esc(r["posto"].replace("B2 ", ""))}'
                     f'<small>{format_litros_curto(r["litros"])}{ate}</small></td>{"".join(celulas)}</tr>')
    corpo.append('<tr class="rede"><td class="unidade">Rede<small>' + format_litros_curto(rede["litros"])
                 + "</small></td>" + "".join(f"<td>{reuniao.formatar(c, rede[c])}</td>"
                                             for c, *_ in reuniao.INDICADORES) + "</tr>")
    return (f'<div class="tabela-wrap"><table class="tabela matriz placar"><thead><tr><th></th>{cab}</tr></thead>'
            f'<tbody>{"".join(corpo)}</tbody></table></div>'
            '<div class="nota" style="margin-top:.4rem">■ crítico · ▲ atenção · sem marca: dentro da régua. '
            'Margem e despesa comparadas com a média da rede (o perfil de cada posto pesa); perda, aditivada e '
            'pontualidade, com meta fixa.</div>')


def pagina_reuniao():
    per = cabecalho(PAGINA_REUNIAO, "O placar do mês para a conversa com cada gerente — o que ele controla.")
    p = reuniao.placar(DF, D["despesas"], D["envios"], D["auditoria"], per, POSTOS)
    if p.empty:
        st.info("Sem dados no período.")
        return
    rede = reuniao.medias_rede(p)
    ui.secao("Placar das gerências", f"{texto_periodo(per)} · cada posto até o último dia que enviou, comparado "
             "com os mesmos dias do mês anterior")
    ui.md(placar_html(p, rede, per))

    ui.secao("🏆 Destaques do mês")
    cartoes = []
    for coluna, rotulo, icone in (("margem_litro", "Melhor LB por litro", "📈"),
                                  ("mix_aditivada", "Mais aditivada vendida", "⛽"),
                                  ("var_litros", "Maior crescimento", "🚀"),
                                  ("pontualidade", "Planilha mais pontual", "⏱️")):
        # Empate no topo (todos com 100% de pontualidade) não é destaque de ninguém.
        if p[coluna].notna().any() and (p[coluna] == p[coluna].max()).sum() == 1:
            m = p.loc[p[coluna].idxmax()]
            cartoes.append(ui.kpi(rotulo, ui.esc(m["posto"].replace("B2 ", "")),
                                  reuniao.formatar(coluna, m[coluna]), icone))
    ui.grade_kpis(cartoes)

    ui.secao("Pauta por gerente", "O que levar para a conversa, do mais grave ao elogio. A ficha sai pronta "
             "para imprimir, com espaço para os combinados.")
    curtos = {x.replace("B2 ", ""): x for x in p["posto"]}
    escolha = st.segmented_control("Gerente", list(curtos), default=list(curtos)[0], key="reuniao_posto",
                                   label_visibility="collapsed") or list(curtos)[0]
    posto = curtos[escolha]
    linha = p[p["posto"] == posto].iloc[0]
    gerente = next((u.nome for u, _ in auth.usuarios().values() if u.posto == posto), "")
    with st.container(border=True):
        ui.bloco_titulo(f"⛽ {posto}", f"Gerente: {ui.esc(gerente)}" if gerente else "")
        ui.md('<ul class="pauta">' + "".join(f"<li>{ui.esc(i)}</li>" for i in reuniao.pauta(linha, rede, p))
              + "</ul>")
        st.download_button("⬇️ Baixar a ficha da reunião", type="primary",
                           data=reuniao.ficha_html(linha, rede, p, per, auth.modo_demo()),
                           file_name=f"Reuniao {posto} {per.mes:02d}-{per.ano}.html", mime="text/html")

    with st.expander("Por que estes indicadores"):
        ui.md(f"""
* **Volume** contra os mesmos dias do mês anterior — atendimento, pista, concorrência.
* **Margem bruta por litro** contra a média da rede — preço de bomba e compra bem feita.
* **Aditivada na gasolina** (meta {format_pct_simples(reuniao.META_MIX_ADITIVADA, 0)}) — é venda ativa do
  frentista: margem que não depende de subir preço.
* **Perda no LMC** (meta até {format_pct_simples(reuniao.META_PERDA, 2)}) — cuidado com tanque e bomba, e o
  primeiro sinal de desvio.
* **Despesa e resultado por litro** — o posto como negócio, não só como bomba.
* **Planilha até as {reuniao.HORA_LIMITE_ENVIO}h** (meta {format_pct_simples(reuniao.META_PONTUALIDADE, 0)}
  dos dias) — sem dado no horário, o dono decide no escuro.
* **Dias com estoque crítico** — pedido feito tarde à distribuidora.
* **Dias alterados depois de enviados** — da trilha de auditoria. O ideal é zero.

O placar também vai para o celular: no **💬 B2 Assistente**, o disparo "📋 Placar das gerências" sai toda
segunda às 8h (ou peça "reunião" ao robô).
""")


# ============================================================ admin =========
def pagina_admin():
    ui.topo("⚙️ Administração", "Usuários, regras dos alertas e a saúde da base.")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        ui.bloco_titulo("Usuários e perfis",
                        "Modo demonstração — senha de todos: b2demo" if auth.modo_demo()
                        else "Usuários do secrets.toml")
        linhas = [[f"<b>{ui.esc(u.login)}</b>", ui.esc(u.nome), u.perfil_nome, ui.esc(u.posto or "Todos")]
                  for u, _ in auth.usuarios().values()]
        ui.md(ui.tabela_html([("Login", False), ("Nome", False), ("Perfil", False), ("Posto", False)], linhas))
        ui.nota("O gerente vê e alimenta só o próprio posto — ele não escolhe. Para cadastrar usuários de "
                "verdade, veja o README (seção <i>Usuários</i>).")
    with c2, st.container(border=True):
        ui.bloco_titulo("Regras dos alertas", "Limites em src/alertas.py e src/analytics.py")
        regras = [
            ["🔴 Estoque crítico", f"autonomia abaixo de {format_decimal(an.AUTONOMIA_CRITICA, 1)} dia"],
            ["🟡 Estoque baixo", f"autonomia abaixo de {format_decimal(an.AUTONOMIA_ATENCAO, 1)} dias"],
            ["🔴 Perda no LMC", f"acima de {format_pct_simples(an.TOLERANCIA_PERDA, 1)} do vendido no mês"],
            ["🟡 Margem em queda", f"margem/L dos últimos 7 dias {format_pct_simples(al.QUEDA_MARGEM_ATENCAO, 0)} "
                                  "abaixo dos 30 dias anteriores"],
            ["🟡 Margem abaixo do histórico", f"{format_decimal(al.MARGEM_ABAIXO_HISTORICO_PP, 1)} p.p. abaixo "
                                             "da média de 12 meses"],
            ["🟡 Venda fora do padrão", f"últimos 7 dias {format_pct_simples(-al.VENDA_ABAIXO_ATENCAO, 0)} "
                                       "abaixo da média de 8 semanas"],
            ["🟡 Dados desatualizados", f"{al.DIAS_SEM_ENVIO} dias atrás dos outros postos"],
            ["🔴 Dados alterados depois de recebidos", f"dia já recebido mudou {auditoria.DIAS_CRITICO}+ dias "
                                                       "depois, ou mês já fechado"],
        ]
        ui.md(ui.tabela_html([("Alerta", False), ("Dispara quando", False)], regras))
    with st.container(border=True):
        ui.bloco_titulo("Desconto do boleto por distribuidora", "R$ por litro abatido no boleto")
        distrib = sorted(set(D["compras"]["distribuidora"].astype(str))) if len(D["compras"]) else []
        tabela = D["descontos"].rename(columns={"distribuidora": "Distribuidora", "produto": "Produto",
                                                "desconto": "Desconto (R$/L)"})
        editada = st.data_editor(
            tabela, num_rows="dynamic", hide_index=True, key="editor_descontos", width="stretch",
            column_config={
                "Distribuidora": st.column_config.TextColumn("Distribuidora", help="Como aparece nas notas: "
                                                             + (", ".join(distrib) or "ainda sem compras"), required=True),
                "Produto": st.column_config.SelectboxColumn("Produto", options=[descontos.TODOS] + theme.COMBUSTIVEIS,
                                                            default=descontos.TODOS),
                "Desconto (R$/L)": st.column_config.NumberColumn("Desconto (R$/L)", min_value=0.0,
                                                                 max_value=descontos.MAX_DESCONTO, step=0.005, format="%.3f"),
            })
        if st.button("Salvar descontos", key="salvar_descontos"):
            avisos = descontos.gravar(editada.rename(columns={"Distribuidora": "distribuidora", "Produto": "produto",
                                                              "Desconto (R$/L)": "desconto"}))
            carregar.clear()
            st.toast("Descontos salvos: as contas foram refeitas." + (" " + " ".join(avisos) if avisos else ""))
            st.rerun()
        ui.nota("Na nuvem, para valer de vez, edite <code>data/descontos_boleto.csv</code> e envie ao GitHub.")
    with st.container(border=True):
        info = D["info"]
        ui.bloco_titulo("Base de dados", f"Montada em {datetime.fromisoformat(info['gerado_em']):%d/%m/%Y às %H:%M} · "
                        f"armazenamento: {'GitHub' if arm.modo() == 'github' else 'nesta máquina'}")
        arquivos = pd.DataFrame(info.get("arquivos", []))
        if len(arquivos):
            resumo = arquivos.groupby("posto").agg(meses=("mes", "count"), linhas=("linhas", "sum"))
            linhas = [[p, format_int(r["meses"]), format_int(r["linhas"]), f"{an.ultima_data(DF, p):%d/%m/%Y}"]
                      for p, r in resumo.reindex(POSTOS).iterrows()]
            ui.md(ui.tabela_html([("Posto", False), ("Planilhas", True), ("Linhas", True), ("Dados até", True)],
                                 linhas))
        for e in info.get("erros", []):
            st.error(e)
        for a in info.get("avisos", []):
            st.warning(a)
        if not info.get("erros") and not info.get("avisos"):
            ui.nota("✅ Nenhum erro ou aviso na última montagem da base.")
        novas = base.planilhas_mais_novas_que_a_base()
        if novas:
            st.warning(f"Há {len(novas)} planilha(s) salvas depois da última montagem da base "
                       f"({', '.join(novas[:3])}…). Rode o Atualizar Dados.")
    if auth.modo_demo():
        with st.container(border=True):
            ui.bloco_titulo("Demonstração", "Desfaz os envios de teste e volta aos dados simulados originais.")
            if st.button("🔄 Restaurar os dados da demonstração"):
                with st.spinner("Gerando as planilhas simuladas e remontando a base…"):
                    r = subprocess.run([sys.executable, str(RAIZ / "gerar_dados_simulados.py")], cwd=RAIZ,
                                       capture_output=True, text=True, encoding="utf-8")
                    r2 = subprocess.run([sys.executable, str(RAIZ / "gerar_base.py")], cwd=RAIZ,
                                        capture_output=True, text=True, encoding="utf-8")
                for pasta in (base.PASTA_DADOS).glob("*/_versoes"):
                    for v in pasta.glob("*.xlsx"):
                        v.unlink()
                st.cache_data.clear()
                (st.success if r.returncode == 0 and r2.returncode == 0 else st.error)(
                    "Dados da demonstração restaurados." if r.returncode == 0 else r.stderr[-800:])


# ============================================================ roteamento ====
pagina = lateral()
if pagina.startswith("🎯"):
    pagina_central()
elif pagina.startswith("💬") and usuario.ve_rede:
    assistente_ui.pagina(DF, D["tanques"], POSTOS)
elif pagina.startswith("🛡️") and usuario.ve_rede:
    pagina_auditoria()
elif pagina.startswith("📡") and usuario.ve_rede:
    radar_ui.pagina()
elif pagina.startswith("📋") and usuario.ve_rede:
    pagina_reuniao()
elif pagina.startswith("🏠"):
    pagina_rede()
elif pagina == "⛽ Meu Posto":
    pagina_posto(usuario.posto)
elif pagina.startswith("⛽"):
    pagina_posto(pagina.replace("⛽ ", "", 1))
elif pagina.startswith("📤"):
    pagina_envio()
elif pagina.startswith("🔔"):
    pagina_alertas()
elif pagina.startswith("📑"):
    pagina_atualizacoes()
elif pagina.startswith("⚙️"):
    pagina_admin()
