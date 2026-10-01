"""Trilha de auditoria — o que mudou num dado DEPOIS de ele ter sido recebido.

Toda vez que a base é remontada (envio pelo painel, Atualizar Dados.bat ou o
GitHub Actions), a base nova é comparada com a anterior, linha a linha
(posto × dia × combustível). O que já existia e mudou vai para
`data/auditoria.csv`: quando, por qual canal, quem enviou, o dia alterado, o
campo, o valor antes e depois, e o impacto estimado em reais.

Por que isso pega fraude: o gerente que desvia dinheiro do caixa precisa
"sumir" com a venda — e o jeito é baixar o número de litros vendidos DEPOIS
que o dia já foi informado. Corrigir o dia de ontem é rotina; mexer num dia
de duas semanas atrás, ou de um mês já fechado, não é. A gravidade sai daí:

* **normal** — o dia mexido é recente (até `DIAS_CORRECAO_NORMAL` dias antes
  do último dia que o posto já tinha mandado): correção do dia a dia;
* **atenção** — dia mais antigo que isso;
* **crítico** — mês já fechado, ou dia com 7 dias ou mais.

Dia NOVO não é alteração (a planilha do mês cresce todo dia). Dia que SUMIU
é: linha apagada depois de recebida.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.formatting import format_brl, format_decimal, format_int, format_rs_litro

RAIZ = Path(__file__).resolve().parent.parent
ARQ_AUDITORIA = RAIZ / "data" / "auditoria.csv"
FUSO_BRASILIA = timezone(timedelta(hours=-3))      # sem horário de verão desde 2019

DIAS_CORRECAO_NORMAL = 2
DIAS_CRITICO = 7

# campo interno -> (nome na tela, unidade)
CAMPOS = {
    "vendas_l": ("Vendas", "L"),
    "estoque_final": ("Estoque final", "L"),
    "compras_l": ("Compras", "L"),
    "estoque_inicial": ("Estoque inicial", "L"),
    "preco_medio": ("Preço médio", "R$/L"),
    "custo_medio": ("Custo médio", "R$/L"),
}
TOLERANCIA = {"L": 0.5, "R$/L": 0.0005}
COLUNAS = ["registrado_em", "origem", "usuario", "posto", "data", "produto", "campo", "antes", "depois",
           "diferenca", "impacto_rs", "dias_depois", "gravidade"]


def agora() -> datetime:
    return datetime.now(FUSO_BRASILIA).replace(tzinfo=None)


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["data"] = pd.to_datetime(d["data"]).dt.normalize()
    d["produto"] = d["produto"].astype(str)
    return d


def comparar(antiga: pd.DataFrame, nova: pd.DataFrame, ultima: pd.Series | None = None) -> pd.DataFrame:
    """As mudanças em linhas que JÁ existiam na base antiga.

    `ultima` (posto -> último dia já recebido) serve para comparar um recorte
    (um mês só) sem perder a régua: corrigir agosto com setembro já recebido
    é mexer em mês fechado, mesmo que o recorte só tenha agosto."""
    if antiga is None or antiga.empty or nova is None or nova.empty:
        return pd.DataFrame(columns=COLUNAS)
    a, n = _preparar(antiga), _preparar(nova)
    chaves = ["posto", "data", "produto"]
    campos = [c for c in CAMPOS if c in a.columns and c in n.columns]
    m = a[chaves + campos].merge(n[chaves + campos], on=chaves, how="left", suffixes=("_a", "_n"),
                                 indicator=True)
    ultima_antiga = ultima if ultima is not None else a.groupby("posto")["data"].max()
    linhas = []
    for _, r in m.iterrows():
        dias_depois = int((ultima_antiga[r["posto"]] - r["data"]).days)
        mes_fechado = (r["data"].year, r["data"].month) < (ultima_antiga[r["posto"]].year,
                                                          ultima_antiga[r["posto"]].month)
        if r["_merge"] == "left_only":
            linhas.append(_linha(r, "Linha inteira", r.get("vendas_l_a"), np.nan,
                                 -(r.get("vendas_l_a") or 0) * (r.get("preco_medio_a") or 0),
                                 dias_depois, mes_fechado))
            continue
        for campo in campos:
            antes, depois = r[f"{campo}_a"], r[f"{campo}_n"]
            if pd.isna(antes) or pd.isna(depois):
                continue
            unidade = CAMPOS[campo][1]
            if abs(depois - antes) <= TOLERANCIA[unidade]:
                continue
            linhas.append(_linha(r, CAMPOS[campo][0], antes, depois,
                                 _impacto(campo, antes, depois, r), dias_depois, mes_fechado))
    return pd.DataFrame(linhas, columns=[c for c in COLUNAS if c not in ("registrado_em", "origem", "usuario")])


def _impacto(campo: str, antes: float, depois: float, r) -> float:
    """Quanto a mudança mexe em reais: no faturamento, na margem ou no estoque."""
    dif = depois - antes
    if campo == "vendas_l":
        return dif * r["preco_medio_n"]
    if campo == "preco_medio":
        return dif * r["vendas_l_n"]
    if campo == "custo_medio":
        return -dif * r["vendas_l_n"]            # custo maior = margem menor
    return dif * r["custo_medio_n"]              # litros de estoque, a preço de custo


def _linha(r, campo, antes, depois, impacto, dias_depois, mes_fechado) -> dict:
    if mes_fechado or dias_depois >= DIAS_CRITICO:
        gravidade = "critico"
    elif dias_depois >= DIAS_CORRECAO_NORMAL:
        gravidade = "atencao"
    else:
        gravidade = "normal"
    dif = (depois - antes) if (antes == antes and depois == depois) else np.nan
    return {"posto": r["posto"], "data": r["data"], "produto": r["produto"], "campo": campo,
            "antes": antes, "depois": depois, "diferenca": dif, "impacto_rs": round(float(impacto), 2),
            "dias_depois": dias_depois, "gravidade": gravidade}


def registrar(mudancas: pd.DataFrame, origem: str, usuario: str = "", quando: datetime | None = None) -> int:
    """Acrescenta as mudanças ao arquivo de auditoria. Devolve quantas.
    `quando` só é passado pelo gerador da demonstração."""
    if mudancas is None or mudancas.empty:
        return 0
    ARQ_AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
    novo = not ARQ_AUDITORIA.exists()
    quando = (quando or agora()).strftime("%Y-%m-%d %H:%M")
    with open(ARQ_AUDITORIA, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(COLUNAS)
        for _, m in mudancas.iterrows():
            w.writerow([quando, origem, usuario, m["posto"], pd.Timestamp(m["data"]).strftime("%Y-%m-%d"),
                        m["produto"], m["campo"], _num(m["antes"]), _num(m["depois"]), _num(m["diferenca"]),
                        _num(m["impacto_rs"]), int(m["dias_depois"]), m["gravidade"]])
    return len(mudancas)


def _num(v) -> str:
    return "" if v is None or v != v else f"{float(v):.4f}"


def ler() -> pd.DataFrame:
    if not ARQ_AUDITORIA.exists():
        return pd.DataFrame(columns=COLUNAS)
    df = pd.read_csv(ARQ_AUDITORIA, sep=";", dtype={"usuario": str, "origem": str})
    df["registrado_em"] = pd.to_datetime(df["registrado_em"], errors="coerce")
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    for c in ("antes", "depois", "diferenca", "impacto_rs"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["usuario"] = df["usuario"].fillna("")
    return df.sort_values("registrado_em", ascending=False).reset_index(drop=True)


def assinatura() -> tuple:
    return (ARQ_AUDITORIA.stat().st_mtime_ns,) if ARQ_AUDITORIA.exists() else ()


def suspeitas(aud: pd.DataFrame, dias: int = 30, referencia: datetime | None = None) -> pd.DataFrame:
    """Só o que merece olhar: atenção e crítico, registrado nos últimos `dias`."""
    if aud is None or aud.empty:
        return aud if aud is not None else pd.DataFrame(columns=COLUNAS)
    ref = referencia or aud["registrado_em"].max()
    recentes = aud[aud["registrado_em"] >= ref - timedelta(days=dias)]
    return recentes[recentes["gravidade"].isin(["atencao", "critico"])]


def descrever(m) -> str:
    """Uma linha legível: "Gasolina Comum de 03/09: vendas 5.520 L → 4.820 L (−700 L)"."""
    unidade = next((u for n, u in CAMPOS.values() if n == m["campo"]), "L")
    if m["campo"] == "Linha inteira":
        return f"{m['produto']} de {pd.Timestamp(m['data']):%d/%m}: linha APAGADA depois de recebida"
    if unidade == "L":
        antes, depois = f"{format_int(m['antes'])} L", f"{format_int(m['depois'])} L"
        dif = f"{'+' if m['diferenca'] > 0 else '−'}{format_int(abs(m['diferenca']))} L"
    else:
        antes, depois = format_rs_litro(m["antes"], 3), format_rs_litro(m["depois"], 3)
        dif = f"{'+' if m['diferenca'] > 0 else '−'}{format_decimal(abs(m['diferenca']) * 100, 1)} centavos"
    return (f"{m['produto']} de {pd.Timestamp(m['data']):%d/%m}: {m['campo'].lower()} {antes} → {depois} "
            f"({dif}; {format_brl(m['impacto_rs'], 0)})")
