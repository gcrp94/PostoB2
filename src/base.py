"""A base consolidada (Parquet): gravar e carregar.

Quem grava é o `gerar_base.py` (e o envio de planilha pelo painel, que chama
a mesma função). Quem lê é o painel e o motor de alertas.

**A gravação é atômica**: os Parquet novos vão para uma pasta temporária e só
substituem os antigos se TUDO der certo. Planilha com erro nunca derruba o
painel que já estava no ar.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from src import auditoria, etl

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
PASTA_BASE = PASTA_DADOS / "base"
TABELAS = ["movimento", "compras", "despesas", "postos", "tanques"]


def construir(pasta_dados: Path = PASTA_DADOS) -> etl.Resultado:
    return etl.ler_tudo(pasta_dados)


def gravar(res: etl.Resultado, pasta_base: Path = PASTA_BASE, origem: str | None = "Atualizar Dados",
           usuario: str = "") -> dict:
    """Grava a base nova e, antes de trocar, compara com a anterior: o que já
    tinha sido recebido e mudou vai para a trilha de auditoria. `origem=None`
    pula a comparação (base nova do zero, como na demonstração)."""
    if res.movimento.empty:
        raise ValueError("Nenhum movimento encontrado nas planilhas — a base não foi gravada.")
    mudancas = None
    anterior = pasta_base / "movimento.parquet"
    if origem is not None and anterior.exists():
        try:
            mudancas = auditoria.comparar(pd.read_parquet(anterior), res.movimento)
        except Exception:
            mudancas = None          # auditoria nunca impede a base de ser gravada
    temp = pasta_base.with_name(pasta_base.name + "_nova")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    for nome in TABELAS:
        getattr(res, nome).to_parquet(temp / f"{nome}.parquet", index=False)
    info = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "ultima_data": res.movimento["data"].max().strftime("%Y-%m-%d"),
        "arquivos": res.arquivos,
        "avisos": res.avisos,
        "erros": res.erros,
    }
    (temp / "_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    antiga = pasta_base.with_name(pasta_base.name + "_anterior")
    if antiga.exists():
        shutil.rmtree(antiga)
    if pasta_base.exists():
        pasta_base.rename(antiga)
    temp.rename(pasta_base)
    if antiga.exists():
        shutil.rmtree(antiga, ignore_errors=True)
    info["alteracoes"] = auditoria.registrar(mudancas, origem or "", usuario) if mudancas is not None else 0
    return info


@dataclass
class Base:
    movimento: pd.DataFrame
    compras: pd.DataFrame
    despesas: pd.DataFrame
    postos: pd.DataFrame
    tanques: pd.DataFrame
    info: dict


def carregar(pasta_base: Path = PASTA_BASE) -> Base:
    tabelas = {n: pd.read_parquet(pasta_base / f"{n}.parquet") for n in TABELAS}
    info_arq = pasta_base / "_info.json"
    info = json.loads(info_arq.read_text(encoding="utf-8")) if info_arq.exists() else {}
    return Base(**tabelas, info=info)


def assinatura(pasta_base: Path = PASTA_BASE) -> tuple:
    """Muda quando a base é regravada — é a chave do cache do painel."""
    if not pasta_base.exists():
        return ()
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in pasta_base.glob("*")))


def planilhas_mais_novas_que_a_base(pasta_dados: Path = PASTA_DADOS, pasta_base: Path = PASTA_BASE) -> list[str]:
    """Planilhas salvas na pasta DEPOIS da última montagem da base — é o
    lembrete de rodar o 'Atualizar Dados' (o painel lê o Parquet)."""
    info = pasta_base / "_info.json"
    if not info.exists():
        return []
    limite = info.stat().st_mtime
    novas = []
    for p in pasta_dados.glob("*/*.xlsx"):
        if p.parent.name.startswith("_") or p.name.startswith("~$"):
            continue
        if p.stat().st_mtime > limite + 1:
            novas.append(f"{p.parent.name}/{p.name}")
    return novas
