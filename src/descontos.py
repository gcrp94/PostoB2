"""Desconto do boleto: a diferença entre o custo da PLANILHA e o custo do SISTEMA.

A distribuidora dá um desconto no boleto pago direto a ela. Por isso:

* **Preço planilha** = o que o posto realmente paga (já com o desconto): é o `custo_medio` das planilhas;
* **Preço sistema** = o preço cheio da nota fiscal, como o Linx registra: planilha + desconto.

O botão do painel troca de um para o outro; margem, ponto de equilíbrio, alertas e comparações se recalculam. Os dois
números existem sempre (`custo_planilha` e `custo_sistema`); só um vira o `custo_medio` da conta.

O desconto mora numa TABELA de configuração (`data/descontos_boleto.csv`: distribuidora, produto ou "Todos", R$ por litro),
e não na planilha do posto: é um termo comercial que muda raramente, e assim as planilhas já enviadas continuam valendo.
Para cada dia, o desconto usado é a MÉDIA PONDERADA PELOS LITROS das compras dos últimos 30 dias (sem compra na janela,
vale o último conhecido). Quando o Linx entregar o custo cheio de cada nota, a tabela vira conferência.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ARQ = Path(__file__).resolve().parent.parent / "data" / "descontos_boleto.csv"
COLUNAS = ["distribuidora", "produto", "desconto"]
TODOS = "Todos"
JANELA_DIAS = 30
MAX_DESCONTO = 1.0           # R$/L: acima disso é erro de digitação


def carregar(arquivo: Path = ARQ) -> pd.DataFrame:
    """A tabela (vazia se ainda não existe: então os dois preços são iguais)."""
    vazio = pd.DataFrame(columns=COLUNAS).astype({"desconto": float})
    if not arquivo.exists():
        return vazio
    try:
        t = pd.read_csv(arquivo, sep=";", encoding="utf-8", dtype={"distribuidora": str, "produto": str})
    except (ValueError, OSError):
        return vazio
    t, _ = validar(t)
    return t


def assinatura(arquivo: Path = ARQ) -> int:
    """Muda quando a tabela muda (entra na chave do cache do painel)."""
    return arquivo.stat().st_mtime_ns if arquivo.exists() else 0


def validar(t: pd.DataFrame, produtos: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Limpa a tabela e diz o que descartou. Linha sem distribuidora ou com desconto inválido sai."""
    avisos: list[str] = []
    t = t.copy()
    for c in COLUNAS:
        if c not in t.columns:
            t[c] = np.nan
    t["distribuidora"] = t["distribuidora"].fillna("").astype(str).str.strip()
    t["produto"] = t["produto"].fillna(TODOS).astype(str).str.strip().replace("", TODOS)
    t["desconto"] = pd.to_numeric(t["desconto"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    ruim_dist = t["distribuidora"] == ""
    ruim_valor = t["desconto"].isna() | (t["desconto"] < 0) | (t["desconto"] > MAX_DESCONTO)
    if produtos is not None:
        ruim_prod = ~t["produto"].isin([TODOS, *produtos])
        if ruim_prod.any():
            avisos.append(f"{int(ruim_prod.sum())} linha(s) com produto fora da lista foram descartadas.")
    else:
        ruim_prod = pd.Series(False, index=t.index)
    if ruim_valor.any():
        avisos.append(f"{int((ruim_valor & ~ruim_dist).sum())} linha(s) com desconto vazio, negativo ou acima de "
                      f"R$ {MAX_DESCONTO:.2f}/L foram descartadas.")
    t = t[~(ruim_dist | ruim_valor | ruim_prod)]
    t = t.drop_duplicates(["distribuidora", "produto"], keep="last")
    return t[COLUNAS].reset_index(drop=True), avisos


def gravar(t: pd.DataFrame, arquivo: Path = ARQ) -> list[str]:
    """Valida e grava de uma vez (arquivo temporário e troca). Devolve os avisos."""
    limpa, avisos = validar(t)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = arquivo.with_suffix(".tmp")
    limpa.to_csv(tmp, sep=";", index=False, encoding="utf-8")
    tmp.replace(arquivo)
    return avisos


def por_compra(compras: pd.DataFrame, tabela: pd.DataFrame) -> pd.Series:
    """O desconto (R$/L) de cada compra: (distribuidora, produto) vale mais que (distribuidora, "Todos"); sem linha, zero."""
    if compras is None or compras.empty or tabela is None or tabela.empty:
        return pd.Series(0.0, index=compras.index if compras is not None else None)
    t = tabela.drop_duplicates(["distribuidora", "produto"], keep="last")
    especifico = t[t["produto"] != TODOS].set_index(["distribuidora", "produto"])["desconto"]
    geral = t[t["produto"] == TODOS].set_index("distribuidora")["desconto"]
    dist = compras["distribuidora"].astype(str)
    esp = especifico.reindex(pd.MultiIndex.from_arrays([dist, compras["produto"].astype(str)])).to_numpy(dtype=float)
    ger = dist.map(geral).to_numpy(dtype=float)
    return pd.Series(np.where(~np.isnan(esp), esp, np.where(~np.isnan(ger), ger, 0.0)), index=compras.index)


def desconto_diario(mov: pd.DataFrame, compras: pd.DataFrame | None, tabela: pd.DataFrame | None,
                    janela: int = JANELA_DIAS) -> pd.Series:
    """Para cada linha do movimento (posto, produto, dia): o desconto médio por litro das compras dos últimos `janela` dias.

    Média ponderada pelos litros. Sem compra na janela vale o último conhecido; antes da 1ª compra, o 1º conhecido.
    """
    saida = pd.Series(0.0, index=mov.index)
    if compras is None or compras.empty or tabela is None or tabela.empty:
        return saida
    c = compras[["posto", "data", "produto", "litros", "distribuidora"]].copy()
    c["data"] = pd.to_datetime(c["data"]).dt.normalize()
    c["produto"] = c["produto"].astype(str)
    c["litros"] = pd.to_numeric(c["litros"], errors="coerce").fillna(0.0)
    c["lit_desc"] = c["litros"] * por_compra(c, tabela)
    c = c[c["litros"] > 0]
    produto_mov = mov["produto"].astype(str)
    for (posto, produto), g in mov.groupby([mov["posto"], produto_mov]):
        cc = c[(c["posto"] == posto) & (c["produto"] == produto)]
        if cc.empty:
            continue
        datas = pd.date_range(min(g["data"].min(), cc["data"].min()), g["data"].max(), freq="D")
        diario = cc.groupby("data")[["litros", "lit_desc"]].sum().reindex(datas, fill_value=0.0)
        janela_soma = diario.rolling(janela, min_periods=1).sum()
        taxa = (janela_soma["lit_desc"] / janela_soma["litros"]).where(janela_soma["litros"] > 0)
        taxa = taxa.ffill().bfill().fillna(0.0)
        saida.loc[g.index] = taxa.reindex(g["data"]).to_numpy()
    return saida
