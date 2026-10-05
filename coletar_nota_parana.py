"""Coleta o retrato diário do Menor Preço (Nota Paraná). TESTE LOCAL — nada disso vai ao Git.

    python coletar_nota_parana.py              # a coleta do dia (no máximo uma por dia)
    python coletar_nota_parana.py --varredura  # força a varredura da cidade em grade (16 pontos)
    python coletar_nota_parana.py --forcar     # coleta mesmo que já tenha coletado hoje
    python coletar_nota_parana.py --status     # só mostra o que já foi coletado

No dia a dia: uma consulta larga a partir do centro, 4 a 8 consultas com pausa de 8 a 20 s
entre elas (~2 minutos). Na 1ª vez e uma vez por mês, a varredura em grade (uns 15 minutos),
para achar posto novo na periferia. Ao primeiro sinal de bloqueio ela para e não insiste.
Veja `src/nota_parana.py`.
Para rodar todo dia, agende o "Coletar Menor Preco.bat" no Agendador de Tarefas do Windows.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from src import nota_parana as np_


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--forcar", action="store_true", help="ignora a trava de uma coleta por dia")
    ap.add_argument("--varredura", action="store_true", help="varre a cidade inteira em grade, mesmo fora do mês")
    ap.add_argument("--status", action="store_true", help="só mostra o que já foi coletado")
    args = ap.parse_args()

    if args.status:
        e = np_.estado(np_.carregar())
        print(f"{e['ofertas']} ofertas em {e['dias']} dia(s) · última coleta: {e['ultima'] or 'nenhuma'}")
        if e["interrompida"]:
            print(f"Última tentativa foi interrompida: {e['interrompida']['mensagem']}")
        return 0

    agora = datetime.now()
    if not args.forcar and np_.ja_coletou_hoje(agora):
        print("Já coletei hoje (uma por dia basta). Use --forcar se precisar mesmo.")
        return 0

    completa = args.varredura or np_.precisa_varredura_completa(agora)
    print(f"Coletando o Menor Preço — {'varredura da cidade em grade' if completa else 'ponto central'} "
          "(consultas espaçadas, como uma pessoa)...")
    resultado = np_.coletar(np_.CENTROS, avisar=print, modo="completa") if completa else np_.coletar(avisar=print)
    novas = np_.gravar(resultado.linhas) if len(resultado.linhas) else 0
    np_.anotar(resultado, novas, agora)
    print(f"{resultado.consultas} consulta(s) · {len(resultado.linhas)} ofertas de {resultado.linhas['loja'].nunique()} postos · "
          f"{novas} novas · {resultado.extras_de_paginacao} posto(s) só na 2ª página · gravado em {np_.PASTA}")
    if resultado.status != "ok":
        print(f"\nCOLETA INTERROMPIDA: {resultado.mensagem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
