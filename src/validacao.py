"""Conferência da planilha ANTES de ela entrar no painel.

Regra de ouro: **erro no Excel nunca derruba o painel que está no ar.** A
planilha só é gravada se passar aqui sem ERRO; AVISO não impede, mas aparece
para quem enviou. Cada item diz o que achou e onde, na língua de quem
preenche a planilha — não na do programador.

Usa as mesmas funções de leitura do ETL (`etl.ler_arquivo`): o que passa aqui
é exatamente o que o ETL vai ler depois.
"""
from __future__ import annotations

import hashlib
import io
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from src import etl
from src import planilhas as P
from src.formatting import format_brl, format_int, format_litros, nome_mes

PRECO_MIN, PRECO_MAX = 2.0, 12.0


@dataclass
class Relatorio:
    itens: list[tuple[str, str]] = field(default_factory=list)   # (ok|aviso|erro, texto)
    ano: int | None = None
    mes: int | None = None
    resumo: dict = field(default_factory=dict)
    comparacao: dict = field(default_factory=dict)
    nome_padrao: str = ""
    duplicado: bool = False

    @property
    def erros(self) -> list[str]:
        return [t for s, t in self.itens if s == "erro"]

    @property
    def avisos(self) -> list[str]:
        return [t for s, t in self.itens if s == "aviso"]

    @property
    def aprovado(self) -> bool:
        return not self.erros and not self.duplicado

    @property
    def periodo(self) -> str:
        return f"{self.mes:02d}/{self.ano}" if self.ano else ""

    def ok(self, t): self.itens.append(("ok", t))
    def aviso(self, t): self.itens.append(("aviso", t))
    def erro(self, t): self.itens.append(("erro", t))


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def validar(conteudo: bytes, nome_arquivo: str, posto: str, postos: list[str], tanques: pd.DataFrame,
            movimento_base: pd.DataFrame, hash_atual: str | None = None) -> Relatorio:
    rel = Relatorio()

    # 1. É uma planilha Excel?
    if not nome_arquivo.lower().endswith((".xlsx", ".xlsm")):
        rel.erro("O arquivo não é uma planilha Excel (.xlsx).")
        return rel
    try:
        xls = pd.ExcelFile(io.BytesIO(conteudo))
    except Exception:
        rel.erro("Não foi possível abrir o arquivo — ele está corrompido ou não é Excel.")
        return rel
    rel.ok("Planilha Excel aberta")

    # 2. É deste posto? (o nome do arquivo não pode citar OUTRO posto)
    nome_n = _norm(nome_arquivo)
    outros = [p for p in postos if p != posto and _norm(p.replace("B2 ", "")) in nome_n]
    if outros:
        rel.erro(f"O nome do arquivo cita o {outros[0]}, mas o envio é do {posto}. "
                 "Confira se escolheu a planilha certa.")
    else:
        rel.ok(f"Posto: {posto}")

    # 3. Abas e colunas. Coluna faltando é erro, mas a conferência CONTINUA
    #    com as que existem: quem corrige a planilha precisa ver todos os
    #    problemas de uma vez, e não um por envio.
    if P.ABA_MOVIMENTO not in xls.sheet_names:
        rel.erro(f"Falta a aba '{P.ABA_MOVIMENTO}' (as abas têm de ter o nome do modelo).")
        return rel
    bruto = xls.parse(P.ABA_MOVIMENTO)
    bruto.columns = [str(c).strip() for c in bruto.columns]
    faltam = [c for c in P.COLUNAS[P.ABA_MOVIMENTO] if c not in bruto.columns]
    for c in faltam:
        rel.erro(f'Coluna "{c}" não encontrada na aba {P.ABA_MOVIMENTO}.')
    if "Data" in faltam or "Produto" in faltam:
        return rel
    if not faltam:
        rel.ok("Colunas obrigatórias presentes")
    presentes_col = [c for c in P.COLUNAS[P.ABA_MOVIMENTO] if c in bruto.columns]
    df = bruto[presentes_col].rename(columns=P.RENOMEAR[P.ABA_MOVIMENTO]).dropna(how="all")
    df["data"] = pd.to_datetime(df["data"], errors="coerce", dayfirst=True)
    sem_data = int(df["data"].isna().sum())
    if sem_data:
        rel.aviso(f"{sem_data} linha(s) sem data válida — seriam ignoradas.")
        df = df.dropna(subset=["data"])

    # 4. Período: um mês só, e o mesmo do nome do arquivo.
    meses = sorted({(d.year, d.month) for d in df["data"]})
    if not meses:
        rel.erro("A aba MOVIMENTO DIÁRIO não tem nenhuma linha com data.")
        return rel
    if len(meses) > 1:
        lista = ", ".join(f"{m:02d}/{a}" for a, m in meses)
        rel.erro(f"A planilha mistura meses ({lista}). Envie uma planilha por mês.")
        return rel
    rel.ano, rel.mes = meses[0]
    m = etl.PADRAO_ARQUIVO.search(nome_arquivo)
    if m and (int(m.group(2)), int(m.group(1))) != (rel.ano, rel.mes):
        rel.erro(f"O nome do arquivo diz {m.group(1)}/{m.group(2)}, mas as datas são de "
                 f"{rel.mes:02d}/{rel.ano}.")
    else:
        rel.ok(f"Referência: {nome_mes(rel.mes, rel.ano)}")
    rel.nome_padrao = f"{posto} {rel.mes:02d}-{rel.ano}.xlsx"

    # 5. Produtos.
    df["produto_ok"] = df["produto"].map(etl.normalizar_produto)
    desconhecidos = df.loc[df["produto_ok"].isna(), "produto"].dropna().astype(str).unique()
    if len(desconhecidos):
        rel.erro(f"Produto não reconhecido: {', '.join(desconhecidos)}. Use: {', '.join(P.PRODUTOS)}.")
    presentes = set(df["produto_ok"].dropna())
    for p in P.PRODUTOS:
        if p in presentes:
            rel.ok(p)
        else:
            rel.aviso(f"{p} não aparece na planilha — o posto não vendeu no mês?")
    df = df.dropna(subset=["produto_ok"]).assign(produto=lambda d: d["produto_ok"]).drop(columns="produto_ok")

    # 6. Números.
    numericas = [c for c in ["estoque_inicial", "compras_l", "vendas_l", "estoque_final", "custo_medio",
                             "preco_medio"] if c in df.columns]
    for c in numericas:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "compras_l" in df.columns:
        df["compras_l"] = df["compras_l"].fillna(0)
    obrigatorias = [c for c in ["estoque_inicial", "vendas_l", "estoque_final", "custo_medio", "preco_medio"]
                    if c in df.columns]
    vazios = df[obrigatorias].isna().any(axis=1)
    if vazios.any():
        dias = ", ".join(df.loc[vazios, "data"].dt.strftime("%d/%m").unique()[:4])
        rel.erro(f"{int(vazios.sum())} linha(s) com campo vazio ou texto no lugar de número ({dias}…).")
        df = df[~vazios]
    dup = df.duplicated(subset=["data", "produto"])
    if dup.any():
        rel.erro(f"{int(dup.sum())} linha(s) repetidas — o mesmo dia e produto aparece duas vezes.")

    tem = set(df.columns)
    vazio = df.iloc[0:0]
    for _, r in (df[df["estoque_final"] < 0].head(3) if "estoque_final" in tem else vazio).iterrows():
        rel.erro(f"{r['produto']} possui estoque negativo em {r['data']:%d/%m/%Y}.")
    for _, r in (df[df["vendas_l"] < 0].head(3) if "vendas_l" in tem else df.iloc[0:0]).iterrows():
        rel.erro(f"{r['produto']} com venda negativa em {r['data']:%d/%m/%Y}.")
    fora = (df[(df["preco_medio"] < PRECO_MIN) | (df["preco_medio"] > PRECO_MAX)]
            if "preco_medio" in tem else vazio)
    if len(fora):
        r = fora.iloc[0]
        rel.erro(f"Preço fora do normal: {r['produto']} a {format_brl(r['preco_medio'])} em "
                 f"{r['data']:%d/%m/%Y} (esperado entre {format_brl(PRECO_MIN)} e {format_brl(PRECO_MAX)}).")
    negativa = (df[df["preco_medio"] < df["custo_medio"]] if {"preco_medio", "custo_medio"} <= tem
                else vazio)
    if len(negativa):
        rel.aviso(f"Margem negativa (preço abaixo do custo) em {len(negativa)} linha(s) — "
                  f"ex.: {negativa.iloc[0]['produto']} em {negativa.iloc[0]['data']:%d/%m}.")
    tq = tanques[tanques["posto"] == posto].set_index("produto")["capacidade"]
    acima = (df[df.apply(lambda r: r["produto"] in tq.index and r["estoque_final"] > tq[r["produto"]] * 1.02,
                         axis=1)] if "estoque_final" in tem and len(df) else vazio)
    if len(acima):
        r = acima.iloc[0]
        rel.aviso(f"{r['produto']} com estoque acima da capacidade do tanque em {r['data']:%d/%m} "
                  f"({format_litros(r['estoque_final'])} para {format_litros(tq[r['produto']])}).")
    # Conta do LMC dentro do mês.
    for prod, g in (df.sort_values("data").groupby("produto") if {"estoque_inicial", "estoque_final"} <= tem else []):
        salto = (g["estoque_inicial"] - g["estoque_final"].shift()).abs() > 1
        salto.iloc[0] = False
        if salto.any():
            rel.aviso(f"{prod}: o estoque inicial não bate com o final do dia anterior em "
                      f"{int(salto.sum())} dia(s) (ex.: {g.loc[salto, 'data'].iloc[0]:%d/%m}).")

    # 7. Dias.
    dias = sorted(df["data"].dt.date.unique())
    faltam = (dias[-1] - dias[0]).days + 1 - len(dias)
    if faltam:
        rel.aviso(f"Faltam {faltam} dia(s) entre {dias[0]:%d/%m} e {dias[-1]:%d/%m}.")
    else:
        rel.ok(f"{len(dias)} dias encontrados ({dias[0]:%d/%m} a {dias[-1]:%d/%m})")

    # 8. Duplicado.
    if hash_atual and hash_atual == hashlib.sha256(conteudo).hexdigest():
        rel.duplicado = True
        rel.aviso("Esta planilha é idêntica à que já está no painel — não há nada para atualizar.")

    if rel.erros:
        return rel

    # 9. Resumo e comparação com a versão que está no painel.
    fat = float((df["vendas_l"] * df["preco_medio"]).sum())
    margem = float((df["vendas_l"] * (df["preco_medio"] - df["custo_medio"])).sum())
    rel.resumo = {"registros": len(df), "dias": len(dias), "ate": dias[-1],
                  "litros": float(df["vendas_l"].sum()), "faturamento": fat, "margem": margem}
    if len(movimento_base):
        antigo = movimento_base[(movimento_base["posto"] == posto)
                                & (movimento_base["ano"] == rel.ano) & (movimento_base["mes"] == rel.mes)]
        if len(antigo):
            rel.comparacao = {
                "ate": antigo["data"].max().date(),
                "litros": rel.resumo["litros"] - float(antigo["vendas_l"].sum()),
                "faturamento": fat - float(antigo["faturamento"].sum()),
                "margem": margem - float(antigo["margem"].sum()),
            }
    return rel


def texto_resumo(rel: Relatorio) -> str:
    r = rel.resumo
    return (f"dados até {r['ate']:%d/%m} · {format_int(r['registros'])} registros · "
            f"{format_litros(r['litros'])}")
