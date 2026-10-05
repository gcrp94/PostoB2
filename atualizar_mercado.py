"""Atualiza o Radar de Mercado: baixa os preços públicos da ANP e monta o Parquet.

    python atualizar_mercado.py             # baixa o que falta (e renova os 2 meses mais recentes) e monta
    python atualizar_mercado.py --montar    # só remonta o Parquet com o que já está em data/mercado/bruto/
    python atualizar_mercado.py --forcar    # baixa tudo de novo

A ANP atualiza os arquivos toda semana: uma rodada por semana basta. Os CSVs brutos
(dezenas de MB) ficam em `data/mercado/bruto/`, fora do Git; só o Parquet filtrado
(Guarapuava e Candói, alguns KB) vai para o repositório.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from src import mercado


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--montar", action="store_true", help="não baixa nada; só remonta o Parquet")
    ap.add_argument("--forcar", action="store_true", help="baixa todos os arquivos de novo")
    ap.add_argument("--meses", type=int, default=15, help="quantos meses de histórico (padrão 15)")
    args = ap.parse_args()

    if not args.montar:
        print("Consultando a página da ANP...")
        links = mercado.descobrir_links(mercado.pagina_serie())
        hoje = date.today()
        recentes = {(hoje.year, hoje.month), ((hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12))}
        for nome, url in mercado.selecionar(links, hoje, args.meses):
            destino = mercado.BRUTO / nome
            mensal_recente = destino.suffix == ".csv" and nome[:7].replace("-", "") and \
                (int(nome[:4]), int(nome[5:7])) in recentes if nome[:2] == "20" else False
            if destino.exists() and not args.forcar and not mensal_recente and nome != "cadastro-revendedores.csv":
                print(f"  = {nome} (já existe)")
                continue
            try:
                tamanho = mercado.baixar(url, destino)
                print(f"  ↓ {nome}  {tamanho / 1048576:.1f} MB")
            except RuntimeError as erro:
                print(f"  ✗ {erro}")

    print("Montando o Parquet (Guarapuava e Candói)...")
    try:
        info = mercado.construir()
    except ValueError as erro:
        print(erro)
        return 1
    print(f"  {info['linhas']:,} preços · {info['postos_com_preco']} postos com preço · "
          f"{info['postos_cadastrados']} cadastrados · coletas de {info['primeira_coleta']} a {info['ultima_coleta']}"
          .replace(",", "."))
    print(f"Gravado em {mercado.PASTA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
