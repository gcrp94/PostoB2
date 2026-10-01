"""Onde a planilha enviada pelo painel vai morar — e o histórico dos envios.

Dois modos, escolhidos sozinhos:

* **local** (padrão, e o da demonstração): a planilha é gravada na pasta do
  posto, a versão anterior vai para `_versoes/` e a base é remontada na hora;
* **GitHub** (quando o `secrets.toml` tem `[github]`): a planilha vai para o
  repositório privado pela API; o GitHub Actions remonta a base, roda os
  testes, dispara os alertas e publica. Para quem envia, o GitHub nem existe.

    [github]
    token = "github_pat_..."      # fine-grained, só "Contents: read and write"
    repo = "usuario/b2-gestao"
    branch = "main"

O `st.file_uploader` guarda o arquivo só na memória, e o disco da Streamlit
Community Cloud não é permanente — por isso, publicado, o modo GitHub é o
único que não perde planilha.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src import base

PASTA_DADOS = base.PASTA_DADOS
ARQ_ENVIOS = PASTA_DADOS / "envios.csv"
COLUNAS_ENVIOS = ["data_hora", "posto", "pasta", "usuario", "periodo", "arquivo", "resultado", "detalhe"]


# -------------------------------------------------------------- histórico ---
def ler_envios() -> pd.DataFrame:
    if not ARQ_ENVIOS.exists():
        return pd.DataFrame(columns=COLUNAS_ENVIOS)
    df = pd.read_csv(ARQ_ENVIOS, sep=";", dtype=str).fillna("")
    df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce")
    return df.sort_values("data_hora", ascending=False).reset_index(drop=True)


def _gravar_envios(df: pd.DataFrame) -> str:
    saida = df.sort_values("data_hora").copy()
    saida["data_hora"] = saida["data_hora"].dt.strftime("%Y-%m-%d %H:%M")
    texto = saida[COLUNAS_ENVIOS].to_csv(sep=";", index=False, quoting=csv.QUOTE_MINIMAL)
    ARQ_ENVIOS.write_text(texto, encoding="utf-8")
    return texto


def registrar_envio(posto: str, pasta: str, usuario: str, periodo: str, arquivo: str,
                    resultado: str, detalhe: str) -> str:
    df = ler_envios()
    if resultado == "Processado":
        # A versão anterior do mesmo posto e mês passa a ser "Substituído".
        mesmo = (df["posto"] == posto) & (df["periodo"] == periodo) & (df["resultado"] == "Processado")
        df.loc[mesmo, "resultado"] = "Substituído"
    nova = pd.DataFrame([{
        "data_hora": pd.Timestamp(datetime.now().replace(second=0, microsecond=0)), "posto": posto,
        "pasta": pasta, "usuario": usuario, "periodo": periodo, "arquivo": arquivo,
        "resultado": resultado, "detalhe": detalhe}])
    return _gravar_envios(pd.concat([df, nova], ignore_index=True))


def status_postos(envios: pd.DataFrame, postos: list[str]) -> dict[str, dict]:
    saida = {}
    for p in postos:
        e = envios[(envios["posto"] == p) & (envios["resultado"] == "Processado")]
        saida[p] = e.iloc[0].to_dict() if len(e) else {}
    return saida


# ------------------------------------------------------------------ modos ---
def config_github() -> dict | None:
    try:
        g = st.secrets["github"]
        if g.get("token") and g.get("repo"):
            return {"token": g["token"], "repo": g["repo"], "branch": g.get("branch", "main")}
    except Exception:
        pass
    return None


def modo() -> str:
    return "github" if config_github() else "local"


def hash_conteudo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def arquivo_atual(pasta: str, nome: str) -> Path | None:
    p = PASTA_DADOS / pasta / nome
    return p if p.exists() else None


# ------------------------------------------------------------------ local ---
def listar_versoes(pasta: str, nome: str) -> list[Path]:
    dir_v = PASTA_DADOS / pasta / "_versoes"
    if not dir_v.exists():
        return []
    stem = Path(nome).stem
    return sorted(dir_v.glob(f"{stem} __ *.xlsx"), reverse=True)


def _salvar_local(pasta: str, nome: str, conteudo: bytes) -> Path | None:
    destino = PASTA_DADOS / pasta / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destino.exists():
        dir_v = destino.parent / "_versoes"          # o "_" faz o ETL ignorar
        dir_v.mkdir(exist_ok=True)
        backup = dir_v / f"{destino.stem} __ {datetime.now():%Y-%m-%d %H%M%S}.xlsx"
        shutil.copy2(destino, backup)
    destino.write_bytes(conteudo)
    return backup


def remontar_base(usuario: str = "", origem: str = "Envio pelo painel") -> tuple[bool, str]:
    res = base.construir()
    if res.erros:
        return False, "; ".join(res.erros)
    try:
        base.gravar(res, origem=origem, usuario=usuario)
    except ValueError as erro:
        return False, str(erro)
    return True, ""


# ----------------------------------------------------------------- GitHub ---
def _github(cfg: dict, metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{urllib.request.quote(caminho)}"
    if metodo == "GET":
        url += f"?ref={cfg['branch']}"
    req = urllib.request.Request(url, method=metodo, data=json.dumps(corpo).encode() if corpo else None,
                                 headers={"Authorization": f"Bearer {cfg['token']}",
                                          "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as erro:
        if erro.code == 404 and metodo == "GET":
            return {}
        raise


def _github_put(cfg: dict, caminho: str, conteudo: bytes, mensagem: str):
    atual = _github(cfg, "GET", caminho)
    corpo = {"message": mensagem, "content": base64.b64encode(conteudo).decode(), "branch": cfg["branch"]}
    if atual.get("sha"):
        corpo["sha"] = atual["sha"]
    _github(cfg, "PUT", caminho, corpo)


# ---------------------------------------------------------------- salvar ---
def salvar_planilha(usuario: str, posto: str, pasta: str, nome: str, conteudo: bytes,
                    periodo: str, detalhe: str) -> dict:
    """Grava a planilha JÁ VALIDADA. Se a base não remontar, desfaz tudo."""
    cfg = config_github()
    if cfg:
        try:
            _github_put(cfg, f"data/{pasta}/{nome}", conteudo,
                        f"Planilha {posto} {periodo} enviada por {usuario}")
            texto = registrar_envio(posto, pasta, usuario, periodo, nome, "Processado", detalhe)
            _github_put(cfg, "data/envios.csv", texto.encode("utf-8"),
                        f"Histórico de envios: {posto} {periodo}")
        except Exception as erro:            # rede fora, token vencido...
            return {"ok": False, "modo": "github",
                    "mensagem": f"Não foi possível gravar no GitHub ({erro}). O painel anterior continua intacto."}
        return {"ok": True, "modo": "github",
                "mensagem": "Planilha recebida. O painel publicado se atualiza em 2 a 3 minutos."}

    backup = _salvar_local(pasta, nome, conteudo)
    ok, erro = remontar_base(usuario)
    if not ok:
        destino = PASTA_DADOS / pasta / nome
        if backup:
            shutil.copy2(backup, destino)
        else:
            destino.unlink(missing_ok=True)
        remontar_base(origem=None)
        return {"ok": False, "modo": "local",
                "mensagem": f"A base não remontou ({erro}). A planilha anterior foi restaurada."}
    registrar_envio(posto, pasta, usuario, periodo, nome, "Processado", detalhe)
    return {"ok": True, "modo": "local", "mensagem": "Painel atualizado."}


def restaurar_versao(usuario: str, posto: str, pasta: str, nome: str, versao: Path, periodo: str) -> dict:
    conteudo = versao.read_bytes()
    r = salvar_planilha(usuario, posto, pasta, nome, conteudo, periodo,
                        f"restaurada a versão de {versao.stem.split(' __ ')[-1]}")
    return r
