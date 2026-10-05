"""Menor Preço (Nota Paraná) — o preço REAL de venda, tirado da nota fiscal, quase em tempo real. TESTE LOCAL.

O app público "Menor Preço" do Paraná mostra, por posto, o último preço de cada combustível
que apareceu numa NFC-e (minutos de atraso). Diferente da ANP (uma amostra semanal, preço
anotado por pesquisador), aqui é o preço que o cliente pagou, de todos os postos que
emitem nota. Este módulo guarda esse retrato UMA VEZ POR DIA e deixa a série crescer.

Regras de convivência (o estado não publica termos nem API oficial para isso):

* só local: `data/mercado/nota_parana/` está no .gitignore; nada disso vai ao Git nem à nuvem;
* volume de pessoa: ~10 consultas por dia, com pausa sorteada de 8 a 20 s entre elas;
* nome honesto no User-Agent (B2-Gestao, teste local) e sem login, sem cookie, sem "disfarce";
* ao primeiro sinal de bloqueio (403, 429, página de verificação, JSON diferente do esperado)
  a coleta PARA, anota no log e não insiste — nunca tenta contornar.

Mesmo desenho do resto do projeto: `coletar_nota_parana.py` coleta e grava; este módulo só
lê e calcula; a tela (`radar_ui`) só desenha.
"""
from __future__ import annotations

import json
import math
import random
import re
import time
import difflib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from src import base

PASTA = base.PASTA_DADOS / "mercado" / "nota_parana"
ARQ_OFERTAS = "ofertas.parquet"
ARQ_LOG = "coletas.csv"
URL = "https://menorpreco.notaparana.pr.gov.br/api/v1/produtos"
AGENTE = "Mozilla/5.0 (compatible; B2-Gestao/1.0; teste local, 1 coleta por dia)"
ESPERA = (8.0, 20.0)                      # segundos entre uma consulta e a seguinte
MAX_PAGINAS = 3                           # a 1ª página costuma trazer tudo; as outras só se faltar
FUSO_BRT = timedelta(hours=-3)            # o Brasil não tem horário de verão desde 2019

# tp_comb do app: 1 gasolina, 2 aditivada, 3 etanol, 4 diesel (5, GNV, não interessa).
TIPOS = (1, 2, 3, 4)


@dataclass(frozen=True)
class Centro:
    """Um ponto e um raio (km) de busca. O servidor limita o raio a ~7 km."""
    nome: str
    geohash: str
    raio: int


# A cidade inteira, varrida em grade: a consulta só enxerga postos perto do ponto (e o servidor limita o raio),
# então cobrimos a mancha urbana com círculos que se sobrepõem. Os postos conhecidos ficam entre lat −25,43 e
# −25,35 e lon −51,51 e −51,44; a caixa abaixo dá folga para a BR-277 e os bairros novos.
CAIXA_GUARAPUAVA = (-25.46, -51.55, -25.31, -51.39)      # (sul, oeste, norte, leste)
PASSO_KM = 4.5                                           # distância entre pontos; raio 4 km cobre o quadrado inteiro
RAIO_KM = 4


def grade(caixa=CAIXA_GUARAPUAVA, passo_km: float = PASSO_KM, raio: int = RAIO_KM, nome: str = "Guarapuava") -> tuple[Centro, ...]:
    """Pontos de busca que cobrem a caixa (sul, oeste, norte, leste) sem buraco entre eles."""
    sul, oeste, norte, leste = caixa
    meia_lat = (sul + norte) / 2
    passo_lat = passo_km / 111.0
    passo_lon = passo_km / (111.0 * math.cos(math.radians(meia_lat)))
    linhas, colunas = math.ceil((norte - sul) / passo_lat), math.ceil((leste - oeste) / passo_lon)
    centros = []
    for i in range(linhas):
        for j in range(colunas):
            lat, lon = sul + (i + 0.5) * (norte - sul) / linhas, oeste + (j + 0.5) * (leste - oeste) / colunas
            centros.append(Centro(f"{nome} L{i + 1}C{j + 1}", geohash(lat, lon), raio))
    return tuple(centros)

# Os postos do B2 de Guarapuava pelo endereço da NFC-e (rua contém, número igual) — o Menor Preço
# não mostra CNPJ. Os endereços vêm do cadastro da ANP. Candói fica de fora por enquanto.
ENDERECOS_B2 = (("GUAIRA", "3148", "B2 Centro"), ("SEBASTIAO DE CAMARGO RIBAS", "1071", "B2 Bonsucesso"),
                ("JOAO FORTKAMP", "721", "B2 Primavera"), ("MANOEL RIBAS", "2760", "B2 Índio"))

# Nomes de gasolina aditivada de marca que não trazem a palavra "aditivada".
MARCAS_ADITIVADA = ("V POWER", "V-POWER", "PODIUM", "GRID", "NITRO", "IPIMAX", "SUPREME", "TECHRON", "EXTRA PREMIUM")
COLUNAS = ["loja", "razao", "fantasia", "rua", "numero", "bairro", "municipio", "desc", "cdanp", "produto", "preco",
           "datahora", "lat", "lon", "dist_km", "centro", "pagina", "unidade_b2", "coletado_em"]


class ColetaInterrompida(RuntimeError):
    """Algo no caminho parece bloqueio ou mudança do serviço: a coleta para e não insiste."""


# ------------------------------------------------------------------ geohash ---
_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat: float, lon: float, n: int = 9) -> str:
    """Código que o app usa para o ponto de busca (para trocar o centro por outro lugar)."""
    la, lo, saida, bits, ch, par = [-90.0, 90.0], [-180.0, 180.0], "", 0, 0, True
    while len(saida) < n:
        faixa, v = (lo, lon) if par else (la, lat)
        meio = (faixa[0] + faixa[1]) / 2
        if v >= meio:
            ch, faixa[0] = ch * 2 + 1, meio
        else:
            ch, faixa[1] = ch * 2, meio
        par, bits = not par, bits + 1
        if bits == 5:
            saida, bits, ch = saida + _B32[ch], 0, 0
    return saida


def decodificar(codigo: str) -> tuple[float, float]:
    """O ponto (lat, lon) de um geohash — cada oferta traz o do posto (aproximado: alguns têm só ~150 m de precisão)."""
    la, lo, par = [-90.0, 90.0], [-180.0, 180.0], True
    for c in codigo:
        v = _B32.index(c)
        for bit in (16, 8, 4, 2, 1):
            faixa = lo if par else la
            meio = (faixa[0] + faixa[1]) / 2
            faixa[0 if v & bit else 1] = meio
            par = not par
    return (la[0] + la[1]) / 2, (lo[0] + lo[1]) / 2


CENTROS = grade()                     # depois do geohash: a grade já nasce em código de busca
# A 1ª varredura em grade (05/10/2026, 65 consultas) achou 32 postos — os MESMOS que uma consulta larga a partir do
# centro (raio 8 km, o servidor corta em ~7 km) já tinha achado. Por isso o dia a dia usa só o ponto central, e a
# grade completa roda uma vez por mês, para pegar posto novo na periferia.
CENTRO_LARGO = (Centro("Guarapuava (centro)", "6g7rscrbp", 8),)
DIAS_ENTRE_VARREDURAS = 30


# ------------------------------------------------------------ interpretação ---
def _sem_acento(texto) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).upper().strip()


def classificar(desc: str, tp: int) -> str | None:
    """Que combustível é, pelo NOME que o posto deu na nota. O `tp_comb` do app mistura (a V-Power vem
    na busca de gasolina comum, e a "Gasolina Original" da Ipiranga na de aditivada) — o nome é mais fiel."""
    d = _sem_acento(desc)
    if tp in (1, 2) and ("GASOLINA" in d or d.startswith("GC ") or d.startswith("GA ") or d.startswith("GO ")):
        if "ADITIV" in d or any(m in d for m in MARCAS_ADITIVADA) or d.startswith("GA "):
            return "Gasolina Aditivada"
        return "Gasolina Comum"
    if tp == 3 and ("ETANOL" in d or "ALCOOL" in d):
        return "Etanol"
    if tp == 4 and "DIESEL" in d:
        return "Diesel S10" if re.search(r"S[ -]?10\b", d) else "Diesel S500"
    return None


def unidade_b2(rua: str, numero: str, municipio: str) -> str:
    if _sem_acento(municipio) != "GUARAPUAVA":
        return ""
    rua, numero = _sem_acento(rua), str(numero).strip().lstrip("0")
    for chave, num, nome in ENDERECOS_B2:
        if chave in rua and numero == num:
            return nome
    return ""


def normalizar(resposta: dict, centro: str, tp: int, coletado_em: datetime, pagina: int = 1) -> pd.DataFrame:
    """A resposta JSON do app -> uma linha por oferta (posto × combustível × nota), já classificada."""
    linhas = []
    for p in resposta.get("produtos", []):
        e = p.get("estabelecimento", {})
        produto = classificar(p.get("desc", ""), tp)
        try:
            preco = float(p["valor"])
            quando = datetime.fromisoformat(str(p["datahora"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        if produto is None or preco <= 0:
            continue
        rua = f"{e.get('tp_logr', '')} {e.get('nm_logr', '')}".strip()
        try:
            lat, lon = decodificar(p["local"])
        except (KeyError, ValueError):
            lat = lon = float("nan")
        linhas.append({
            "loja": e.get("codigo", ""), "razao": e.get("nm_emp", ""), "fantasia": e.get("nm_fan", ""), "rua": rua,
            "numero": str(e.get("nr_logr", "")).strip(), "bairro": e.get("bairro", ""), "municipio": e.get("mun", ""),
            "desc": p.get("desc", ""), "cdanp": p.get("cdanp", ""), "produto": produto, "preco": preco,
            "datahora": (quando + FUSO_BRT).replace(tzinfo=None), "lat": lat, "lon": lon, "dist_km": float(p.get("distkm") or 0),
            "centro": centro, "pagina": pagina, "unidade_b2": unidade_b2(e.get("nm_logr", ""), e.get("nr_logr", ""), e.get("mun", "")),
            "coletado_em": coletado_em})
    return pd.DataFrame(linhas, columns=COLUNAS)


# ------------------------------------------------------------------- coleta ---
def _abrir(url: str) -> tuple[int, str, bytes]:
    """Uma consulta HTTP. Devolve (status, content-type, corpo); erro HTTP vira status, não exceção."""
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.headers.get("Content-Type", "") if erro.headers else "", b""


def consultar(centro: Centro, tp: int, offset: int = 0, abrir: Callable = _abrir, dormir: Callable = time.sleep) -> dict:
    """UMA consulta ao app. Qualquer coisa fora do esperado interrompe a coleta (não tenta de novo, não contorna)."""
    consulta = urllib.parse.urlencode({"local": centro.geohash, "offset": offset, "raio": centro.raio, "data": -1,
                                       "ordem": 0, "tp_comb": tp})
    for tentativa in (1, 2):
        try:
            status, tipo, corpo = abrir(f"{URL}?{consulta}")
            break
        except (urllib.error.URLError, TimeoutError, OSError) as erro:    # rede oscilou: UMA nova tentativa, bem depois
            if tentativa == 2:
                raise ColetaInterrompida(f"sem resposta do servidor ({erro}); parei.") from erro
            dormir(45)
    if status in (401, 403, 429):
        raise ColetaInterrompida(f"o servidor respondeu HTTP {status} (acesso negado ou limite): parei e não insisto.")
    if status != 200:
        raise ColetaInterrompida(f"o servidor respondeu HTTP {status}: parei.")
    try:
        dados = json.loads(corpo.decode("utf-8"))
        if not isinstance(dados, dict) or not isinstance(dados.get("produtos"), list):
            raise ValueError("formato novo")
    except ValueError as erro:
        raise ColetaInterrompida("a resposta não veio no formato esperado (mudança do serviço ou página de "
                                 "verificação): parei.") from erro
    return dados


@dataclass
class Resultado:
    linhas: pd.DataFrame
    consultas: int = 0
    status: str = "ok"                                    # "ok" | "interrompida"
    mensagem: str = ""
    extras_de_paginacao: int = 0              # postos achados só na 2ª página em diante (diz se a paginação compensa)
    modo: str = "diaria"                      # "diaria" (ponto central) | "completa" (grade da cidade)


def coletar(centros=CENTRO_LARGO, tipos=TIPOS, espera=ESPERA, abrir: Callable = _abrir, dormir: Callable = time.sleep,
            agora: Callable = datetime.now, avisar: Callable = lambda _: None, modo: str = "diaria") -> Resultado:
    """O retrato do dia: cada tipo de combustível em cada centro, uma consulta por vez, com pausa entre elas."""
    inicio = agora()
    partes, consultas, extras = [], 0, 0          # extras: postos que só vieram da 2ª página em diante
    try:
        for centro in centros:
            for tp in tipos:
                vistos: set[tuple] = set()
                recebidas = 0
                for pagina in range(MAX_PAGINAS):
                    if consultas:
                        dormir(random.uniform(*espera))
                    dados = consultar(centro, tp, recebidas, abrir, dormir)
                    consultas += 1
                    novas = normalizar(dados, centro.nome, tp, inicio, pagina + 1)
                    chaves = set(zip(novas["loja"], novas["desc"], novas["datahora"], novas["preco"]))
                    recebidas += len(dados["produtos"])
                    total = int(dados.get("total") or 0)
                    if pagina:
                        extras += len(set(novas["loja"]) - lojas_da_1a)
                    else:
                        lojas_da_1a = set(novas["loja"])
                    avisar(f"  {centro.nome} · tp {tp} · página {pagina + 1}: {recebidas} de {total} ofertas, "
                           f"{novas['loja'].nunique()} postos")
                    partes.append(novas)
                    if not (chaves - vistos) or recebidas >= total:
                        break                                     # nada novo, ou já veio tudo
                    vistos |= chaves
                if tp == tipos[0] and not recebidas:
                    break                                         # ponto sem nenhum posto (mata, rio): não pergunta o resto
    except ColetaInterrompida as erro:
        return Resultado(_juntar(partes), consultas, "interrompida", str(erro), extras, modo)
    return Resultado(_juntar(partes), consultas, extras_de_paginacao=extras, modo=modo)


def _sem_repetidas(df: pd.DataFrame) -> pd.DataFrame:
    """Uma mesma nota entra uma vez POR DIA DE COLETA: o app só mostra a última nota de cada posto, então um posto parado
    repete a mesma nota por dias — e cada coleta precisa ficar completa, senão a série do dia seguinte perde postos."""
    if df.empty:
        return df.reset_index(drop=True)
    dia = pd.to_datetime(df["coletado_em"]).dt.normalize().rename("_dia")
    return df[~pd.concat([df[["loja", "desc", "datahora", "preco"]], dia], axis=1).duplicated()].reset_index(drop=True)


def _juntar(partes: list[pd.DataFrame]) -> pd.DataFrame:
    partes = [p for p in partes if len(p)]
    return _sem_repetidas(pd.concat(partes, ignore_index=True)) if partes else pd.DataFrame(columns=COLUNAS)


# ------------------------------------------------------------ gravar e ler ---
def gravar(novas: pd.DataFrame, pasta: Path = PASTA) -> int:
    """Junta ao que já existe (sem repetir a mesma nota) e troca o arquivo de uma vez. Devolve quantas linhas entraram."""
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / ARQ_OFERTAS
    antes = pd.read_parquet(arq) if arq.exists() else pd.DataFrame(columns=COLUNAS)
    junto = _juntar([antes, novas]).sort_values(["datahora", "loja"], ignore_index=True)
    tmp = arq.with_suffix(".tmp")
    junto.to_parquet(tmp, index=False)
    tmp.replace(arq)
    return len(junto) - len(antes)


def anotar(resultado: Resultado, novas: int, quando: datetime, pasta: Path = PASTA) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    nova = pd.DataFrame([{"quando": quando.strftime("%Y-%m-%d %H:%M:%S"), "status": resultado.status, "modo": resultado.modo,
                          "consultas": resultado.consultas, "ofertas": len(resultado.linhas), "novas": novas,
                          "mensagem": resultado.mensagem}])
    antes = ler_log(pasta)
    junto = pd.concat([antes, nova], ignore_index=True) if len(antes) else nova
    junto["quando"] = pd.to_datetime(junto["quando"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    junto.to_csv(pasta / ARQ_LOG, index=False, encoding="utf-8")          # reescreve: é pequeno e o log antigo não tinha "modo"


def ler_log(pasta: Path = PASTA) -> pd.DataFrame:
    colunas = ["quando", "status", "modo", "consultas", "ofertas", "novas", "mensagem"]
    log = pasta / ARQ_LOG
    if not log.exists():
        return pd.DataFrame(columns=colunas)
    df = pd.read_csv(log, encoding="utf-8", parse_dates=["quando"])
    for c in colunas:
        if c not in df:
            df[c] = 0 if c in ("consultas", "ofertas", "novas") else ""
    df[["modo", "mensagem"]] = df[["modo", "mensagem"]].fillna("")                 # CSV vazio volta como NaN
    return df[colunas]


def precisa_varredura_completa(hoje: datetime, pasta: Path = PASTA) -> bool:
    """A grade da cidade roda na 1ª vez e depois a cada `DIAS_ENTRE_VARREDURAS` dias; no resto, só o ponto central."""
    log = ler_log(pasta)
    feitas = log[(log["status"] == "ok") & (log["modo"] == "completa")]
    return feitas.empty or (pd.Timestamp(hoje) - feitas["quando"].max()).days >= DIAS_ENTRE_VARREDURAS


def ja_coletou_hoje(hoje: datetime, pasta: Path = PASTA) -> bool:
    log = ler_log(pasta)
    return bool(len(log) and ((log["status"] == "ok") & (log["quando"].dt.date == hoje.date())).any())


def carregar(pasta: Path = PASTA) -> pd.DataFrame | None:
    arq = pasta / ARQ_OFERTAS
    return pd.read_parquet(arq) if arq.exists() else None


def assinatura(pasta: Path = PASTA) -> tuple:
    return tuple((p.name, p.stat().st_mtime_ns) for p in sorted(pasta.glob("*"))) if pasta.exists() else ()


def agora_brt() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + FUSO_BRT


# ----------------------------------------------------------------- análises ---
def foto(of: pd.DataFrame, produto: str, horas: int = 48, ate=None) -> pd.DataFrame:
    """O preço "de agora" de cada posto: a nota mais recente do combustível, dentro de `horas` até `ate`."""
    g = of[of["produto"] == produto]
    if g.empty:
        return g.set_index("loja")
    ate = pd.Timestamp(ate) if ate is not None else g["datahora"].max()
    g = g[(g["datahora"] <= ate) & (g["datahora"] >= ate - pd.Timedelta(hours=horas))]
    return g.sort_values(["datahora", "preco"]).groupby("loja").tail(1).set_index("loja")


def resumo(f: pd.DataFrame) -> dict:
    """A cidade na foto e onde cada posto do B2 ficou (1 = o mais barato; empate divide a posição)."""
    if f.empty:
        return {}
    b2 = []
    for loja, linha in f[f["unidade_b2"] != ""].iterrows():
        b2.append({"unidade": linha["unidade_b2"], "preco": float(linha["preco"]), "datahora": linha["datahora"],
                   "posicao": int((f["preco"] < linha["preco"] - 1e-9).sum()) + 1, "loja": loja})
    return {"n": int(len(f)), "media": float(f["preco"].mean()), "mediana": float(f["preco"].median()),
            "minimo": float(f["preco"].min()), "maximo": float(f["preco"].max()), "b2": b2}


def historico_diario(of: pd.DataFrame, produto: str) -> pd.DataFrame:
    """Dia a dia, pelo DIA DA COLETA: o que o app mostrava (a última nota de cada posto) em cada coleta -> faixa da cidade
    e preço de cada unidade do B2. Pela data da nota não serve: ela só existe para quem vendeu naquele dia."""
    g = of[of["produto"] == produto].copy()
    g["dia"] = pd.to_datetime(g["coletado_em"]).dt.normalize()
    g = g.sort_values("datahora").groupby(["dia", "loja"], as_index=False).tail(1)
    linhas = []
    for dia, d in g.groupby("dia"):
        linha = {"dia": dia, "n": int(len(d)), "minimo": float(d["preco"].min()), "mediana": float(d["preco"].median()),
                 "maximo": float(d["preco"].max())}
        for _, r in d[d["unidade_b2"] != ""].iterrows():
            linha[r["unidade_b2"]] = float(r["preco"])
        linhas.append(linha)
    return pd.DataFrame(linhas)


def premio_aditivada(of: pd.DataFrame, horas: int = 48) -> pd.DataFrame:
    """Por posto: comum, aditivada e a diferença (R$/L) — só quem tem os dois preços na janela."""
    c, a = foto(of, "Gasolina Comum", horas), foto(of, "Gasolina Aditivada", horas)
    if c.empty or a.empty:
        return pd.DataFrame(columns=["razao", "bairro", "unidade_b2", "comum", "aditivada", "premio"])
    j = c[["razao", "bairro", "unidade_b2", "preco"]].join(a[["preco"]], lsuffix="_c", rsuffix="_a", how="inner")
    j = j.rename(columns={"preco_c": "comum", "preco_a": "aditivada"})
    j["premio"] = (j["aditivada"] - j["comum"]).round(2)
    return j


_PREFIXOS_RUA = {"RUA", "AVENIDA", "AV", "R", "ALAMEDA", "RODOVIA", "ROD", "TRAVESSA", "TV", "PRACA", "ESTRADA", "LARGO"}


def _chave_rua(texto) -> str:
    palavras = [w for w in re.split(r"[^A-Z0-9]+", _sem_acento(texto)) if w]
    while palavras and palavras[0] in _PREFIXOS_RUA:
        palavras.pop(0)
    return " ".join(palavras)


def conferir_cadastro(of: pd.DataFrame, cadastro: pd.DataFrame, municipio: str = "GUARAPUAVA") -> pd.DataFrame:
    """Dos postos cadastrados na ANP no município, quais apareceram no Menor Preço (mesmo número e rua parecida).

    É a régua da varredura: quem está cadastrado e nunca aparece ou não vendeu no período, ou a varredura não o alcançou.
    O cadastro da ANP escreve o endereço como "RUA GUAIRA, 3148"; a nota, rua e número em campos separados.
    """
    lojas = of[of["municipio"].map(_sem_acento) == municipio].drop_duplicates("loja")
    lojas = lojas.assign(_n=lojas["numero"].str.extract(r"(\d+)")[0].fillna("").str.lstrip("0"), _r=lojas["rua"].map(_chave_rua))
    linhas = []
    for _, c in cadastro[cadastro["municipio"] == municipio].iterrows():
        rua, _, numero = str(c["endereco"]).rpartition(",")
        numero, chave = re.sub(r"\D", "", numero).lstrip("0"), _chave_rua(rua)
        achou = ""
        for _, l in lojas.iterrows():
            parecida = difflib.SequenceMatcher(None, chave, l["_r"]).ratio()
            mesmo_numero = l["_n"] == numero
            # o cadastro e a nota às vezes divergem em 1 ou 2 no número (3591 × 3592): vale se a rua for quase igual
            perto = (parecida >= 0.85 and l["_n"].isdigit() and numero.isdigit() and abs(int(l["_n"]) - int(numero)) <= 2)
            if (mesmo_numero and (parecida >= 0.6 or _sem_acento(l["bairro"]) == c["bairro"])) or perto:
                achou = l["loja"]
                break
        linhas.append({"cnpj": c["cnpj"], "razao": c["razao"], "endereco": c["endereco"], "bairro": c["bairro"],
                       "eh_b2": bool(c["eh_b2"]), "achado": bool(achou), "loja": achou})
    return pd.DataFrame(linhas, columns=["cnpj", "razao", "endereco", "bairro", "eh_b2", "achado", "loja"])


def estado(of: pd.DataFrame | None, pasta: Path = PASTA) -> dict:
    """Para a tela dizer o que já foi coletado: dias, última coleta, última interrupção."""
    log = ler_log(pasta)
    out = {"dias": 0, "ofertas": 0, "ultima": None, "interrompida": None}
    if of is not None and len(of):
        out.update(dias=int(pd.to_datetime(of["coletado_em"]).dt.normalize().nunique()), ofertas=int(len(of)))
    if len(log):
        ok = log[log["status"] == "ok"]
        out["ultima"] = ok["quando"].max() if len(ok) else None
        ruim = log[log["status"] != "ok"]
        out["interrompida"] = ruim.iloc[-1].to_dict() if len(ruim) and (not len(ok) or ruim["quando"].max() > ok["quando"].max()) else None
    return out
