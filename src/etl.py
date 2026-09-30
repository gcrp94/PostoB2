"""ETL: lê as planilhas dos postos, confere e devolve tabelas limpas.

Só LÊ arquivo e padroniza — nenhuma conta de negócio aqui (essas moram em
`analytics.py`). Tudo o que não bate vira AVISO com o nome do arquivo e a
linha, para quem cuida das planilhas saber exatamente o que corrigir.

Regras herdadas do Painel de Finanças, cada uma aprendida com um erro real:

* **o nome do arquivo tem de terminar em MM-AAAA.xlsx** — o "(1)" que o
  navegador acrescenta faz o arquivo sumir, e aqui ele vira aviso em vez de
  sumir calado;
* **dois arquivos do mesmo posto e mês não se somam**: fica o mais recente, e
  o outro é anunciado — somar dobraria o mês inteiro sem ninguém perceber;
* **pastas começadas por "_" são ignoradas** — é onde se guarda backup ao lado
  do dado bom sem contar em dobro.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src import planilhas as P

PADRAO_ARQUIVO = re.compile(r"(\d{2})-(\d{4})\.xlsx$", re.IGNORECASE)


@dataclass
class Resultado:
    movimento: pd.DataFrame
    compras: pd.DataFrame
    despesas: pd.DataFrame
    postos: pd.DataFrame
    tanques: pd.DataFrame
    arquivos: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_produto(valor) -> str | None:
    if not isinstance(valor, str):
        return None
    chave = " ".join(valor.strip().lower().split())
    if chave in P.SINONIMOS_PRODUTO:
        return P.SINONIMOS_PRODUTO[chave]
    return P.SINONIMOS_PRODUTO.get(_sem_acento(chave))


def ler_cadastro(pasta_dados: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    arquivo = pasta_dados / "CADASTRO DOS POSTOS.xlsx"
    postos = pd.read_excel(arquivo, sheet_name="POSTOS")
    postos.columns = [c.strip().lower() for c in postos.columns]
    tanques = pd.read_excel(arquivo, sheet_name="TANQUES")
    tanques = tanques.rename(columns={"Posto": "posto", "Produto": "produto",
                                      "Capacidade (L)": "capacidade"})
    tanques["produto"] = tanques["produto"].map(normalizar_produto)
    return postos, tanques[["posto", "produto", "capacidade"]]


def _ler_aba(xls: pd.ExcelFile, aba: str, nome_arquivo: str, res: Resultado) -> pd.DataFrame | None:
    if aba not in xls.sheet_names:
        if aba in P.ABAS_OBRIGATORIAS:
            res.erros.append(f"{nome_arquivo}: falta a aba '{aba}' — o arquivo foi ignorado.")
        return None
    df = xls.parse(aba)
    df.columns = [str(c).strip() for c in df.columns]
    faltam = [c for c in P.COLUNAS[aba] if c not in df.columns]
    if faltam:
        res.erros.append(f"{nome_arquivo}, aba {aba}: faltam as colunas {', '.join(faltam)}.")
        return None
    df = df[P.COLUNAS[aba]].rename(columns=P.RENOMEAR[aba])
    df = df.dropna(how="all")
    df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)
    ruins = df["data"].isna().sum()
    if ruins:
        res.avisos.append(f"{nome_arquivo}, aba {aba}: {ruins} linha(s) sem data válida — ignoradas.")
        df = df.dropna(subset=["data"])
    return df


def _conferir_mes(df: pd.DataFrame, ano: int, mes: int, nome: str, aba: str, res: Resultado):
    fora = df[(df["data"].dt.year != ano) | (df["data"].dt.month != mes)]
    if len(fora):
        res.avisos.append(f"{nome}, aba {aba}: {len(fora)} linha(s) com data fora de "
                          f"{mes:02d}/{ano} — entraram assim mesmo, confira.")


def ler_arquivo(caminho: Path, posto: str, ano: int, mes: int, res: Resultado) -> dict:
    nome = caminho.name
    xls = pd.ExcelFile(caminho)
    saida = {}

    mov = _ler_aba(xls, P.ABA_MOVIMENTO, nome, res)
    if mov is None:
        return saida
    mov["produto_original"] = mov["produto"]
    mov["produto"] = mov["produto"].map(normalizar_produto)
    desconhecidos = mov.loc[mov["produto"].isna(), "produto_original"].dropna().unique()
    if len(desconhecidos):
        res.avisos.append(f"{nome}: produto não reconhecido ({', '.join(map(str, desconhecidos))}) — "
                          "linhas ignoradas. Use um dos quatro nomes da lista.")
    mov = mov.dropna(subset=["produto"]).drop(columns="produto_original")
    for col in ["estoque_inicial", "compras_l", "vendas_l", "estoque_final", "custo_medio", "preco_medio"]:
        mov[col] = pd.to_numeric(mov[col], errors="coerce")
    mov[["compras_l"]] = mov[["compras_l"]].fillna(0)
    faltando = mov[["estoque_inicial", "vendas_l", "estoque_final", "custo_medio", "preco_medio"]].isna().any(axis=1)
    if faltando.any():
        res.avisos.append(f"{nome}: {int(faltando.sum())} linha(s) do movimento com campo vazio — ignoradas.")
        mov = mov[~faltando]
    dup = mov.duplicated(subset=["data", "produto"], keep="last")
    if dup.any():
        res.avisos.append(f"{nome}: {int(dup.sum())} linha(s) repetidas (mesmo dia e produto) — "
                          "ficou a última.")
        mov = mov[~dup]
    _conferir_mes(mov, ano, mes, nome, P.ABA_MOVIMENTO, res)
    mov.insert(0, "posto", posto)
    saida["movimento"] = mov

    comp = _ler_aba(xls, P.ABA_COMPRAS, nome, res)
    if comp is not None and len(comp):
        comp["produto"] = comp["produto"].map(normalizar_produto)
        comp = comp.dropna(subset=["produto"])
        for col in ["litros", "custo", "valor"]:
            comp[col] = pd.to_numeric(comp[col], errors="coerce")
        comp["nota_fiscal"] = comp["nota_fiscal"].astype(str)
        comp["distribuidora"] = comp["distribuidora"].fillna("Não informada").astype(str)
        comp.insert(0, "posto", posto)
        saida["compras"] = comp

    desp = _ler_aba(xls, P.ABA_DESPESAS, nome, res)
    if desp is not None and len(desp):
        desp["valor"] = pd.to_numeric(desp["valor"], errors="coerce").fillna(0)
        desp["categoria"] = desp["categoria"].fillna("Outras despesas").astype(str).str.strip()
        fora = sorted(set(desp["categoria"]) - set(P.CATEGORIAS_DESPESA))
        if fora:
            res.avisos.append(f"{nome}: categoria de despesa fora da lista ({', '.join(fora)}) — "
                              "entrou em 'Outras despesas'.")
            desp.loc[~desp["categoria"].isin(P.CATEGORIAS_DESPESA), "categoria"] = "Outras despesas"
        desp["descricao"] = desp["descricao"].fillna("").astype(str)
        desp.insert(0, "posto", posto)
        saida["despesas"] = desp
    return saida


def conferir_lmc(mov: pd.DataFrame, res: Resultado):
    """O estoque inicial de um dia tem de ser o final do dia anterior."""
    for (posto, produto), g in mov.sort_values("data").groupby(["posto", "produto"]):
        anterior = g["estoque_final"].shift()
        salto = (g["estoque_inicial"] - anterior).abs() > 1
        salto.iloc[0] = False
        if salto.any():
            dias = ", ".join(g.loc[salto, "data"].dt.strftime("%d/%m/%Y").head(4))
            res.avisos.append(f"{posto} · {produto}: o estoque inicial não bate com o final do dia "
                              f"anterior em {int(salto.sum())} dia(s) ({dias}…). Confira o LMC.")


def ler_tudo(pasta_dados: Path) -> Resultado:
    postos, tanques = ler_cadastro(pasta_dados)
    res = Resultado(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), postos, tanques)
    blocos = {"movimento": [], "compras": [], "despesas": []}
    pasta_para_posto = dict(zip(postos["pasta"], postos["posto"]))

    for pasta in sorted(p for p in pasta_dados.iterdir() if p.is_dir()):
        if pasta.name.startswith("_") or pasta.name.startswith("base"):
            continue
        posto = pasta_para_posto.get(pasta.name)
        if posto is None:
            res.avisos.append(f"Pasta '{pasta.name}' não está no CADASTRO DOS POSTOS — ignorada.")
            continue
        por_mes: dict[tuple[int, int], list[Path]] = {}
        for arq in sorted(pasta.glob("*.xls*")):
            if arq.name.startswith("~$"):
                continue
            m = PADRAO_ARQUIVO.search(arq.name)
            if not m:
                res.avisos.append(f"{posto}: '{arq.name}' não termina em MM-AAAA.xlsx — ignorado. "
                                  "Renomeie (ex.: 'B2 Centro 09-2026.xlsx').")
                continue
            chave = (int(m.group(2)), int(m.group(1)))
            por_mes.setdefault(chave, []).append(arq)
        for (ano, mes), arquivos in sorted(por_mes.items()):
            arquivos.sort(key=lambda a: a.stat().st_mtime)
            escolhido = arquivos[-1]
            for outro in arquivos[:-1]:
                res.avisos.append(f"{posto} {mes:02d}/{ano}: há dois arquivos do mesmo mês; valeu "
                                  f"'{escolhido.name}' (o mais recente) e '{outro.name}' foi ignorado.")
            partes = ler_arquivo(escolhido, posto, ano, mes, res)
            for k, v in partes.items():
                blocos[k].append(v)
            if "movimento" in partes:
                res.arquivos.append({"posto": posto, "ano": ano, "mes": mes, "arquivo": escolhido.name,
                                     "linhas": len(partes["movimento"])})

    res.movimento = (pd.concat(blocos["movimento"], ignore_index=True)
                     if blocos["movimento"] else pd.DataFrame(columns=["posto", *P.RENOMEAR[P.ABA_MOVIMENTO].values()]))
    res.compras = (pd.concat(blocos["compras"], ignore_index=True)
                   if blocos["compras"] else pd.DataFrame(columns=["posto", *P.RENOMEAR[P.ABA_COMPRAS].values()]))
    res.despesas = (pd.concat(blocos["despesas"], ignore_index=True)
                    if blocos["despesas"] else pd.DataFrame(columns=["posto", *P.RENOMEAR[P.ABA_DESPESAS].values()]))
    if len(res.movimento):
        conferir_lmc(res.movimento, res)
        sem_tanque = set(map(tuple, res.movimento[["posto", "produto"]].drop_duplicates().values)) \
            - set(map(tuple, res.tanques[["posto", "produto"]].values))
        for posto, produto in sorted(sem_tanque):
            res.avisos.append(f"{posto} · {produto}: sem capacidade de tanque no cadastro — "
                              "o painel não calcula o % do tanque.")
    return res
