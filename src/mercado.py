"""Radar de concorrência — preços PÚBLICOS de bomba da ANP em Guarapuava e Candói.

A ANP contrata uma pesquisa semanal de preços em uma AMOSTRA de postos e publica os
microdados, posto a posto, em CSV (dados abertos). Aqui eles viram Parquet e
alimentam a tela 📡 Radar de Mercado: onde cada unidade do B2 está contra a
cidade, quem subiu quanto quando o custo mexeu e como está o preço da aditivada.

Duas coisas que o dono precisa saber (a tela diz as duas):

* é AMOSTRA: em Guarapuava a ANP colhe preço de uns 5 a 14 postos por semana,
  de 51 cadastrados; em Candói não colhe nenhum;
* é o preço de bomba que um pesquisador anotou, não o da nota fiscal. O preço da
  nota (Nota Paraná) é outra fonte, ainda não conectada.

Mesmo desenho do resto do projeto: `atualizar_mercado.py` baixa e monta o Parquet
(`construir`); este módulo só lê e calcula; a tela só desenha.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import base

PASTA = base.PASTA_DADOS / "mercado"
BRUTO = PASTA / "bruto"
ARQ_PRECOS = PASTA / "precos_anp.parquet"
ARQ_CADASTRO = PASTA / "postos_anp.parquet"
ARQ_INFO = PASTA / "_info.json"

MUNICIPIOS = ("GUARAPUAVA", "CANDOI")
NOME_MUNICIPIO = {"GUARAPUAVA": "Guarapuava", "CANDOI": "Candói"}
# Raiz do CNPJ de "Begnini Comércio de Combustíveis" (as unidades de Guarapuava); a de Candói
# é outra empresa, "B2 Comércio de Combustíveis", achada pelo nome.
CNPJ_RAIZ_B2 = "09182266"
PRODUTOS = {"GASOLINA": "Gasolina Comum", "GASOLINA ADITIVADA": "Gasolina Aditivada",
            "ETANOL": "Etanol", "DIESEL S10": "Diesel S10"}
JANELA_FOTO = 14                     # dias: "o preço atual" de um posto é a última coleta dessa janela
MIN_POSTOS_SEMANA = 4                # semana com menos postos que isso não entra no ranking

URL_ANP = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos"
URL_SERIE = f"{URL_ANP}/serie-historica-de-precos-de-combustiveis"
URL_CADASTRO = (f"{URL_ANP}/arquivos/arquivos-dados-cadastrais-dos-revendedores-varejistas-de-"
                "combustiveis-automotivos/dados-cadastrais-revendedores-varejistas-combustiveis-automoveis.csv")
AGENTE = "Mozilla/5.0 (compatible; B2-Gestao/1.0; uso interno, 1 coleta por semana)"


# ----------------------------------------------------------------- leitura ---
def _sem_acento(texto) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).upper().strip()


def _colunas(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=lambda c: str(c).replace("﻿", "").replace("ï»¿", "").strip())


def _eh_b2(cnpj: pd.Series, nome: pd.Series) -> pd.Series:
    return cnpj.str.startswith(CNPJ_RAIZ_B2) | nome.str.upper().str.startswith("B2 ")


def normalizar_precos(bruto: pd.DataFrame) -> pd.DataFrame:
    """Um pedaço do CSV da ANP -> só PR/Guarapuava+Candói, só os quatro combustíveis, colunas limpas."""
    df = _colunas(bruto)
    municipio = df["Municipio"].map(_sem_acento)
    df = df[(df["Estado - Sigla"] == "PR") & municipio.isin(MUNICIPIOS)]
    vazio = pd.DataFrame(columns=["data", "cnpj", "revenda", "rua", "numero", "bairro", "municipio",
                                  "produto", "preco", "bandeira", "eh_b2"])
    if df.empty:
        return vazio
    out = pd.DataFrame({
        "data": pd.to_datetime(df["Data da Coleta"], format="%d/%m/%Y", errors="coerce"),
        "cnpj": df["CNPJ da Revenda"].astype(str).str.replace(r"\D", "", regex=True),
        "revenda": df["Revenda"].astype(str).str.strip(),
        "rua": df["Nome da Rua"].astype(str).str.strip(),
        "numero": df["Numero Rua"].astype(str).str.strip(),
        "bairro": df["Bairro"].astype(str).str.strip().str.upper(),
        "municipio": municipio[df.index],
        "produto": df["Produto"].astype(str).str.strip().str.upper(),
        "preco": pd.to_numeric(df["Valor de Venda"].astype(str).str.replace(",", "."), errors="coerce"),
        "bandeira": df["Bandeira"].astype(str).str.strip().str.title(),
    })
    out = out[out["produto"].isin(PRODUTOS)].dropna(subset=["data", "preco"])
    out["eh_b2"] = _eh_b2(out["cnpj"], out["revenda"])
    # O mesmo posto/dia/produto aparece nos arquivos mensal e semestral (e com CNPJ formatado de dois jeitos).
    return out.drop_duplicates(["cnpj", "data", "produto"]).reset_index(drop=True)


def normalizar_cadastro(bruto: pd.DataFrame) -> pd.DataFrame:
    df = _colunas(bruto)
    municipio = df["MUNICIPIO"].map(_sem_acento)
    df = df[(df["UF"] == "PR") & municipio.isin(MUNICIPIOS)]
    out = pd.DataFrame({
        "cnpj": df["CNPJ"].astype(str).str.replace(r"\D", "", regex=True),
        "razao": df["RAZAOSOCIAL"].astype(str).str.strip(),
        "endereco": df["ENDERECO"].astype(str).str.replace(r"\s*,\s*", ", ", regex=True).str.strip(),
        "bairro": df["BAIRRO"].astype(str).str.strip().str.upper(),
        "municipio": municipio[df.index],
        "bandeira": df["BANDEIRA"].astype(str).str.strip().str.title(),
    })
    out["eh_b2"] = _eh_b2(out["cnpj"], out["razao"])
    return out.drop_duplicates("cnpj").reset_index(drop=True)


def ler_bruto(pasta: Path = BRUTO) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Lê tudo o que está em `pasta` (zips semestrais, CSVs mensais, cadastro)."""
    partes, usados = [], []
    for arq in sorted(pasta.glob("*")):
        if arq.name.startswith("cadastro"):
            continue
        if arq.suffix == ".zip":
            with zipfile.ZipFile(arq) as z:
                for nome in z.namelist():
                    with z.open(nome) as fh:
                        for pedaco in pd.read_csv(fh, sep=";", encoding="utf-8-sig", dtype=str, chunksize=250_000):
                            partes.append(normalizar_precos(pedaco))
        elif arq.suffix == ".csv":
            for pedaco in pd.read_csv(arq, sep=";", encoding="utf-8-sig", dtype=str, chunksize=250_000):
                partes.append(normalizar_precos(pedaco))
        else:
            continue
        usados.append(arq.name)
    precos = pd.concat(partes, ignore_index=True) if partes else normalizar_precos(pd.DataFrame(
        columns=["Municipio", "Estado - Sigla"]))
    precos = precos.drop_duplicates(["cnpj", "data", "produto"]).sort_values(["data", "cnpj"]).reset_index(drop=True)
    cad_arq = pasta / "cadastro-revendedores.csv"
    cadastro = (normalizar_cadastro(pd.read_csv(cad_arq, sep=";", encoding="utf-8", dtype=str))
                if cad_arq.exists() else pd.DataFrame(columns=["cnpj", "razao", "endereco", "bairro", "municipio",
                                                               "bandeira", "eh_b2"]))
    return precos, cadastro, usados


def construir(pasta_bruta: Path = BRUTO, saida: Path = PASTA) -> dict:
    precos, cadastro, usados = ler_bruto(pasta_bruta)
    if precos.empty:
        raise ValueError("Nenhum preço de Guarapuava/Candói nos arquivos da ANP — nada foi gravado.")
    saida.mkdir(parents=True, exist_ok=True)
    precos.to_parquet(saida / ARQ_PRECOS.name, index=False)
    cadastro.to_parquet(saida / ARQ_CADASTRO.name, index=False)
    info = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
            "primeira_coleta": precos["data"].min().strftime("%Y-%m-%d"),
            "ultima_coleta": precos["data"].max().strftime("%Y-%m-%d"),
            "postos_com_preco": int(precos["cnpj"].nunique()), "postos_cadastrados": int(len(cadastro)),
            "linhas": int(len(precos)), "arquivos": usados, "fonte": URL_SERIE}
    (saida / ARQ_INFO.name).write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


@dataclass
class Mercado:
    precos: pd.DataFrame
    cadastro: pd.DataFrame
    info: dict


def carregar(pasta: Path = PASTA) -> Mercado | None:
    arq_p, arq_c, arq_i = pasta / ARQ_PRECOS.name, pasta / ARQ_CADASTRO.name, pasta / ARQ_INFO.name
    if not (arq_p.exists() and arq_c.exists()):
        return None
    info = json.loads(arq_i.read_text(encoding="utf-8")) if arq_i.exists() else {}
    return Mercado(pd.read_parquet(arq_p), pd.read_parquet(arq_c), info)


def assinatura(pasta: Path = PASTA) -> tuple:
    return tuple((p.name, p.stat().st_mtime_ns) for p in sorted(pasta.glob("*.parquet"))) if pasta.exists() else ()


# ---------------------------------------------------------- unidades do B2 ---
# O cadastro da ANP só tem a razão social e o bairro do CNPJ. Os nomes que o dono usa vêm daqui.
# "B2 Índio" é o "Posto Índio", na Av. Manoel Ribas, 2760 (bairro Conradinho no cadastro).
NOMES_B2 = {"09182266000177": "B2 Centro", "09182266000339": "B2 Bonsucesso", "09182266000410": "B2 Primavera",
            "09182266000258": "B2 Índio", "10592615000108": "B2 Candói"}
ORDEM_B2 = list(NOMES_B2.values())


def nome_unidade(municipio: str, bairro: str, cnpj: str = "") -> str:
    if cnpj in NOMES_B2:
        return NOMES_B2[cnpj]
    return "B2 Candói" if municipio == "CANDOI" else f"B2 {str(bairro).title()}"


def unidades_b2(cadastro: pd.DataFrame, precos: pd.DataFrame) -> pd.DataFrame:
    """As unidades do B2 no cadastro da ANP, e quais delas a pesquisa de preços chega a colher."""
    u = cadastro[cadastro["eh_b2"]].copy()
    u["nome"] = [nome_unidade(m, b, c) for m, b, c in zip(u["municipio"], u["bairro"], u["cnpj"])]
    u["tem_preco"] = u["cnpj"].isin(set(precos["cnpj"]))
    u["_ordem"] = u["nome"].map(lambda n: ORDEM_B2.index(n) if n in ORDEM_B2 else 99)
    return u.sort_values(["_ordem", "nome"]).drop(columns="_ordem").reset_index(drop=True)


def com_preco_informado(f: pd.DataFrame, un: pd.Series, produto: str, preco: float, data) -> pd.DataFrame:
    """Acrescenta à foto da cidade o preço que o próprio B2 informa, para os postos que a ANP não pesquisa."""
    linha = pd.DataFrame([{"data": pd.Timestamp(data), "revenda": un["razao"], "rua": "", "numero": "", "bairro": un["bairro"],
                           "municipio": un["municipio"], "produto": produto, "preco": float(preco),
                           "bandeira": str(un["bandeira"]).replace("Bandeira ", ""),          # o cadastro diz "Bandeira Branca"
                           "eh_b2": True}], index=pd.Index([un["cnpj"]], name="cnpj"))
    return pd.concat([f[~f.index.isin([un["cnpj"]])], linha])


# ----------------------------------------------------------------- análises ---
def foto(precos: pd.DataFrame, produto: str, ate=None, janela: int = JANELA_FOTO) -> pd.DataFrame:
    """O preço "de agora" de cada posto: a última coleta dentro de `janela` dias até `ate`."""
    g = precos[precos["produto"] == produto]
    if g.empty:
        return g.set_index("cnpj")
    ate = pd.Timestamp(ate) if ate is not None else g["data"].max()
    g = g[(g["data"] <= ate) & (g["data"] >= ate - pd.Timedelta(days=janela))]
    return g.sort_values("data").groupby("cnpj").tail(1).set_index("cnpj")


def posicao(f: pd.DataFrame, cnpj: str) -> dict | None:
    """Onde `cnpj` está na foto: preço, média, mínimo e a posição (1 = o mais barato)."""
    if cnpj not in f.index or len(f) == 0:
        return None
    p = float(f.loc[cnpj, "preco"])
    return {"preco": p, "media": float(f["preco"].mean()), "mediana": float(f["preco"].median()),
            "minimo": float(f["preco"].min()), "maximo": float(f["preco"].max()), "n": int(len(f)),
            "posicao": int((f["preco"] < p - 1e-9).sum()) + 1, "data": f.loc[cnpj, "data"]}


def serie_semanal(precos: pd.DataFrame, produto: str, cnpj: str, min_postos: int = MIN_POSTOS_SEMANA) -> pd.DataFrame:
    """Semana a semana: o preço da unidade, a faixa da cidade (mín–máx), a mediana e a posição."""
    g = precos[precos["produto"] == produto].copy()
    colunas = ["semana", "b2", "minimo", "mediana", "maximo", "media", "n", "posicao"]
    if g.empty:
        return pd.DataFrame(columns=colunas)
    g["semana"] = g["data"].dt.to_period("W-SUN").dt.start_time
    g = g.sort_values("data").groupby(["semana", "cnpj"], as_index=False).tail(1)
    linhas = []
    for semana, s in g.groupby("semana"):
        b = s[s["cnpj"] == cnpj]
        if b.empty or len(s) < min_postos:
            continue
        pb = float(b["preco"].iloc[0])
        linhas.append({"semana": semana, "b2": pb, "minimo": float(s["preco"].min()), "mediana": float(s["preco"].median()),
                       "maximo": float(s["preco"].max()), "media": float(s["preco"].mean()), "n": int(len(s)),
                       "posicao": int((s["preco"] < pb - 1e-9).sum()) + 1})
    return pd.DataFrame(linhas, columns=colunas)


def variacao(precos: pd.DataFrame, produto: str, inicio, fim, janela: int = JANELA_FOTO) -> pd.DataFrame:
    """Quanto cada posto mexeu no preço entre duas datas — só postos com preço nas DUAS pontas.

    Comparar a média das duas datas engana: a amostra da ANP muda de uma semana para outra.
    """
    a, b = foto(precos, produto, inicio, janela), foto(precos, produto, fim, janela)
    if a.empty or b.empty:
        return pd.DataFrame(columns=["cnpj", "revenda", "bairro", "bandeira", "eh_b2", "preco_a", "preco_b", "variacao"])
    j = a[["revenda", "bairro", "bandeira", "eh_b2", "preco"]].join(b[["preco"]], lsuffix="_a", rsuffix="_b", how="inner")
    j["variacao"] = (j["preco_b"] - j["preco_a"]).round(2)
    return j.reset_index().sort_values("variacao", ascending=False).reset_index(drop=True)


def premio_aditivada(precos: pd.DataFrame, cnpj: str) -> dict | None:
    """Quanto a aditivada custa a mais que a comum (R$/L): na unidade e nos demais postos."""
    piv = (precos[precos["produto"].isin(["GASOLINA", "GASOLINA ADITIVADA"])]
           .pivot_table(index=["cnpj", "data"], columns="produto", values="preco").dropna())
    if piv.empty or "GASOLINA ADITIVADA" not in piv or "GASOLINA" not in piv:
        return None
    piv["premio"] = (piv["GASOLINA ADITIVADA"] - piv["GASOLINA"]).round(2)
    proprio = piv[piv.index.get_level_values("cnpj") == cnpj]["premio"]
    outros = piv[piv.index.get_level_values("cnpj") != cnpj]["premio"]
    if proprio.empty or outros.empty:
        return None
    return {"coletas": int(len(proprio)), "unidade": float(proprio.mean()),
            "sempre_igual": bool((proprio.abs() < 0.005).all()),
            "mercado_mediana": float(outros.median()), "mercado_com_premio": float((outros > 0.005).mean())}


def ranking_historico(s: pd.DataFrame) -> dict:
    """De `serie_semanal`: em que fatia das semanas a unidade foi a mais barata, top 2 e top 3."""
    if s.empty:
        return {"semanas": 0, "primeiro": np.nan, "top2": np.nan, "top3": np.nan}
    return {"semanas": int(len(s)), "primeiro": float((s["posicao"] == 1).mean()),
            "top2": float((s["posicao"] <= 2).mean()), "top3": float((s["posicao"] <= 3).mean())}


def cobertura(precos: pd.DataFrame, cadastro: pd.DataFrame, municipio: str = "GUARAPUAVA", dias: int = 90) -> dict:
    """Quantos postos a pesquisa de fato colhe, contra os cadastrados no município."""
    p = precos[precos["municipio"] == municipio]
    recentes = p[p["data"] >= p["data"].max() - pd.Timedelta(days=dias)] if len(p) else p
    return {"amostrados": int(recentes["cnpj"].nunique()), "cadastrados": int((cadastro["municipio"] == municipio).sum()),
            "dias": dias}


# ------------------------------------------------- descobrir e baixar arquivos ---
def descobrir_links(html: str) -> dict:
    """Acha, na página da série histórica, os zips semestrais e os CSVs mensais (nomes irregulares)."""
    semestres, mensais = {}, {}
    for href in set(re.findall(r'href="([^"]+)"', html)):
        m = re.search(r"/dsas/ca/ca-(\d{4})-(\d{2})\.(?:zip|csv)$", href)
        if m:
            semestres[(int(m.group(1)), int(m.group(2)))] = href
            continue
        m = (re.search(r"/dsan/(\d{4})/(\d{2})-[^/]*?(gasolina-etanol|diesel-gnv)(?:\.csv)?$", href)
             or None)
        if m:
            mensais[(int(m.group(1)), int(m.group(2)), m.group(3))] = href
            continue
        m = re.search(r"/dsan/(\d{4})/precos-(gasolina-etanol|diesel-gnv)-(\d{2})\.csv$", href)
        if m:
            mensais[(int(m.group(1)), int(m.group(3)), m.group(2))] = href
    return {"semestres": semestres, "mensais": mensais}


def selecionar(links: dict, hoje: date, meses: int = 15) -> list[tuple[str, str]]:
    """Que arquivos baixar para cobrir os últimos `meses`: zips semestrais fechados + CSVs dos meses que sobram."""
    ini = (pd.Timestamp(hoje).to_period("M") - meses).to_timestamp()
    alvo: list[tuple[str, str]] = []
    cobertos: set[tuple[int, int]] = set()
    for (ano, sem), url in sorted(links["semestres"].items()):
        meses_sem = [(ano, m) for m in ((1, 2, 3, 4, 5, 6) if sem == 1 else (7, 8, 9, 10, 11, 12))]
        if pd.Timestamp(ano, meses_sem[-1][1], 1) + pd.offsets.MonthEnd(0) >= ini:
            alvo.append((f"ca-{ano}-{sem:02d}.zip", url))
            cobertos.update(meses_sem)
    for (ano, mes, tipo), url in sorted(links["mensais"].items()):
        inicio_mes = pd.Timestamp(ano, mes, 1)
        if (ano, mes) not in cobertos and ini <= inicio_mes <= pd.Timestamp(hoje):
            alvo.append((f"{ano}-{mes:02d}-{tipo}.csv", url))
    alvo.append(("cadastro-revendedores.csv", URL_CADASTRO))
    return alvo


def baixar(url: str, destino: Path, tentativas: int = 2) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    ultimo = None
    for _ in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(req, timeout=120) as r, open(destino.with_suffix(destino.suffix + ".tmp"), "wb") as f:
                total = 0
                while pedaco := r.read(1 << 20):
                    f.write(pedaco)
                    total += len(pedaco)
            destino.with_suffix(destino.suffix + ".tmp").replace(destino)
            return total
        except Exception as erro:  # rede fora, arquivo ainda não publicado...
            ultimo = erro
    raise RuntimeError(f"não consegui baixar {url}: {ultimo}")


def pagina_serie() -> str:
    req = urllib.request.Request(URL_SERIE, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")
