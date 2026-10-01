"""Tela 💬 B2 Assistente e os "ouvintes" do celular (Telegram e ntfy).

Os ouvintes vivem no processo do painel (um por processo, `st.cache_resource`)
e continuam respondendo enquanto a janela do `Abrir App.bat` estiver aberta,
em qualquer tela — ou até sem ninguém com o painel aberto no navegador.

A configuração fica em `config_assistente.local.json` (fora do Git): o token
do robô do Telegram fica SÓ nesta máquina. Publicado, use as variáveis
`B2_TELEGRAM_TOKEN` e `B2_ASSISTENTE_TOPICO`.

Os dois canais respondem SÓ com a base da demonstração (`data/SIMULADO.txt`):
quem acha o robô ou o tópico não chega a dado real por aqui.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import streamlit as st

from src import armazenamento, assistente, auditoria, base, ui
from src import assistente_agenda as agenda
from src import assistente_telegram as tg
from src.assistente_ntfy import ServicoNtfy

CONFIG_LOCAL = base.RAIZ / "config_assistente.local.json"
_TRAVA_ARQUIVO = threading.RLock()


# ------------------------------------------------------------ configuração ---
def configuracao() -> dict:
    cfg = {"servidor": "https://ntfy.sh", "topico": "", "ativo": False,
           "telegram_token": "", "telegram_ativo": False, "telegram_chats": [], "telegram_nomes": {},
           "agenda_estado": {}}
    with _TRAVA_ARQUIVO:
        if CONFIG_LOCAL.exists():
            try:
                cfg.update(json.loads(CONFIG_LOCAL.read_text(encoding="utf-8")))
            except ValueError:
                pass            # arquivo corrompido: volta ao padrão, sem derrubar o painel
    # Na Streamlit Cloud não há o arquivo local: as chaves de primeiro nível do
    # Secrets viram variáveis de ambiente. Pôr o tópico lá já liga o ntfy.
    if os.environ.get("B2_ASSISTENTE_TOPICO"):
        cfg["topico"] = os.environ["B2_ASSISTENTE_TOPICO"]
        cfg["ativo"] = True
    if os.environ.get("B2_NTFY_SERVIDOR"):
        cfg["servidor"] = os.environ["B2_NTFY_SERVIDOR"]
    if os.environ.get("B2_TELEGRAM_TOKEN"):
        cfg["telegram_token"] = os.environ["B2_TELEGRAM_TOKEN"]
        cfg["telegram_ativo"] = True
    # Na nuvem o arquivo local some a cada reinício: as conversas fixas (o grupo
    # da diretoria) entram pelos Secrets, separadas por vírgula.
    if os.environ.get("B2_TELEGRAM_CHATS"):
        extras = [int(c) for c in os.environ["B2_TELEGRAM_CHATS"].split(",") if c.strip().lstrip("-").isdigit()]
        cfg["telegram_chats"] = sorted(set(cfg["telegram_chats"]) | set(extras))
    cfg["token"] = os.environ.get("B2_NTFY_TOKEN", "")
    return cfg


def _gravar(**mudancas):
    with _TRAVA_ARQUIVO:
        atual = {}
        if CONFIG_LOCAL.exists():
            try:
                atual = json.loads(CONFIG_LOCAL.read_text(encoding="utf-8"))
            except ValueError:
                atual = {}
        atual.update(mudancas)
        atual.pop("token", None)            # token do ntfy nunca vai para o arquivo
        temporario = CONFIG_LOCAL.with_suffix(".tmp")
        temporario.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(CONFIG_LOCAL)


def salvar_configuracao(servidor: str, topico: str, ativo: bool):
    """ntfy — valida o endereço antes de trocar uma configuração que já funciona."""
    ServicoNtfy(servidor, topico, _responder_celular)
    _gravar(servidor=servidor.rstrip("/"), topico=topico, ativo=ativo)


def _registrar_chat(chat_id: int, nome: str):
    cfg = configuracao()
    chats = set(cfg.get("telegram_chats", []))
    chats.add(int(chat_id))
    nomes = dict(cfg.get("telegram_nomes", {}))
    nomes[str(int(chat_id))] = nome
    _gravar(telegram_chats=sorted(chats), telegram_nomes=nomes)


def _remover_chat(chat_id: int):
    cfg = configuracao()
    chats = [c for c in cfg.get("telegram_chats", []) if int(c) != int(chat_id)]
    nomes = {k: v for k, v in cfg.get("telegram_nomes", {}).items() if k != str(int(chat_id))}
    _gravar(telegram_chats=chats, telegram_nomes=nomes)


# --------------------------------------------------------------- respostas ---
_CACHE = {"assinatura": None, "dados": None}
_TRAVA_CACHE = threading.Lock()


def assinatura_dados() -> tuple:
    """Muda quando a base, a auditoria ou o histórico de envios mudam."""
    envios = armazenamento.ARQ_ENVIOS
    return (base.assinatura(), auditoria.assinatura(),
            envios.stat().st_mtime_ns if envios.exists() else 0)


def _dados() -> dict:
    """Base, alertas e extras — recarregados só quando os dados mudam."""
    with _TRAVA_CACHE:
        assinatura = assinatura_dados()
        if _CACHE["assinatura"] != assinatura:
            _CACHE["dados"] = agenda.carregar_dados()
            _CACHE["assinatura"] = assinatura
        return _CACHE["dados"]


def demonstracao() -> bool:
    return (base.PASTA_DADOS / "SIMULADO.txt").exists()


def _responder_celular(comando: str) -> assistente.Resposta:
    # O canal da apresentação só expõe a base da demonstração.
    if not demonstracao():
        raise ValueError("Esta conexão é exclusiva da demonstração com dados simulados.")
    d = _dados()
    return assistente.responder(comando, d["df"], d["tanques"], d["postos"], simulado=True,
                                alertas=d["alertas"], extras=d["extras"])


def _ler_estado_agenda() -> dict:
    return dict(configuracao().get("agenda_estado", {}))


def _gravar_estado_agenda(estado: dict):
    _gravar(agenda_estado=estado)


# --------------------------------------------------------------- ouvintes ---
class Controle:
    """Um ouvinte de cada canal por processo, compartilhado entre sessões."""

    def __init__(self):
        self.ntfy: ServicoNtfy | None = None
        self.chave_ntfy: tuple | None = None
        self.telegram: tg.ServicoTelegram | None = None
        self.chave_telegram: str | None = None
        self.agendador: agenda.Agendador | None = None
        self.trava = threading.RLock()

    def enviar_programado(self, resposta) -> tuple[int, str]:
        """Os disparos automáticos saem por todos os canais ligados. (Método, e
        não função do módulo: o agendador roda numa thread, fora do Streamlit,
        e não pode chamar o `cache_resource` para achar os canais.)"""
        enviados, erro = 0, ""
        if self.telegram is not None:
            enviados, erro = self.telegram.enviar_para_todos(resposta)
        if self.ntfy is not None:
            ok, detalhe = self.ntfy.enviar(resposta)
            enviados += 1 if ok else 0
            erro = erro or ("" if ok else detalhe)
        return enviados, erro or ("" if enviados else "Nenhum canal conectado.")

    def ajustar(self, cfg: dict):
        with self.trava:
            # ntfy
            chave = (cfg["servidor"], cfg["topico"], cfg.get("token", ""))
            if self.ntfy and (self.chave_ntfy != chave or not cfg.get("ativo")):
                self.ntfy.parar()
                self.ntfy = None
            if cfg.get("ativo") and cfg["topico"]:
                if self.ntfy is None:
                    self.ntfy = ServicoNtfy(*chave[:2], _responder_celular, token=chave[2])
                    self.chave_ntfy = chave
                self.ntfy.iniciar()
            # Telegram
            token = cfg.get("telegram_token", "")
            if self.telegram and (self.chave_telegram != token or not cfg.get("telegram_ativo")):
                self.telegram.parar()
                self.telegram = None
            if cfg.get("telegram_ativo") and tg.token_valido(token):
                if self.telegram is None:
                    self.telegram = tg.ServicoTelegram(token, _responder_celular,
                                                       chats=cfg.get("telegram_chats", []),
                                                       ao_registrar=_registrar_chat,
                                                       ao_remover=_remover_chat,
                                                       nomes=cfg.get("telegram_nomes", {}))
                    self.chave_telegram = token
                self.telegram.iniciar()
            # Agendador: no ar sempre que houver um canal para mandar.
            if self.telegram is not None or self.ntfy is not None:
                if self.agendador is None:
                    self.agendador = agenda.Agendador(_dados, self.enviar_programado, assinatura_dados,
                                                      _ler_estado_agenda, _gravar_estado_agenda)
                self.agendador.iniciar()
            elif self.agendador is not None:
                self.agendador.parar()
                self.agendador = None


@st.cache_resource
def controle() -> Controle:
    return Controle()


def ouvintes() -> Controle:
    """O Controle em uso — trocado sozinho se o código mudou com o painel aberto.

    O Streamlit recarrega os módulos quando um arquivo muda, mas o
    `cache_resource` devolve o objeto que já estava na memória: de uma versão
    ANTIGA da classe, sem os atributos novos. Foi o "'Controle' object has no
    attribute 'telegram'" de 29/09/2026, com o Abrir App.bat aberto durante a
    atualização. Aqui o antigo é desligado (para não responder em dobro) e
    substituído.
    """
    c = controle()
    if isinstance(c, Controle):
        return c
    for nome in ("servico", "ntfy", "telegram", "agendador"):
        antigo = getattr(c, nome, None)
        if antigo is not None and hasattr(antigo, "parar"):
            try:
                antigo.parar()
            except Exception:
                pass
    controle.clear()
    return controle()

def iniciar_configurado():
    cfg = configuracao()
    # B2_ASSISTENTE_DESLIGADO: uma segunda janela do painel (teste) sem brigar
    # com a primeira pelo robô — dois ouvintes no mesmo robô = erro 409.
    if not demonstracao() or os.environ.get("B2_ASSISTENTE_DESLIGADO"):
        cfg["ativo"] = cfg["telegram_ativo"] = False
    ouvintes().ajustar(cfg)


def disparar_alertas() -> tuple[int, str]:
    """O momento da demonstração: os alertas da Central chegam ao celular."""
    servico = ouvintes().telegram
    if servico is None:
        return 0, "Conecte o Telegram primeiro."
    d = _dados()
    enviados, erro = 0, ""
    for a in [a for a in d["alertas"] if a.nivel == "critico"]:
        resposta = assistente.Resposta(f"{a.icone} {a.titulo} — {a.posto}", "\n".join(a.detalhes),
                                       ((f"⛽ Abrir {a.posto.replace('B2 ', '')}", f"resumo {a.posto}"),
                                        ("🚨 Todos os alertas", "alertas")))
        n, erro = servico.enviar_para_todos(resposta)
        enviados = max(enviados, n)
    return enviados, erro


# ------------------------------------------------------------------ tela -----
@st.fragment(run_every="3s")
def _estado_telegram():
    servico = ouvintes().telegram
    if servico is None:
        st.info("Telegram desconectado. Siga os 3 passos abaixo (leva 1 minuto).")
        return
    e = servico.status()
    if e["conectado"] and e["bot_usuario"]:
        st.success(f"🟢 Robô **@{e['bot_usuario']}** no ar · {e['chats']} conversa(s) · "
                   f"{e['respostas']} resposta(s) nesta sessão")
        st.link_button(f"📱 Abrir @{e['bot_usuario']} no Telegram", f"https://t.me/{e['bot_usuario']}",
                       type="primary", width="stretch")
    elif e["erro"]:
        st.warning(e["erro"])
    else:
        st.info("Conectando ao Telegram…")
    if e["ultimo_comando"]:
        st.caption(f"Última pergunta recebida: “{e['ultimo_comando']}”")


@st.fragment(run_every="3s")
def _estado_ntfy():
    servico = ouvintes().ntfy
    if servico is None:
        st.info("ntfy desconectado.")
        return
    e = servico.status()
    if e["conectado"]:
        st.success("🟢 Escutando o tópico no ntfy")
    elif e["erro"]:
        st.warning(f"Conexão em recuperação: {e['erro']}")
    else:
        st.info("Conectando ao ntfy…")
    if e["ultimo_comando"]:
        st.caption(f"Última pergunta recebida: “{e['ultimo_comando']}”")


def _telefone(pergunta: str, resposta: assistente.Resposta) -> str:
    botoes = "".join(f'<span class="assistente-botao">{ui.esc(r)}</span>' for r, _ in resposta.sugestoes)
    return ('<div class="assistente-telefone">'
            '<div class="assistente-app">● &nbsp; B2 GESTÃO <span>AGORA</span></div>'
            f'<div class="assistente-pergunta">{ui.esc(pergunta)}</div>'
            f'<div class="assistente-resposta"><b>{ui.esc(resposta.titulo)}</b>'
            f'<div>{ui.esc(resposta.mensagem).replace(chr(10), "<br>")}</div></div>'
            f'<div class="assistente-botoes">{botoes}</div></div>')


def pagina(df, tanques, postos: list[str]):
    ui.topo("💬 B2 Assistente", "Pergunte pelo celular e receba vendas, margem e estoque na hora.",
            selo="DEMONSTRAÇÃO")
    if not demonstracao():
        st.info("Esta experiência está disponível para a apresentação com dados simulados.")
        return
    cfg = configuracao()
    try:
        iniciar_configurado()
    except (OSError, ValueError) as erro:
        st.error(f"Não foi possível preparar o assistente: {erro}")

    ui.md('<div class="central-hero assistente-hero">'
          '<div class="h-data">A GESTÃO DA REDE, NA PALMA DA MÃO</div>'
          '<div class="h-frase">“Como está o estoque do Candói?”</div>'
          '<p>O dono pergunta pelo celular. A resposta sai da mesma base do painel, em um segundo.</p></div>')

    esquerda, direita = st.columns([1, 1.15], gap="large")
    with esquerda:
        ui.secao("1 · Experimente aqui", "Digite como perguntaria no celular — ou toque num exemplo.")
        st.session_state.setdefault("assistente_consulta", "resumo b2 centro")

        def usar(texto):
            st.session_state["assistente_consulta"] = texto

        with st.form("pergunta_assistente", border=False, clear_on_submit=True):
            texto = st.text_input("Sua pergunta", placeholder="estoque candói")
            if st.form_submit_button("Perguntar →", type="primary", width="stretch") and texto.strip():
                usar(texto.strip())
        exemplos = [("📊 Resumo Centro", "resumo b2 centro"), ("📦 Estoque Candói", "estoque candói"),
                    ("🚨 Alertas", "alertas"), ("🏪 Resumo da rede", "resumo rede"),
                    ("📋 Placar da reunião", "reuniao"), ("🛡️ Auditoria", "auditoria")]
        for i in range(0, len(exemplos), 2):
            cols = st.columns(2)
            for col, (rotulo, cmd) in zip(cols, exemplos[i:i + 2]):
                col.button(rotulo, on_click=usar, args=(cmd,), width="stretch", key=f"ex_{cmd}")
        st.caption("Entende sem acento e sem “B2”: “estoque candoi”, “como está o índio?”, “margem rede”.")

    with direita:
        ui.secao("A resposta no celular")
        pergunta = st.session_state["assistente_consulta"]
        try:
            d = _dados()
            resposta = assistente.responder(pergunta, d["df"], d["tanques"], d["postos"], simulado=True,
                                            alertas=d["alertas"], extras=d["extras"])
        except ValueError as erro:
            resposta = assistente.Resposta("🤖 B2 Gestão", str(erro))
        ui.md(_telefone(pergunta, resposta))
        botoes = [s for s in resposta.sugestoes]
        if botoes:
            cols = st.columns(len(botoes))
            for col, (rotulo, cmd) in zip(cols, botoes):
                col.button(rotulo, on_click=usar, args=(cmd,), width="stretch", key=f"sug_{cmd}")

    ui.secao("2 · Conecte o celular", "Escolha o canal. O Telegram é o mais simples e tem botões.")
    aba_tg, aba_ntfy = st.tabs(["📱 Telegram (recomendado)", "🔔 ntfy"])
    with aba_tg:
        _estado_telegram()
        servico = ouvintes().telegram
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📣 Disparar os alertas críticos no celular", width="stretch",
                         disabled=servico is None, type="primary"):
                with st.spinner("Enviando…"):
                    n, erro = disparar_alertas()
                if n:
                    st.success(f"Alertas enviados para {n} conversa(s). Olhe o celular!")
                else:
                    st.warning(erro or "Nenhuma conversa ainda: abra o robô no Telegram e toque em Iniciar.")
        with c2:
            if servico is not None and st.button("Enviar esta resposta ao celular", width="stretch"):
                n, erro = servico.enviar_para_todos(resposta)
                (st.success if n else st.warning)(f"Enviada para {n} conversa(s)." if n else
                                                  (erro or "Nenhuma conversa ainda: toque em Iniciar no robô."))
        with st.expander("Como criar o robô (1 minuto, só uma vez)", expanded=servico is None):
            st.markdown(
                "1. No Telegram do celular, procure **@BotFather** e toque em **Iniciar**.\n"
                "2. Envie **/newbot**. Nome: **B2 Gestão**. Usuário: algo terminado em *bot*, "
                "ex.: **B2GestaoDemoBot**.\n"
                "3. Ele devolve um **token** (`123456789:ABC…`). Cole abaixo e clique em **Conectar**.\n"
                "4. Toque em **Abrir no Telegram** (aparece acima) e depois em **Iniciar**. Pronto: "
                "os botões ⛽ Centro, ⛽ Candói, 🚨 Alertas aparecem embaixo da conversa.")
            with st.form("form_telegram"):
                token = st.text_input("Token do robô", type="password",
                                      placeholder="123456789:AA…" if not cfg["telegram_token"] else
                                      "já configurado — cole outro para trocar")
                conectar = st.form_submit_button("Conectar Telegram", type="primary")
            if conectar:
                novo = token.strip() or cfg["telegram_token"]
                if not tg.token_valido(novo):
                    st.error("Isso não parece um token do @BotFather (formato 123456789:ABC…).")
                else:
                    _gravar(telegram_token=novo, telegram_ativo=True)
                    iniciar_configurado()
                    st.rerun()
            if cfg["telegram_ativo"] and st.button("Desconectar Telegram"):
                _gravar(telegram_ativo=False)
                iniciar_configurado()
                st.rerun()
            st.caption("O token fica só neste computador (config_assistente.local.json, fora do Git). "
                       "O robô responde apenas com os dados simulados da demonstração.")

    with aba_ntfy:
        _estado_ntfy()
        if cfg["topico"]:
            st.link_button("Abrir o tópico no ntfy ↗", f"{cfg['servidor'].rstrip('/')}/{cfg['topico']}")
        st.caption("No app ntfy, assine o tópico e publique a pergunta (ex.: resumo b2 centro). "
                   "A resposta volta no mesmo tópico. Sem botões — por isso o Telegram é o recomendado.")
        with st.form("configurar_assistente"):
            topico = st.text_input("Tópico", value=cfg["topico"], max_chars=64)
            servidor = st.text_input("Servidor ntfy", value=cfg["servidor"])
            ativar = st.form_submit_button("Salvar e conectar ntfy")
        if ativar:
            try:
                salvar_configuracao(servidor.strip(), topico.strip(), True)
                iniciar_configurado()
                st.rerun()
            except (OSError, ValueError) as erro:
                st.error(str(erro))
        if cfg["ativo"] and st.button("Desconectar ntfy"):
            salvar_configuracao(cfg["servidor"], cfg["topico"], False)
            iniciar_configurado()
            st.rerun()

    _secao_disparos(postos)


# ------------------------------------------------------- disparos (agenda) --
def _secao_disparos(postos: list[str]):
    ui.secao("3 · Disparos automáticos",
             "O assistente manda sozinho, sem ninguém abrir o Telegram — para todas as pessoas e grupos do robô.")
    c = ouvintes()
    itens = agenda.carregar()

    # Quem recebe
    conversas = c.telegram.conversas() if c.telegram is not None else []
    if conversas:
        chips = " ".join(f'<span class="pill neutro">{"👥" if t == "grupo" else "👤"} {ui.esc(n)}</span>'
                         for _, n, t in conversas)
        ui.md(f'<div style="margin:-.2rem 0 .6rem"><b>Recebem:</b> {chips}</div>')
    else:
        ui.nota("Ninguém recebe ainda: conecte o Telegram e toque em Iniciar no robô — ou adicione o robô "
                "ao grupo da diretoria (ele se registra sozinho e passa a receber ali).")

    # A agenda, um disparo por linha
    for i, item in enumerate(itens):
        col_ativo, col_desc, col_enviar, col_tirar = st.columns([0.6, 5, 1.4, 0.7], vertical_alignment="center")
        ativo = col_ativo.toggle("Ativo", value=bool(item.get("ativo")), key=f"ag_on_{item['id']}",
                                 label_visibility="collapsed")
        if ativo != bool(item.get("ativo")):
            itens[i]["ativo"] = ativo
            agenda.salvar(itens)
            st.rerun()
        col_desc.markdown(f"**{ui.esc(item['nome'])}**  \n<span class='nota'>{ui.esc(agenda.descrever(item))}</span>",
                          unsafe_allow_html=True)
        if col_enviar.button("▶️ Enviar agora", key=f"ag_go_{item['id']}", width="stretch",
                             disabled=c.agendador is None):
            with st.spinner("Enviando…"):
                n, erro = c.agendador.disparar(item)
            (st.success if n else st.info)(f"Enviado para {n} canal(is)." if n else (erro or "Nada enviado."))
        if col_tirar.button("🗑️", key=f"ag_del_{item['id']}", help="Remover este disparo"):
            agenda.salvar([x for x in itens if x["id"] != item["id"]])
            st.rerun()

    with st.expander("➕ Novo disparo"):
        opcoes = dict(agenda.CONTEUDOS)
        opcoes.update({f"resumo {p}": f"⛽ Resumo do {p}" for p in postos})
        with st.form("novo_disparo", border=False):
            nome = st.text_input("Nome", placeholder="ex.: Fechamento do dia")
            conteudo = st.selectbox("O que mandar", list(opcoes), format_func=lambda k: opcoes[k])
            quando = st.radio("Quando", list(agenda.QUANDO), format_func=lambda k: agenda.QUANDO[k],
                              horizontal=True)
            c1, c2 = st.columns([1, 3])
            hora = c1.time_input("Horário", value=None, step=900)
            dias = c2.multiselect("Dias", agenda.DIAS, default=agenda.DIAS,
                                  format_func=lambda d: agenda.NOMES_DIAS[d])
            st.caption("Em “assim que os dados chegarem”, o horário e os dias não contam. Em “cobrar”, "
                       "o assistente só manda se algum posto ainda não enviou a planilha.")
            if st.form_submit_button("Salvar disparo", type="primary"):
                if quando != "chegada" and hora is None:
                    st.error("Escolha o horário.")
                else:
                    novo = {"id": f"d{int(agenda.agora().timestamp())}", "nome": nome.strip() or opcoes[conteudo],
                            "conteudo": conteudo, "quando": quando,
                            "hora": hora.strftime("%H:%M") if hora else "", "dias": dias or agenda.DIAS,
                            "ativo": True}
                    agenda.salvar(itens + [novo])
                    st.rerun()

    if c.agendador is not None and c.agendador.historico:
        linhas = " · ".join(f"{q:%d/%m %H:%M} {ui.esc(n)} ({ui.esc(r)})" for q, n, r in c.agendador.historico[:4])
        ui.nota(f"Últimos disparos: {linhas}")
    ui.nota("O assistente fica no ar enquanto o painel estiver rodando — no notebook (Abrir App.bat) ou na nuvem, "
            "que o despertador mantém acordada. Na nuvem, os dados novos também disparam pelo GitHub.")

