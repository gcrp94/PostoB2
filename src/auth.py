"""Login e perfis — quem entra, e o que cada um enxerga.

Três perfis:

* **Proprietário** e **Administrador** — a rede inteira, a Central, os
  alertas, as atualizações e a administração;
* **Gerente** — só o PRÓPRIO posto: "Meu Posto", "Enviar Planilha" e "Meus
  Envios". O posto vem do login, e o gerente não escolhe: assim ninguém
  alimenta o posto errado.

Os usuários de verdade ficam no `.streamlit/secrets.toml` (nunca no código,
nunca no Git), com a senha em hash PBKDF2 — o mesmo formato do Painel de
Finanças:

    [usuarios.ana_candoi]
    login = "ana.candoi"
    nome = "Ana"
    perfil = "gerente"
    posto = "B2 Candói"
    senha = "pbkdf2_sha256$260000$<salt>$<hash>"

Sem `[usuarios]` no secrets, o painel entra em **modo demonstração**: os
usuários fictícios abaixo, todos com a senha `b2demo`, e botões de acesso
rápido na tela de login para a apresentação.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets as _secrets
from dataclasses import dataclass

import streamlit as st

from src import ui

PERFIS = {"proprietario": "Proprietário", "administrador": "Administrador", "gerente": "Gerente"}
SENHA_DEMO = "b2demo"
ITERACOES = 260_000


@dataclass(frozen=True)
class Usuario:
    login: str
    nome: str
    perfil: str
    posto: str | None = None

    @property
    def ve_rede(self) -> bool:
        return self.perfil in ("proprietario", "administrador")

    @property
    def perfil_nome(self) -> str:
        return PERFIS.get(self.perfil, self.perfil)


USUARIOS_DEMO = [
    Usuario("proprietario", "Proprietário", "proprietario"),
    Usuario("administracao", "Administração", "administrador"),
    Usuario("joao.centro", "João", "gerente", "B2 Centro"),
    Usuario("carlos.bonsucesso", "Carlos", "gerente", "B2 Bonsucesso"),
    Usuario("marcos.primavera", "Marcos", "gerente", "B2 Primavera"),
    Usuario("paulo.indio", "Paulo", "gerente", "B2 Índio"),
    Usuario("ana.candoi", "Ana", "gerente", "B2 Candói"),
]


def gerar_hash(senha: str) -> str:
    sal = _secrets.token_hex(16)
    dig = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), ITERACOES).hex()
    return f"pbkdf2_sha256${ITERACOES}${sal}${dig}"


def verificar_senha(senha: str, guardado: str) -> bool:
    try:
        _alg, it, sal, dig = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(it)).hex()
        return hmac.compare_digest(calc, dig)
    except (ValueError, TypeError):
        return False


def _usuarios_do_secrets() -> dict[str, tuple[Usuario, str]] | None:
    try:
        bloco = st.secrets["usuarios"]
    except Exception:          # sem secrets.toml, ou sem a seção
        return None
    saida = {}
    for _chave, u in bloco.items():
        usuario = Usuario(u["login"], u.get("nome", u["login"]), u.get("perfil", "gerente"), u.get("posto"))
        saida[usuario.login] = (usuario, u["senha"])
    return saida or None


def modo_demo() -> bool:
    return _usuarios_do_secrets() is None


def usuarios() -> dict[str, tuple[Usuario, str | None]]:
    reais = _usuarios_do_secrets()
    if reais is not None:
        return reais
    return {u.login: (u, None) for u in USUARIOS_DEMO}


def autenticar(login: str, senha: str) -> Usuario | None:
    registro = usuarios().get(login.strip().lower())
    if not registro:
        return None
    usuario, guardado = registro
    if guardado is None:                       # modo demonstração
        return usuario if hmac.compare_digest(senha, SENHA_DEMO) else None
    return usuario if verificar_senha(senha, guardado) else None


def usuario_atual() -> Usuario | None:
    login = st.session_state.get("_usuario")
    if not login:
        return None
    registro = usuarios().get(login)
    return registro[0] if registro else None


def entrar(usuario: Usuario):
    st.session_state.clear()
    st.session_state["_usuario"] = usuario.login
    st.rerun()


def sair():
    st.session_state.clear()
    st.rerun()


def tela_login():
    _, meio, _ = st.columns([1, 1.25, 1])
    with meio:
        ui.md('<div class="login-card">'
              f'<img src="data:image/png;base64,{ui.logo_base64()}" alt="B2 Postos">'
              '<h1>B2 Gestão</h1><p>Painel de gestão da Rede B2 Postos</p></div>')
        with st.form("form_login", border=False):
            login = st.text_input("Usuário", placeholder="ex.: ana.candoi")
            senha = st.text_input("Senha", type="password")
            ok = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if ok:
            usuario = autenticar(login, senha)
            if usuario:
                entrar(usuario)
            st.error("Usuário ou senha não conferem.")
        if modo_demo():
            ui.md('<div style="text-align:center;margin:1.2rem 0 .5rem">'
                  '<span class="selo">MODO DEMONSTRAÇÃO · dados simulados</span></div>')
            ui.nota("Acesso rápido para a apresentação (a senha de todos é <b>b2demo</b>):")
            c1, c2 = st.columns(2)
            if c1.button("👔 Proprietário", use_container_width=True):
                entrar(USUARIOS_DEMO[0])
            if c2.button("🧑‍🔧 Gerente · B2 Candói", use_container_width=True):
                entrar(USUARIOS_DEMO[6])
            c3, c4 = st.columns(2)
            if c3.button("🧑‍🔧 Gerente · B2 Primavera", use_container_width=True):
                entrar(USUARIOS_DEMO[4])
            if c4.button("🛠️ Administração", use_container_width=True):
                entrar(USUARIOS_DEMO[1])
