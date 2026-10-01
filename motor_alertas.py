"""Motor de alertas — roda SEM o painel aberto e manda para o celular.

    python motor_alertas.py            # envia os alertas novos
    python motor_alertas.py --listar   # só mostra, não envia nada
    python motor_alertas.py --teste    # manda uma notificação de teste
    python motor_alertas.py --chegada  # disparos "assim que chegar" do B2 Assistente

Roda sozinho no fim do `Atualizar Dados.bat` e, publicado, no GitHub Actions
depois de cada planilha recebida. O dono não precisa estar com o painel
aberto para saber que o diesel do Candói está acabando.

**Não repete alerta.** Cada alerta tem uma chave (tipo, posto, produto, data
dos dados); o que já foi enviado fica em `data/alertas_enviados.csv` e não
volta a tocar o celular. Se a situação continuar no dia seguinte, a data
muda e ele avisa de novo — uma vez por dia, não a cada planilha.

As regras são as MESMAS do painel (`src/alertas.py`): o celular nunca mostra
um alerta que a Central não mostra.

`--chegada`: publicado, a planilha nova chega pelo GitHub e o commit da base
reinicia o app da nuvem — o agendador que roda dentro do painel não vê a
chegada. Então o Actions manda, ele mesmo, os disparos de "assim que os dados
chegarem" da agenda do B2 Assistente (Telegram, para todas as conversas).
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from src import alertas as al
from src import analytics as an
from src import auditoria, base
from src import notificacoes as notif

RAIZ = Path(__file__).resolve().parent
# Em data/, e não em logs/: publicado, o arquivo vai para o repositório junto
# com a base — sem isso o GitHub Actions reenviaria tudo a cada planilha.
ARQ_ENVIADOS = RAIZ / "data" / "alertas_enviados.csv"


def ja_enviados() -> set[str]:
    if not ARQ_ENVIADOS.exists():
        return set()
    with open(ARQ_ENVIADOS, encoding="utf-8") as f:
        return {linha["chave"] for linha in csv.DictReader(f, delimiter=";")}


def anotar(alerta: al.Alerta, canal: str, retorno: str):
    ARQ_ENVIADOS.parent.mkdir(exist_ok=True)
    novo = not ARQ_ENVIADOS.exists()
    with open(ARQ_ENVIADOS, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["enviado_em", "chave", "nivel", "posto", "titulo", "resumo", "canal", "retorno"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), alerta.chave, alerta.nivel, alerta.posto,
                    alerta.titulo, alerta.resumo, canal, retorno])


def gerar() -> list[al.Alerta]:
    b = base.carregar()
    df = an.preparar(b.movimento)
    return al.gerar(df, b.tanques, b.postos["posto"].tolist(), auditoria=auditoria.ler())


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listar", action="store_true", help="só mostra os alertas, não envia")
    ap.add_argument("--teste", action="store_true", help="envia uma notificação de teste")
    ap.add_argument("--chegada", action="store_true", help="disparos 'assim que chegar' do B2 Assistente")
    args = ap.parse_args()

    if args.chegada:
        from src import assistente_agenda
        for linha in assistente_agenda.disparar_chegada_fora_do_painel():
            print(linha)
        return 0

    cfg = notif.config()
    canal, pronto, motivo = notif.canal_pronto(cfg)
    url = cfg["envio"].get("url_painel", "")
    print(f"Canal de envio: {canal} ({motivo})")

    if args.teste:
        ok, ret = notif.enviar_alerta("✅ B2 Gestão — teste", "Se você está lendo isto no celular, "
                                      "os alertas da rede vão chegar aqui.", url, "destaque", cfg)
        print("Teste:", "enviado" if ok else "NÃO enviado", "—", ret)
        return 0 if ok else 1

    alertas = gerar()
    niveis = set(cfg["envio"].get("niveis", ["critico", "atencao"]))
    enviados = ja_enviados()
    novos = [a for a in alertas if a.nivel in niveis and a.chave not in enviados]
    print(f"{len(alertas)} alerta(s) na rede · {len(novos)} novo(s) para enviar "
          f"(níveis: {', '.join(sorted(niveis))})\n")
    for a in alertas:
        marca = "→" if a in novos else " "
        print(f" {marca} {a.icone} {a.titulo} — {a.posto}: {a.resumo}")
    if args.listar or not novos:
        return 0
    print()
    for a in novos:
        ok, ret = notif.enviar_alerta(f"{a.icone} {a.titulo.capitalize()} — {a.posto}",
                                      a.texto_celular(), url, a.nivel, cfg)
        if ok:
            anotar(a, canal, ret)
        print(f"   {'✓' if ok else '✗'} {a.posto}: {ret}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
