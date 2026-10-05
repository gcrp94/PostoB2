"""Tela 📡 Radar de Mercado (protótipo): onde cada unidade do B2 está contra a cidade.

Só desenha: as contas moram em `mercado.py`. Os dados são PÚBLICOS e REAIS (pesquisa
semanal da ANP) — diferente do resto do painel, que na demonstração é simulado — e a
tela avisa isso, e avisa também o que a pesquisa não enxerga (amostra; Candói fora).

Duas situações entre as unidades de Guarapuava:

* **a ANP pesquisa o posto** (Centro, Índio): há histórico de preço, posição, repasse;
* **a ANP nunca pesquisou** (Bonsucesso, Primavera): a tela mostra a vizinhança e deixa
  o dono informar o preço do próprio posto, para ver onde ele ficaria. (Com a planilha
  do B2, o preço próprio vem do "preço médio" diário, sem digitar.)

Quando existe coleta local do Menor Preço (`coletar_nota_parana.py`), a tela ganha uma
segunda aba com o preço da NOTA FISCAL, hoje, de todos os postos da cidade. Sem coleta
(na nuvem, por exemplo), a aba não aparece.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from src import charts, mercado, nota_parana, theme, ui
from src.formatting import format_brl, format_pct_simples

GASOLINAS = ("Gasolina Comum", "Gasolina Aditivada")
ANP = {nome: chave for chave, nome in mercado.PRODUTOS.items()}      # "Gasolina Comum" -> "GASOLINA"
TERMOS_RAZAO = ("LTDA", "LTD", "EIRELI", "S/A", "ME", "EPP", "COMERCIO VAREJISTA DE COMBUSTIVEIS", "COMERCIO DE COMBUSTIVEIS",
                "DE COMBUSTIVEIS", "COMBUSTIVEIS", "COMERCIO", "AUTO POSTO", "POSTO")


@st.cache_data(show_spinner="Carregando o radar…")
def _carregar(assinatura: tuple):
    return mercado.carregar()


def _curto(razao: str) -> str:
    """Razão social -> nome curto. Tira só PALAVRAS inteiras (um " ME" solto comia o começo de "METROPOLITANO")."""
    nome = " ".join(razao.upper().replace(".", "").split())
    for termo in TERMOS_RAZAO:
        nome = re.sub(rf"(?<![\w/]){re.escape(termo)}(?![\w/])", " ", nome)
    return " ".join(nome.split()).title() or razao.title()


def _nome_posto(linha) -> str:
    """O B2 pelo nome que o dono usa; os demais pelo nome curto da razão social + bairro."""
    if linha["eh_b2"]:
        return mercado.NOMES_B2.get(linha.get("cnpj", ""), f"B2 · {str(linha['bairro']).title()}")
    return f"{_curto(linha['revenda'])} · {str(linha['bairro']).title()}"


def _sinal(v: float) -> str:
    return ("+" if v > 0 else "") + format_brl(v)


def _centavos(v: float) -> str:
    c = round(v * 100)
    return "igual" if c == 0 else f"{'+' if c > 0 else '−'}{abs(c)} centavos"


@st.cache_data(show_spinner=False)
def _carregar_np(assinatura: tuple):
    return nota_parana.carregar()


def pagina():
    ui.topo("📡 Radar de Mercado", "Onde o B2 está contra a cidade · preços de bomba · dados públicos reais",
            selo="PROTÓTIPO")
    of = _carregar_np(nota_parana.assinatura())
    if of is None or of.empty:
        _aba_anp()                      # na nuvem (e antes da 1ª coleta) só existe a ANP
        return
    aba_anp, aba_np = st.tabs(["📊 ANP · semanal", "⛽ Menor Preço · hoje (teste local)"])
    with aba_anp:
        _aba_anp()
    with aba_np:
        _aba_menor_preco(of)


def _aba_anp():
    m = _carregar(mercado.assinatura())
    if m is None:
        st.info("O radar ainda não foi montado. Rode o **atualizar_mercado.py** (baixa os preços públicos da ANP).")
        return
    unidades = mercado.unidades_b2(m.cadastro, m.precos)
    # Candói fica de fora por enquanto: a ANP não pesquisa preço lá.
    unidades = unidades[unidades["municipio"] == "GUARAPUAVA"].reset_index(drop=True)
    if unidades.empty:
        st.warning("Nenhuma unidade do B2 de Guarapuava foi achada no cadastro da ANP.")
        return

    c1, c2, c3 = st.columns([1.2, 2.2, 1.4], vertical_alignment="bottom")
    nome = c1.selectbox("Unidade", unidades["nome"].tolist(), key="radar_unidade")
    produto = c2.segmented_control("Combustível", theme.COMBUSTIVEIS, default=theme.COMBUSTIVEIS[0], key="radar_produto",
                                   format_func=lambda p: f"{theme.ICONES_COMBUSTIVEL[p]} {theme.ROTULO_CURTO[p]}") \
        or theme.COMBUSTIVEIS[0]
    janela = c3.segmented_control("Comparar com", [30, 60, 90], default=30, key="radar_janela",
                                  format_func=lambda d: f"{d} dias") or 30

    un = unidades[unidades["nome"] == nome].iloc[0]
    cnpj, chave, pesquisado = un["cnpj"], ANP[produto], bool(un["tem_preco"])
    precos = m.precos[m.precos["municipio"] == un["municipio"]]
    f = mercado.foto(precos, chave)
    ultima = pd.Timestamp(m.info.get("ultima_coleta", f["data"].max() if len(f) else pd.Timestamp.today()))
    if f.empty:
        st.info(f"Sem coleta recente de {produto.lower()} em {mercado.NOME_MUNICIPIO[un['municipio']]}.")
        return

    if pesquisado:
        if cnpj not in f.index:
            st.info(f"Sem coleta recente de {produto.lower()} para o {nome} (últimos {mercado.JANELA_FOTO} dias).")
            return
        rotulo_preco, legenda_preco = f"Preço do {nome}", ""
    else:
        ui.nota(f"<b>A ANP nunca pesquisou o preço do {nome}</b> (nenhuma coleta em {m.info.get('primeira_coleta', '')[:7]} a "
                f"{m.info.get('ultima_coleta', '')[:7]}). Abaixo, a vizinhança dele; informe o preço do posto hoje para ver onde ficaria. "
                "Com a planilha do B2, esse preço vem do “preço médio” diário, sem digitar.")
        mediana = float(f["preco"].median())
        informado = st.number_input(f"Preço de {produto.lower()} no {nome} hoje (R$/L)", min_value=2.0, max_value=12.0,
                                    value=round(mediana, 2), step=0.01, format="%.2f", key=f"radar_inf_{nome}_{chave}")
        f = mercado.com_preco_informado(f, un, chave, informado, ultima)
        rotulo_preco, legenda_preco = f"Preço do {nome}", " (informado)"
    pos = mercado.posicao(f, cnpj)
    barato = f.sort_values("preco").iloc[0]

    ui.md(f'<div class="secao-sub">Foto de {pos["data"]:%d/%m/%Y} · {pos["n"]} postos com preço nas últimas duas semanas · '
          f"preço de bomba anotado pela ANP</div>")
    ui.grade_kpis([
        ui.kpi(rotulo_preco + legenda_preco, format_brl(pos["preco"]),
               ui.delta_html(pos["preco"] - pos["media"], "neutra", "rs_litro") + " vs média da cidade", "🏷️", "destaque"),
        ui.kpi("Média da cidade", format_brl(pos["media"]), f"mediana {format_brl(pos['mediana'])} · "
               f"de {format_brl(pos['minimo'])} a {format_brl(pos['maximo'])}", "🏙️"),
        ui.kpi("Posição de preço", f"{pos['posicao']}º mais barato", f"de {pos['n']} postos", "📍"),
        ui.kpi("Mais barato agora", format_brl(barato["preco"]),
               f"{_nome_posto(barato.to_dict() | {'cnpj': barato.name})} · {barato['bandeira']}", "🥇"),
    ])

    # --- semana a semana e repasse (só para quem a ANP pesquisa)
    if pesquisado:
        s = mercado.serie_semanal(precos, chave, cnpj)
        r = mercado.ranking_historico(s)
        with st.container(border=True):
            ui.bloco_titulo("Semana a semana", f"{produto} · a faixa cinza é de onde ao onde a cidade variou",
                            pergunta="Onde estivemos em relação à cidade?")
            if len(s) >= 4:
                st.plotly_chart(charts.radar_serie(s, produto, nome), width="stretch", config=charts.CFG)
                ui.nota(f"Nas {r['semanas']} semanas com pesquisa, o {nome} foi o <b>mais barato em "
                        f"{format_pct_simples(r['primeiro'] * 100, 0)}</b> delas e um dos <b>3 mais baratos em "
                        f"{format_pct_simples(r['top3'] * 100, 0)}</b> ({produto.lower()}).")
            else:
                ui.nota("Poucas semanas com pesquisa para este combustível.")

        inicio = ultima - pd.Timedelta(days=int(janela))
        v = mercado.variacao(precos, chave, inicio, ultima)
        with st.container(border=True):
            ui.bloco_titulo("Quem mexeu no preço", f"{produto} · variação de {inicio:%d/%m} a {ultima:%d/%m}, "
                            "só postos com preço nas duas pontas", pergunta="Quem repassou o custo, e quanto?")
            if len(v) >= 4 and cnpj in set(v["cnpj"]):
                st.plotly_chart(charts.radar_variacao(v, [_nome_posto(l) for _, l in v.iterrows()], 70 + 30 * len(v)),
                                width="stretch", config=charts.CFG)
                b = float(v.loc[v["cnpj"] == cnpj, "variacao"].iloc[0])
                ui.nota(f"{len(v)} postos comparáveis: mediana {_sinal(float(v['variacao'].median()))}, de "
                        f"{_sinal(float(v['variacao'].min()))} a {_sinal(float(v['variacao'].max()))}. "
                        f"O <b>{nome}</b> mexeu <b>{_sinal(b)}</b>.")
            else:
                ui.nota("Poucos postos com preço nas duas datas para comparar. Tente outra janela.")
    else:
        with st.container(border=True):
            ui.bloco_titulo("Histórico e repasse", "Sem série para este posto",
                            pergunta="E o que aconteceu com o nosso preço?")
            ui.nota(f"Como a ANP não colhe o {nome}, não há série de preços dele aqui. O histórico e o tempo de repasse dele "
                    "virão da planilha do próprio B2 (preço médio diário), que é mais exata que a pesquisa.")

    # --- a foto da cidade, com o bairro em destaque
    bairro = un["bairro"]
    with st.container(border=True):
        ui.bloco_titulo("A cidade agora", f"{produto} · do mais barato ao mais caro · "
                        f"no bairro {str(bairro).title()}: {int((f['bairro'] == bairro).sum())} postos com preço",
                        pergunta="Quem está ao nosso redor?")
        f2 = f.reset_index().sort_values(["preco", "revenda"])
        linhas = []
        for _, l in f2.iterrows():
            nome_l = _nome_posto(l) + (" (informado)" if l["cnpj"] == cnpj and not pesquisado else "")
            texto = f"<b>{nome_l}</b>" if l["eh_b2"] else nome_l
            vizinho = " 📍" if (l["bairro"] == bairro and not (l["cnpj"] == cnpj)) else ""
            linhas.append([texto + vizinho, ui.esc(l["bandeira"]), format_brl(l["preco"]), _centavos(l["preco"] - pos["preco"]),
                           f"{l['data']:%d/%m}"])
        ui.md('<div style="max-height:420px;overflow-y:auto">' + ui.tabela_html(
            [("Posto", False), ("Bandeira", False), ("Preço", True), (f"vs {nome}", True), ("Coleta", True)], linhas) + "</div>")
        ui.nota("📍 = no mesmo bairro do posto.")

    # --- achados
    achados = []
    prem = mercado.premio_aditivada(precos, cnpj) if (pesquisado and produto in GASOLINAS) else None
    if prem:
        if prem["sempre_igual"]:
            achados.append(f"A aditivada custou <b>o mesmo que a comum</b> em todas as {prem['coletas']} coletas do {nome}. "
                           f"No mercado de Guarapuava, a aditivada custa em mediana <b>{format_brl(prem['mercado_mediana'])}</b> a mais.")
        else:
            achados.append(f"Prêmio da aditivada sobre a comum: {nome} {format_brl(prem['unidade'])}; "
                           f"mercado (mediana) {format_brl(prem['mercado_mediana'])}.")
    if achados:
        with st.container(border=True):
            ui.bloco_titulo("Achado para conversar", "Dado público, sem juízo: serve para perguntar a estratégia por trás")
            ui.md('<ul class="pauta">' + "".join(f"<li>{a}</li>" for a in achados) + "</ul>")

    # --- o que o radar vê e não vê
    cob = mercado.cobertura(m.precos, m.cadastro)
    mesmo_bairro = m.cadastro[(m.cadastro["municipio"] == un["municipio"]) & (m.cadastro["bairro"] == bairro)]
    bandeiras = ", ".join(f"{n} {b}" for b, n in mesmo_bairro["bandeira"].value_counts().items())
    sim = ", ".join(unidades.loc[unidades["tem_preco"], "nome"])
    nao = ", ".join(unidades.loc[~unidades["tem_preco"], "nome"]) or "nenhuma"
    with st.expander("O que este radar vê e o que não vê"):
        ui.md(f"""
* **É amostra.** A ANP colheu preço de {cob['amostrados']} dos {cob['cadastrados']} postos cadastrados em Guarapuava nos
  últimos {cob['dias']} dias. **Candói não é pesquisado** (8 postos cadastrados, nenhum com preço) e fica de fora por enquanto.
* **Só algumas unidades do B2 são pesquisadas.** Com preço: {sim}. Sem preço: {nao}.
* **É preço de bomba anotado por um pesquisador**, não o preço da nota fiscal. O preço real de venda, quase em tempo real,
  está no Nota Paraná (Menor Preço): **teste local na outra aba** (ainda depende do aval do estado para virar produto).
* **No bairro {str(bairro).title()}** há {len(mesmo_bairro)} postos cadastrados na ANP: {bandeiras}.
* Dados da ANP até {ultima:%d/%m/%Y}; atualização semanal ({m.info.get('fonte', 'dados abertos da ANP')}).
""")


# ------------------------------------------------- aba Menor Preço (teste local) ---
UNIDADES_NP = [n for n in mercado.ORDEM_B2 if n != "B2 Candói"]
CNPJ_DA_UNIDADE = {nome: cnpj for cnpj, nome in mercado.NOMES_B2.items()}


def _quando(dt) -> str:
    minutos = int((nota_parana.agora_brt() - pd.Timestamp(dt)).total_seconds() // 60)
    if minutos < 1:
        return "agora"
    if minutos < 60:
        return f"há {minutos} min"
    if minutos < 24 * 60:
        return f"há {minutos // 60} h"
    return f"{pd.Timestamp(dt):%d/%m %H:%M}"


def _bandeira_np(razao: str, fantasia: str) -> str:
    for texto in (razao, fantasia):
        if " - " in texto:
            return texto.split(" - ", 1)[0].strip().title()
    return "—"


def _nome_np(linha) -> str:
    """O B2 pelo nome que o dono usa; os demais pelo nome fantasia (ou a razão, encurtada) + bairro."""
    if linha["unidade_b2"]:
        return linha["unidade_b2"]
    fantasia = str(linha["fantasia"]).split(" - ", 1)[-1].strip()
    nome = _curto(fantasia or str(linha["razao"]).split(" - ", 1)[-1])
    return f"{nome} · {str(linha['bairro']).title()}"


def _aba_menor_preco(of: pd.DataFrame):
    est = nota_parana.estado(of)
    ui.md('<div class="secao-sub">O que a bomba cobrou de verdade: o preço sai da <b>nota fiscal (NFC-e)</b> e chega ao app '
          "Menor Preço do Paraná em minutos. Teste local: a coleta roda no seu computador, uma vez por dia.</div>")
    if est["interrompida"]:
        st.warning(f"A última tentativa de coleta foi interrompida: {est['interrompida']['mensagem']}")

    produto = st.segmented_control("Combustível", theme.COMBUSTIVEIS, default=theme.COMBUSTIVEIS[0], key="radar_np_produto",
                                   format_func=lambda p: f"{theme.ICONES_COMBUSTIVEL[p]} {theme.ROTULO_CURTO[p]}") \
        or theme.COMBUSTIVEIS[0]
    f = nota_parana.foto(of, produto, horas=48)
    if f.empty:
        st.info(f"Nenhuma nota de {produto.lower()} nas últimas 48 horas na coleta.")
        return
    r = nota_parana.resumo(f)
    barato = f.sort_values(["preco", "datahora"]).iloc[0]
    m = _carregar(mercado.assinatura())
    conf = nota_parana.conferir_cadastro(of, m.cadastro) if m is not None else pd.DataFrame()
    ui.grade_kpis([
        ui.kpi("Média da cidade", format_brl(r["media"]), f"mediana {format_brl(r['mediana'])} · "
               f"de {format_brl(r['minimo'])} a {format_brl(r['maximo'])}", "🏙️", "destaque"),
        ui.kpi("Mais barato agora", format_brl(barato["preco"]), f"{_nome_np(barato)} · {_quando(barato['datahora'])}", "🥇"),
        ui.kpi("Postos com nota", f"{r['n']}", "nas últimas 48 h" + (
            f" · {int(conf['achado'].sum())} dos {len(conf)} cadastrados na ANP já apareceram" if len(conf) else ""), "📍"),
        ui.kpi("Última coleta", f"{est['ultima']:%d/%m %H:%M}" if est["ultima"] is not None else "—",
               f"{est['dias']} dia(s) de histórico · {est['ofertas']:,} notas".replace(",", "."), "🗓️"),
    ])

    # --- o B2 hoje, lado a lado com a pesquisa da ANP
    anp = mercado.foto(m.precos, ANP[produto], janela=45) if m is not None else pd.DataFrame()
    por_unidade = {b["unidade"]: b for b in r["b2"]}
    linhas = []
    for nome in UNIDADES_NP:
        b = por_unidade.get(nome)
        a = anp.loc[CNPJ_DA_UNIDADE[nome]] if len(anp) and CNPJ_DA_UNIDADE.get(nome) in anp.index else None
        pesquisa = f"{format_brl(a['preco'])} · {a['data']:%d/%m}" if a is not None else "não pesquisa"
        if b:
            linhas.append([f"<b>{nome}</b>", format_brl(b["preco"]), _centavos(b["preco"] - r["media"]),
                           f"{b['posicao']}º de {r['n']}", _quando(b["datahora"]), pesquisa])
        else:
            linhas.append([f"<b>{nome}</b>", "—", "—", "—", "sem nota nas últimas 48 h", pesquisa])
    with st.container(border=True):
        ui.bloco_titulo("O B2 agora", f"{produto} · preço da última nota de cada unidade, contra a cidade e contra a pesquisa da ANP",
                        pergunta="Onde estamos e o que o cliente está pagando?")
        ui.md(ui.tabela_html([("Unidade", False), ("Preço na nota", True), ("vs média da cidade", True), ("Posição", True),
                              ("Última nota", True), ("ANP (pesquisador)", True)], linhas))
        faltam = [n for n in UNIDADES_NP if n not in por_unidade]
        if faltam:
            ui.nota(f"{', '.join(faltam)}: o Menor Preço não mostrou nota de {produto.lower()} nas últimas 48 horas. "
                    "Pode ser que o posto não tenha vendido o produto, ou que o app ainda não o liste — vale conferir.")

    # --- mapa e lista da cidade
    nomes = [_nome_np(l) for _, l in f.iterrows()]
    with st.container(border=True):
        ui.bloco_titulo("A cidade no mapa", f"{produto} · {r['n']} postos · B2 em laranja · a posição é aproximada",
                        pergunta="Quem está ao redor de cada unidade?")
        st.plotly_chart(charts.radar_mapa(f, nomes), width="stretch", config={**charts.CFG, "scrollZoom": True})
    with st.container(border=True):
        ui.bloco_titulo("Ranking agora", f"{produto} · do mais barato ao mais caro", pergunta="Quem cobra quanto?")
        ordenado = f.assign(_nome=nomes).sort_values(["preco", "datahora"])
        tabela = []
        for _, l in ordenado.iterrows():
            nome_l = f"<b>{l['_nome']}</b>" if l["unidade_b2"] else ui.esc(l["_nome"])
            tabela.append([nome_l, ui.esc(_bandeira_np(l["razao"], l["fantasia"])), format_brl(l["preco"]),
                           _centavos(l["preco"] - r["media"]), _quando(l["datahora"])])
        ui.md('<div style="max-height:420px;overflow-y:auto">' + ui.tabela_html(
            [("Posto", False), ("Bandeira", False), ("Preço", True), ("vs média", True), ("Última nota", True)], tabela) + "</div>")

    # --- a série, que só existe depois de alguns dias de coleta
    h = nota_parana.historico_diario(of, produto)
    unidades_h = [n for n in UNIDADES_NP if n in h.columns]
    with st.container(border=True):
        ui.bloco_titulo("Dia a dia", f"{produto} · a faixa cinza é de onde ao onde a cidade variou",
                        pergunta="Como o preço andou desde que começamos a coletar?")
        if len(h) >= 2 and unidades_h:
            nome_h = st.selectbox("Unidade", unidades_h, key="radar_np_unidade")
            st.plotly_chart(charts.radar_dia(h, produto, nome_h), width="stretch", config=charts.CFG)
        else:
            ui.nota("A série começa a aparecer no <b>segundo dia de coleta</b>. Cada dia entra com a última nota de cada posto; "
                    "com algumas semanas dá para ver quem repassa o custo primeiro e em quantos dias.")

    # --- achado: aditivada contra comum
    prem = nota_parana.premio_aditivada(of)
    achados = []
    if len(prem):
        mercado_prem = prem[prem["unidade_b2"] == ""]["premio"]
        for nome in UNIDADES_NP:
            p = prem[prem["unidade_b2"] == nome]
            if len(p) and len(mercado_prem) >= 3:
                v = float(p["premio"].iloc[0])
                achados.append(f"No <b>{nome}</b> a aditivada custa <b>{format_brl(v) if abs(v) >= 0.005 else 'o mesmo preço'}</b>"
                               f"{'' if abs(v) < 0.005 else ' a mais'} que a comum; nos outros {len(mercado_prem)} postos "
                               f"a mediana da diferença é <b>{format_brl(float(mercado_prem.median()))}</b>.")
    if achados:
        with st.container(border=True):
            ui.bloco_titulo("Achado para conversar", "Dado público, sem juízo: serve para perguntar a estratégia por trás")
            ui.md('<ul class="pauta">' + "".join(f"<li>{a}</li>" for a in achados) + "</ul>")

    if len(conf) and not conf["achado"].all():
        ausentes = conf[~conf["achado"]].sort_values(["eh_b2", "razao"], ascending=[False, True])
        with st.expander(f"Cadastrados na ANP que a varredura não achou ({len(ausentes)})"):
            itens = [f"* {'**' if a['eh_b2'] else ''}{a['razao'].title()}{'**' if a['eh_b2'] else ''} · {a['endereco'].title()} · "
                     f"{a['bairro'].title()}" + (" ← B2" if a["eh_b2"] else "") for _, a in ausentes.iterrows()]
            ui.md("Postos que a ANP tem em Guarapuava e que nunca apareceram no Menor Preço durante a coleta. Podem ter parado de "
                  "vender, não emitir NFC-e com o combustível, estar fora da área varrida ou ter outro endereço no app.\n\n"
                  + "\n".join(itens))

    with st.expander("Como esta aba funciona e o que ela não é"):
        ui.md(f"""
* **A fonte** é o app público *Menor Preço* (Nota Paraná): o último preço de cada combustível que apareceu numa NFC-e, de todo
  posto que emite nota. Diferente da ANP, não é amostra nem preço anotado: é o que o cliente pagou, minutos depois.
* **A coleta** roda **uma vez por dia**: 4 a 8 consultas a partir do centro da cidade (cobre todos os postos que o app mostra),
  com pausa de 8 a 20 segundos entre elas. Uma vez por mês faz também a **varredura da cidade em {len(nota_parana.CENTROS)} pontos**
  (uns 15 minutos), para achar posto novo na periferia. O acesso se identifica com clareza; se o servidor negar ou mudar, a
  coleta **para** e anota — não insiste.
* **É teste local:** os dados ficam só neste computador (`data/mercado/nota_parana/`, fora do Git) e esta aba não aparece na nuvem.
  Antes de virar produto, falta o aval do estado (e-mail ao suporte do Nota Paraná).
* **Limites:** o app não mostra CNPJ (o B2 é reconhecido pelo endereço); a posição no mapa é aproximada; o nome do combustível
  é o que o posto escreveu na nota (a V-Power, por exemplo, é lida como aditivada); só aparece quem vendeu nas últimas 48 h.
""")
