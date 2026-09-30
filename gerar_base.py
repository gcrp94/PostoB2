"""Monta a base do painel a partir das planilhas dos postos.

    python gerar_base.py

Lê `data/<pasta do posto>/*.xlsx` e o `data/CADASTRO DOS POSTOS.xlsx`,
confere tudo e grava `data/base/*.parquet` — a base que o painel e o motor de
alertas leem. **O painel lê o Parquet, não o Excel**: planilha nova na pasta
não muda nada até rodar este script (o `Atualizar Dados.bat` roda este e, em
seguida, o motor de alertas). O envio de planilha pelo próprio painel chama a
mesma função.

O que ele imprime é a conferência de quem cuida das planilhas: quantos meses
de cada posto entraram e tudo o que não bateu, com o nome do arquivo.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from src import base
from src.formatting import nome_mes


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("Lendo as planilhas dos postos...")
    res = base.construir()
    try:
        base.gravar(res)
    except ValueError as erro:
        print(erro)
        for e in res.erros:
            print("  ERRO:", e)
        return 1

    meses = defaultdict(list)
    for a in res.arquivos:
        meses[a["posto"]].append((a["ano"], a["mes"]))
    print()
    for posto, lista in meses.items():
        lista.sort()
        ini, fim = lista[0], lista[-1]
        ultima = res.movimento.loc[res.movimento["posto"] == posto, "data"].max()
        print(f"  {posto:<14} {len(lista):>2} meses  ({nome_mes(ini[1], ini[0], True)} a "
              f"{nome_mes(fim[1], fim[0], True)}) · dados até {ultima:%d/%m/%Y}")
    print(f"\n  Movimento: {len(res.movimento):,} linhas · compras: {len(res.compras):,} notas · "
          f"despesas: {len(res.despesas):,} lançamentos".replace(",", "."))
    if res.erros:
        print(f"\n  {len(res.erros)} ERRO(S) — estes arquivos não entraram:")
        for e in res.erros:
            print("   ✗", e)
    if res.avisos:
        print(f"\n  {len(res.avisos)} aviso(s):")
        for a in res.avisos:
            print("   !", a)
    print(f"\nBase gravada em {base.PASTA_BASE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
