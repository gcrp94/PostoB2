"""B2 Assistente pelo WhatsApp (sessão logada, TESTE com chip dedicado). Veja `src/assistente_whatsapp.py`.

    python whatsapp_assistente.py                      # liga o robô (1ª vez: mostra o QR para parear)
    python whatsapp_assistente.py --autorizar 42999999999 --nome "Gustavo"   # libera um número
    python whatsapp_assistente.py --remover 42999999999
    python whatsapp_assistente.py --listar             # quem está autorizado

O robô só responde a quem está na lista e só com dados simulados. Pare com Ctrl+C.
"""
from __future__ import annotations

import argparse
import sys
import webbrowser

from src import assistente_whatsapp as wa


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--autorizar", metavar="NUMERO", help="libera um número (DDD + número) a conversar com o robô")
    ap.add_argument("--nome", default="", help="nome para lembrar de quem é o número")
    ap.add_argument("--remover", metavar="NUMERO", help="tira um número da lista")
    ap.add_argument("--listar", action="store_true", help="mostra quem está autorizado")
    ap.add_argument("--abrir", action="store_true", help="abre a página do QR no navegador")
    args = ap.parse_args()

    if args.autorizar:
        try:
            n = wa.autorizar(args.autorizar, args.nome)
        except ValueError as erro:
            print(erro)
            return 1
        print(f"Autorizado: {wa.mascarar(n)}" + (f" ({args.nome})" if args.nome else ""))
        return 0
    if args.remover:
        print("Removido." if wa.remover(args.remover) else "Esse número não estava na lista.")
        return 0
    if args.listar:
        cfg = wa.ler_config()
        if not cfg["autorizados"]:
            print("Ninguém autorizado ainda. Use --autorizar NUMERO.")
        for n in cfg["autorizados"]:
            print(f"  {wa.mascarar(n)}  {cfg['nomes'].get(n, '')}")
        return 0

    if not wa.ler_config()["autorizados"]:
        print("Atenção: ninguém está autorizado, então o robô não vai responder a ninguém.\n"
              "         Libere o seu número com:  python whatsapp_assistente.py --autorizar 42999999999\n")
    servico = wa.ServicoWhatsApp(wa.Roteador(wa.responder_padrao(), lambda: wa.ler_config()["autorizados"]))
    servidor = wa.servir_pagina_qr(servico)
    url = f"http://127.0.0.1:{wa.PORTA_QR}/"
    print(f"Página do QR e da situação: {url}")
    if args.abrir:
        webbrowser.open(url)
    print("Conectando ao WhatsApp... (Ctrl+C para parar)")
    try:
        servico.rodar()
    finally:
        servidor.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
