"""Gera 12 meses de planilhas SIMULADAS da rede B2 Postos — para apresentação.

    python gerar_dados_simulados.py

Cria em `data/` uma pasta por posto (`b2_centro/`, `b2_bonsucesso/` ...) com
uma planilha por mês (`B2 Centro 09-2026.xlsx`), no MESMO formato que o posto
vai preencher de verdade; o `CADASTRO DOS POSTOS.xlsx` (tanques e
capacidades); e o modelo em branco em `modelo/`. Quando os dados reais
chegarem, apague as planilhas simuladas e ponha as reais nas mesmas pastas.

Os números seguem a lógica de um posto de verdade, para a apresentação contar
uma história coerente:

* **preço de bomba = custo da distribuidora + margem por litro**, arredondado
  para terminar em 9 (R$ 6,39); o custo muda em degraus, como nos reajustes;
* **etanol vende mais quando compensa** (abaixo de 70% do preço da gasolina:
  safra da cana, abr–set) e menos na entressafra;
* **o estoque é o do LMC**: inicial + compras − vendas = escritural; o final
  medido tem a evaporação normal (0,1% a 0,2% do vendido). O pedido sai quando
  o tanque cobre menos de ~2,5 dias, em cargas de 5.000 L, sem entrega aos
  domingos; o custo médio é o móvel ponderado das entregas;
* **despesas por categoria**: folha, energia, aluguel (Centro e Primavera),
  taxas de cartão proporcionais à venda, fretes, manutenções pontuais.

As situações plantadas para a apresentação — o motor de alertas acha todas:

1. **B2 Candói — Diesel S10 quase no fim.** A entrega da última semana
   atrasou em plena época de plantio.
2. **B2 Primavera — perda acima da tolerância** na Gasolina Comum desde
   agosto (~1% do vendido, contra 0,6%): vazamento, bomba descalibrada ou
   desvio — o tipo de coisa que só o LMC denuncia.
3. **B2 Primavera — guerra de preço.** Um concorrente abriu em junho; o posto
   cortou a margem da gasolina e cortou de novo em setembro.
4. **Aumento do diesel (15/09)** — +R$ 0,28/L na distribuidora. Quatro postos
   repassaram; o **B2 Bonsucesso** segurou o preço e a margem do diesel caiu.
5. **B2 Índio — perdendo volume**: obras na saída da BR-277 desde 08/09.
6. **B2 Bonsucesso cresce** mês a mês; **B2 Candói** tem a melhor margem por
   litro (menos concorrência); **B2 Centro** é o maior faturamento.

E as do controle de fraudes (tela 🛡️ Auditoria):

7. **B2 Primavera — venda apagada depois de enviada.** Em 22/09, o envio
   baixou a Gasolina Comum de 03/09 (−700 L) e 04/09 (−500 L), dias já
   recebidos: fica na trilha de auditoria (`data/auditoria.csv`) e vira
   alerta crítico. A régua não mudou, então a perda do LMC cresce junto.
8. **B2 Bonsucesso — carga sem nota**: uma entrega de Gasolina Comum em
   setembro entra no tanque sem nota na aba COMPRAS.
9. **B2 Índio — nota repetida**: uma nota de Etanol lançada de novo 2 dias
   depois.
Além disso, a Primavera manda a planilha em horário irregular (pontualidade
baixa no placar da reunião), e o exemplo `ALTERADA - B2 Primavera` mostra a
auditoria pegando a alteração AO VIVO no envio pelo painel.
"""
from __future__ import annotations

import math
import zlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src import planilhas as P

RAIZ = Path(__file__).resolve().parent
PASTA_DADOS = RAIZ / "data"
PASTA_MODELO = RAIZ / "modelo"

INICIO = date(2025, 10, 1)
FIM = date(2026, 9, 30)          # setembro FECHADO: o mês inteiro, para o ponto de equilíbrio e as comparações
# A B2 Primavera continua 3 dias atrás dos outros: a planilha dela vai só até 27/09.
# É a situação que a tela de Atualizações denuncia ("3 dias sem enviar") e que a cobrança de planilha usa.
FIM_POSTO = {"B2 Primavera": date(2026, 9, 27)}

# Quem envia a planilha de cada posto, e a que horas costuma enviar.
ENVIOS = {
    "B2 Centro": ("joao.centro", (8, 14), 1),        # manhã seguinte
    "B2 Bonsucesso": ("carlos.bonsucesso", (7, 52), 1),
    "B2 Primavera": ("marcos.primavera", (17, 31), 1),
    "B2 Índio": ("paulo.indio", (8, 32), 1),
    "B2 Candói": ("ana.candoi", (18, 42), 0),         # fim do próprio dia
}

rng = np.random.default_rng(2026)

C, A, E, D = P.PRODUTOS          # Comum, Aditivada, Etanol, Diesel

# ----------------------------------------------------------------- postos ---
POSTOS = {
    "B2 Centro": {
        "pasta": "b2_centro", "cidade": "Guarapuava", "bairro": "Centro",
        "perfil": "Urbano, maior fluxo da rede",
        "volume_dia": 15_200,
        "mix": {C: .42, A: .20, E: .22, D: .16},
        "tanques": {C: 60_000, A: 30_000, E: 45_000, D: 30_000},
        "margem_extra": {C: .06, A: .06, E: .06, D: .06},
        "folha": 106_000, "aluguel": 38_000, "energia": 13_200, "agua": 1_900,
        "sistemas": 4_300, "marketing": 4_200, "outras": 5_200, "manutencao": 6_000,
        "cartao": .76, "frete": 0.0,
    },
    "B2 Bonsucesso": {
        "pasta": "b2_bonsucesso", "cidade": "Guarapuava", "bairro": "Bonsucesso",
        "perfil": "Bairro residencial em expansão",
        "volume_dia": 11_600,
        "mix": {C: .45, A: .12, E: .23, D: .20},
        "tanques": {C: 60_000, A: 20_000, E: 30_000, D: 30_000},
        "margem_extra": {C: .0, A: .0, E: .0, D: .0},
        "folha": 88_000, "aluguel": 0, "energia": 10_100, "agua": 1_400,
        "sistemas": 3_600, "marketing": 2_000, "outras": 4_000, "manutencao": 5_000,
        "cartao": .72, "frete": 0.0,
    },
    "B2 Primavera": {
        "pasta": "b2_primavera", "cidade": "Guarapuava", "bairro": "Primavera",
        "perfil": "Bairro, concorrência forte desde junho",
        "volume_dia": 11_100,
        "mix": {C: .44, A: .12, E: .28, D: .16},
        "tanques": {C: 60_000, A: 15_000, E: 45_000, D: 20_000},
        "margem_extra": {C: .02, A: .02, E: .02, D: .02},
        "folha": 78_000, "aluguel": 14_000, "energia": 9_000, "agua": 1_200,
        "sistemas": 3_600, "marketing": 1_600, "outras": 4_000, "manutencao": 5_000,
        "cartao": .74, "frete": 0.0,
    },
    "B2 Índio": {
        "pasta": "b2_indio", "cidade": "Guarapuava", "bairro": "Vila Índio (saída BR-277)",
        "perfil": "Entrada da cidade, fluxo de caminhões",
        "volume_dia": 10_200,
        "mix": {C: .40, A: .12, E: .22, D: .26},
        "tanques": {C: 45_000, A: 15_000, E: 30_000, D: 45_000},
        "margem_extra": {C: .02, A: .02, E: .02, D: -.02},
        "folha": 70_000, "aluguel": 0, "energia": 9_500, "agua": 2_000,
        "sistemas": 3_900, "marketing": 1_500, "outras": 4_000, "manutencao": 5_000,
        "cartao": .64, "frete": 0.0,
    },
    "B2 Candói": {
        "pasta": "b2_candoi", "cidade": "Candói", "bairro": "Centro",
        "perfil": "Cidade do agronegócio, forte em diesel",
        "volume_dia": 12_100,
        "mix": {C: .30, A: .08, E: .10, D: .52},
        "tanques": {C: 45_000, A: 15_000, E: 15_000, D: 90_000},
        "margem_extra": {C: .11, A: .11, E: .11, D: .11},
        "folha": 78_000, "aluguel": 0, "energia": 8_200, "agua": 1_000,
        "sistemas": 3_200, "marketing": 1_000, "outras": 3_500, "manutencao": 4_500,
        "cartao": .58, "frete": .022,          # R$/L comprado: fica longe da base
    },
}

MARGEM_BASE = {C: .62, A: .84, E: .50, D: .50}      # R$/L sobre o custo

# Custo da distribuidora (R$/L, com impostos) — degraus nas datas de reajuste.
REAJUSTES = {
    C: [(date(2025, 10, 1), 5.62), (date(2025, 11, 20), 5.66), (date(2026, 1, 1), 5.68),
        (date(2026, 2, 1), 5.78), (date(2026, 4, 15), 5.72), (date(2026, 7, 8), 5.81),
        (date(2026, 9, 2), 5.76)],
    E: [(date(2025, 10, 1), 3.95), (date(2025, 11, 3), 4.02), (date(2025, 12, 1), 4.08),
        (date(2026, 1, 5), 4.12), (date(2026, 2, 3), 4.20), (date(2026, 3, 2), 4.26),
        (date(2026, 4, 13), 4.02), (date(2026, 5, 4), 3.90), (date(2026, 6, 1), 3.84),
        (date(2026, 7, 6), 3.86), (date(2026, 8, 3), 3.93), (date(2026, 9, 1), 3.99)],
    D: [(date(2025, 10, 1), 5.88), (date(2025, 12, 10), 5.84), (date(2026, 1, 1), 5.82),
        (date(2026, 3, 10), 5.90), (date(2026, 5, 20), 5.78), (date(2026, 8, 5), 5.83),
        (date(2026, 9, 15), 6.11)],                      # o aumento do diesel
}
REAJUSTES[A] = [(d, v + 0.14) for d, v in REAJUSTES[C]]

DISTRIBUIDORAS = {"Distribuidora Alfa": 0.0, "Distribuidora Sul": 0.015, "Distribuidora Paraná": -0.01}

FATOR_SEMANA = [0.97, 0.95, 0.98, 1.02, 1.16, 1.08, 0.80]         # seg..dom
FATOR_MES = {10: 1.0, 11: .99, 12: 1.09, 1: 1.04, 2: .95, 3: .99, 4: .98, 5: 1.0,
             6: .98, 7: 1.03, 8: 1.0, 9: 1.01}
# Plantio e colheita puxam o diesel em Candói.
SAFRA_CANDOI = {10: 1.22, 11: 1.10, 12: .95, 1: .90, 2: 1.25, 3: 1.30, 4: 1.05, 5: .95,
                6: 1.10, 7: 1.15, 8: .95, 9: 1.20}

GUERRA_PRIMAVERA = [(date(2026, 6, 1), {C: -.22, A: -.15, E: -.10, D: 0.0}),
                    (date(2026, 9, 8), {C: -.30, A: -.15, E: -.10, D: 0.0})]
INICIO_PERDA_PRIMAVERA = date(2026, 8, 8)
DIESEL_SEGURADO_BONSUCESSO = date(2026, 9, 15)       # não repassou o aumento
OBRAS_INDIO = date(2026, 9, 8)
# (data a partir da qual a entrega atrasa, litros da carga parcial que chegou)
ATRASO_ENTREGA = {("B2 Candói", D): (date(2026, 9, 22), 40_000)}

# Controle de fraudes — o que a 🛡️ Auditoria acha na demonstração.
# Primavera: venda de Gasolina Comum de dias antigos baixada DEPOIS de enviada,
# no envio com os dados até 21/09 (litros a menos por dia).
VENDA_BAIXADA_PRIMAVERA = {date(2026, 9, 3): 700, date(2026, 9, 4): 500}
ENVIO_DA_ALTERACAO = date(2026, 9, 21)
# Bonsucesso: a 1ª carga de Gasolina Comum a partir desta data entra sem nota.
CARGA_SEM_NOTA_BONSUCESSO = date(2026, 9, 10)
# Índio: a nota da 1ª carga de Etanol a partir desta data é lançada de novo 2 dias depois.
NOTA_REPETIDA_INDIO = date(2026, 9, 12)
# Bonsucesso: uma correção normal (dia recente), para a trilha não ser só suspeita.
CORRECAO_NORMAL_BONSUCESSO = (date(2026, 9, 25), E, 40)
# A Primavera manda a planilha em horário irregular: chance de mandar cedo.
CHANCE_CEDO_PRIMAVERA = .45


def custo_base(produto: str, dia: date) -> float:
    valor = REAJUSTES[produto][0][1]
    for inicio, v in REAJUSTES[produto]:
        if dia >= inicio:
            valor = v
    return valor


def margem_alvo(posto: str, produto: str, dia: date) -> float:
    margem = MARGEM_BASE[produto] + POSTOS[posto]["margem_extra"][produto]
    if posto == "B2 Primavera":
        cortes = [corte[produto] for inicio, corte in GUERRA_PRIMAVERA if dia >= inicio]
        if cortes:
            margem += cortes[-1]
    if posto == "B2 Bonsucesso" and produto == D and dia >= DIESEL_SEGURADO_BONSUCESSO:
        margem -= .22
    return margem


def preco_bomba(posto: str, produto: str, dia: date) -> float:
    bruto = custo_base(produto, dia) + margem_alvo(posto, produto, dia)
    return math.floor(bruto * 10) / 10 + 0.09          # termina em 9: R$ 6,39


def dias():
    d = INICIO
    while d <= FIM:
        yield d
        d += timedelta(days=1)


def meses():
    ano, mes = INICIO.year, INICIO.month
    while (ano, mes) <= (FIM.year, FIM.month):
        yield ano, mes
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)


# ------------------------------------------------------------- simulação ---
def simular_posto(nome: str) -> dict:
    # Sorteio próprio de cada posto: mexer num não muda os números dos outros.
    global rng
    rng = np.random.default_rng(zlib.crc32(nome.encode()))
    cfg = POSTOS[nome]
    movimento, compras = [], []
    estoque = {p: round(cfg["tanques"][p] * rng.uniform(.55, .75)) for p in P.PRODUTOS}
    valor_estoque = {p: estoque[p] * custo_base(p, INICIO) for p in P.PRODUTOS}
    pendente: dict[str, list] = {p: [] for p in P.PRODUTOS}
    historico = {p: [] for p in P.PRODUTOS}
    parcial_entregue = {p: False for p in P.PRODUTOS}
    nf = int(rng.integers(120_000, 380_000))
    n_mes = 0
    mes_anterior = INICIO.month

    for dia in dias():
        if dia.month != mes_anterior:
            n_mes += 1
            mes_anterior = dia.month
        total = (cfg["volume_dia"] * FATOR_SEMANA[dia.weekday()] * FATOR_MES[dia.month]
                 * float(np.exp(rng.normal(0, .06))))
        if nome == "B2 Bonsucesso":
            total *= 0.92 + 0.016 * n_mes                 # cresce mês a mês
        if nome == "B2 Índio" and dia >= OBRAS_INDIO:
            total *= 0.80
        precos = {p: preco_bomba(nome, p, dia) for p in P.PRODUTOS}
        razao = precos[E] / precos[C]                      # etanol compensa < 70%
        fator_etanol = float(np.clip(1 + (0.70 - razao) * 6, .6, 1.5))
        litros = {p: total * cfg["mix"][p] * float(np.exp(rng.normal(0, .05))) for p in P.PRODUTOS}
        base_etanol = litros[E]
        litros[E] *= fator_etanol
        litros[C] += (base_etanol - litros[E]) * .7
        if nome == "B2 Candói":
            litros[D] *= SAFRA_CANDOI[dia.month]
        if nome == "B2 Primavera" and dia >= GUERRA_PRIMAVERA[0][0]:
            litros[C] *= 1.04
        if nome == "B2 Bonsucesso" and dia >= DIESEL_SEGURADO_BONSUCESSO:
            litros[D] *= 1.06                               # atraiu quem fugiu do aumento

        for p in P.PRODUTOS:
            inicial = estoque[p]
            chegou = [x for x in pendente[p] if x[0] == dia]
            pendente[p] = [x for x in pendente[p] if x[0] != dia]
            recebido = 0
            for (_, qtd, custo, distrib) in chegou:
                nf += int(rng.integers(3, 40))
                compras.append([dia, p, qtd, round(custo, 4), round(qtd * custo, 2), nf, distrib])
                recebido += qtd
                valor_estoque[p] += qtd * custo
            disponivel = inicial + recebido
            custo_medio = valor_estoque[p] / disponivel if disponivel else custo_base(p, dia)

            vendido = int(round(litros[p]))
            vendido = max(0, min(vendido, disponivel - 150))     # nunca vende o que não tem
            perda_pct = rng.normal(.0012, .0009)                  # evaporação normal
            if nome == "B2 Primavera" and p == C and dia >= INICIO_PERDA_PRIMAVERA:
                perda_pct = rng.normal(.0102, .0012)
            final = disponivel - vendido - int(round(vendido * perda_pct))
            estoque[p] = final
            valor_estoque[p] = final * custo_medio

            preco_medio = round(precos[p] - rng.uniform(0, .012), 3)   # descontos de app/frota
            movimento.append([dia, p, inicial, recebido, vendido, final,
                              round(custo_medio, 4), preco_medio])
            historico[p].append(vendido)

            # Pedido à distribuidora.
            media = float(np.mean(historico[p][-7:]))
            cap = cfg["tanques"][p]
            if not pendente[p]:
                chegada = dia + timedelta(days=2 if rng.random() < .2 else 1)
                if chegada.weekday() == 6:
                    chegada += timedelta(days=1)
                prazo = (chegada - dia).days
                previsto = final - media * (prazo - 1)
                ponto = max(cap * .45, media * (prazo + 3.6))
                if previsto < ponto:
                    qtd = int((cap * .95 - previsto) // 5000 * 5000)
                    if qtd >= 5000:
                        atraso = ATRASO_ENTREGA.get((nome, p))
                        if atraso and chegada >= atraso[0]:
                            # A distribuidora mandou só uma carga parcial, e a
                            # entrega completa ficou para depois do fim.
                            if not parcial_entregue[p]:
                                qtd, parcial_entregue[p] = atraso[1], True
                            else:
                                chegada = FIM + timedelta(days=3)
                        distrib = str(rng.choice(list(DISTRIBUIDORAS)))
                        custo = custo_base(p, chegada) + DISTRIBUIDORAS[distrib] + rng.normal(0, .008)
                        pendente[p].append((chegada, qtd, custo, distrib))

    despesas = gerar_despesas(nome, movimento, compras)
    return {"movimento": movimento, "compras": compras, "despesas": despesas}


OUTRAS = ["Material de limpeza e escritório", "Uniformes e EPI", "Monitoramento e alarme",
          "Coleta de resíduos (óleo e borra)", "Seguro do posto", "Tarifas bancárias"]
MANUT = ["Manutenção preventiva das bombas", "Troca de filtros das bombas", "Reparo elétrico",
         "Manutenção do compressor de ar", "Limpeza da caixa separadora"]
EXTRAS = {
    ("B2 Centro", 2026, 3): ("Manutenção", "Pintura e reforma da cobertura", 16_400),
    ("B2 Índio", 2026, 7): ("Manutenção", "Troca de bomba medidora (diesel)", 19_800),
    ("B2 Primavera", 2026, 8): ("Manutenção", "Aferição das bombas — Inmetro", 4_250),
    ("B2 Candói", 2026, 6): ("Manutenção", "Reforma dos banheiros", 7_600),
    ("B2 Primavera", 2026, 6): ("Marketing", "Campanha contra a concorrência nova", 6_500),
    ("B2 Bonsucesso", 2025, 12): ("Manutenção", "Ampliação da pista de abastecimento", 22_000),
}


def gerar_despesas(nome: str, movimento: list, compras: list) -> list:
    cfg = POSTOS[nome]
    linhas = []

    def add(d: date, cat: str, desc: str, valor: float):
        if d <= FIM and valor > 0:
            linhas.append([d, cat, desc, round(valor, 2)])

    def r(v: float, sd: float = .03) -> float:
        return v * float(np.exp(rng.normal(0, sd)))

    for ano, mes in meses():
        verao = 1.08 if mes in (12, 1, 2, 3) else 1.0
        add(date(ano, mes, 5), "Folha de pagamento", "Salários do mês anterior", r(cfg["folha"] * .74, .01))
        add(date(ano, mes, 20), "Folha de pagamento", "Encargos (INSS e FGTS)", r(cfg["folha"] * .26, .01))
        if cfg["aluguel"]:
            add(date(ano, mes, 10), "Aluguel", "Aluguel do imóvel", cfg["aluguel"])
        add(date(ano, mes, 15), "Energia elétrica", "Conta de energia", r(cfg["energia"] * verao, .05))
        add(date(ano, mes, 12), "Água e esgoto", "Conta de água", r(cfg["agua"], .08))
        add(date(ano, mes, 10), "Sistemas e contabilidade", "Sistema de automação e contabilidade",
            cfg["sistemas"])
        marketing = cfg["marketing"] * (2.2 if nome == "B2 Primavera" and (ano, mes) >= (2026, 6) else 1)
        add(date(ano, mes, 15), "Marketing", "Placas, redes sociais e brindes", r(marketing, .1))
        for desc in rng.choice(OUTRAS, size=3, replace=False):
            add(date(ano, mes, int(rng.integers(3, 27))), "Outras despesas", str(desc),
                r(cfg["outras"] / 3, .25))
        for desc in rng.choice(MANUT, size=2, replace=False):
            add(date(ano, mes, int(rng.integers(2, 27))), "Manutenção", str(desc),
                r(cfg["manutencao"] / 2, .3))
        extra = EXTRAS.get((nome, ano, mes))
        if extra:
            add(date(ano, mes, 18), extra[0], extra[1], extra[2])
        if cfg["frete"]:
            litros_mes = sum(c[2] for c in compras if c[0].year == ano and c[0].month == mes)
            add(date(ano, mes, 25), "Fretes", "Frete das entregas de combustível",
                litros_mes * cfg["frete"])

    # Taxas de cartão: toda semana, sobre o que foi vendido no cartão.
    fat_dia: dict[date, float] = {}
    for dia, _p, _i, _c, vendido, _f, _custo, preco in movimento:
        fat_dia[dia] = fat_dia.get(dia, 0) + vendido * preco
    acumulado = 0.0
    for dia in sorted(fat_dia):
        acumulado += fat_dia[dia]
        if dia.weekday() == 6 or dia == FIM or (dia + timedelta(days=1)).day == 1:
            add(dia, "Taxas de cartão", "Taxas das maquininhas (semana)",
                acumulado * cfg["cartao"] * rng.uniform(.0108, .0122))
            acumulado = 0.0
    linhas.sort(key=lambda x: (x[0], x[1]))
    return linhas


# ------------------------------------------------------------------ Excel ---
NAVY = "041243"
LARANJA = "E4612A"
CINZA = "F3F5F9"


def _cabecalho(ws, colunas: list[str]):
    fonte = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    fundo = PatternFill("solid", fgColor=NAVY)
    borda = Border(bottom=Side(style="medium", color=LARANJA))
    for i, nome in enumerate(colunas, 1):
        c = ws.cell(row=1, column=i, value=nome)
        c.font, c.fill, c.border = fonte, fundo, borda
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = P.LARGURAS.get(nome, 16)
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"


def _aba(wb: Workbook, nome: str, linhas: list, zebra: bool = True):
    ws = wb.create_sheet(nome)
    colunas = P.COLUNAS[nome]
    _cabecalho(ws, colunas)
    fundo = PatternFill("solid", fgColor=CINZA)
    for r, linha in enumerate(linhas, 2):
        for c, valor in enumerate(linha, 1):
            cel = ws.cell(row=r, column=c, value=valor)
            fmt = P.FORMATOS.get(colunas[c - 1])
            if fmt:
                cel.number_format = fmt
            if zebra and r % 2 == 0:
                cel.fill = fundo
    ws.auto_filter.ref = f"A1:{get_column_letter(len(colunas))}{max(len(linhas), 1) + 1}"
    return ws


def _lista(ws, coluna: str, opcoes: list[str], ate: int = 2000):
    dv = DataValidation(type="list", formula1='"' + ",".join(opcoes) + '"', allow_blank=True,
                        showErrorMessage=True, errorTitle="Valor fora da lista",
                        error="Escolha um item da lista.")
    ws.add_data_validation(dv)
    dv.add(f"{coluna}2:{coluna}{ate}")


def _instrucoes(wb: Workbook, posto: str | None = None, mes: str | None = None):
    ws = wb.active
    ws.title = P.ABA_INSTRUCOES
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 110
    for r, (a, b) in enumerate(P.INSTRUCOES, 1):
        ws.cell(row=r, column=1, value=a).font = Font(bold=True, color=NAVY)
        ws.cell(row=r, column=2, value=b).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=1, column=1).font = Font(bold=True, size=14, color="FFFFFF")
    for c in (1, 2):
        ws.cell(row=1, column=c).fill = PatternFill("solid", fgColor=NAVY)
    if posto:
        ws.cell(row=2, column=1, value="Posto").font = Font(bold=True, color=LARANJA)
        ws.cell(row=2, column=2, value=f"{posto} — {mes}   ·   DADOS SIMULADOS PARA APRESENTAÇÃO")
    ws.sheet_view.showGridLines = False


def salvar_mes(posto: str, ano: int, mes: int, dados: dict, fim: date | None = None,
               destino: Path | None = None, sem_coluna: str | None = None):
    fim = fim or FIM_POSTO.get(posto, FIM)

    def do_mes(linhas):
        return [l for l in linhas if l[0].year == ano and l[0].month == mes and l[0] <= fim]

    wb = Workbook()
    _instrucoes(wb, posto, f"{mes:02d}/{ano}")
    ws = _aba(wb, P.ABA_MOVIMENTO, do_mes(dados["movimento"]))
    _lista(ws, "B", P.PRODUTOS)
    if sem_coluna:                      # exemplo com erro: some uma coluna obrigatória
        col = P.COLUNAS[P.ABA_MOVIMENTO].index(sem_coluna) + 1
        ws.delete_cols(col)
    ws = _aba(wb, P.ABA_COMPRAS, do_mes(dados["compras"]))
    _lista(ws, "B", P.PRODUTOS)
    ws = _aba(wb, P.ABA_DESPESAS, do_mes(dados["despesas"]))
    _lista(ws, "B", P.CATEGORIAS_DESPESA)
    if destino is None:
        destino = PASTA_DADOS / POSTOS[posto]["pasta"] / f"{posto} {mes:02d}-{ano}.xlsx"
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


PASTA_EXEMPLOS = RAIZ / "exemplos_para_envio"


def salvar_exemplos(dados_por_posto: dict):
    """Três planilhas para demonstrar o envio pelo painel:

    * a da B2 Primavera COMPLETA até 27/09 — o posto que estava atrasado
      "põe em dia": o alerta de dados desatualizados some na hora;
    * a da B2 Primavera ALTERADA — igual, mas com a venda de 08/09 e 09/09
      baixada: a conferência avisa, a auditoria registra e o alerta crítico
      aparece na Central (e no celular, no disparo "assim que chegar");
    * uma do B2 Candói COM ERRO (sem a coluna de custo médio e com estoque
      negativo) — a conferência recusa e o painel continua intacto.
    """
    PASTA_EXEMPLOS.mkdir(exist_ok=True)
    for antigo in PASTA_EXEMPLOS.glob("*.xlsx"):
        antigo.unlink()
    primavera = dados_por_posto["B2 Primavera"]
    salvar_mes("B2 Primavera", FIM.year, FIM.month, primavera, fim=FIM,
               destino=PASTA_EXEMPLOS / f"GERENCIAL_B2_PRIMAVERA_{FIM.month:02d}-{FIM.year}.xlsx")
    alterada = dict(primavera)
    alterada["movimento"] = [list(l) for l in primavera["movimento"]]
    for l in alterada["movimento"]:
        if l[1] == C and l[0] in (date(FIM.year, FIM.month, 8), date(FIM.year, FIM.month, 9)):
            l[4] -= 600 if l[0].day == 8 else 400
    salvar_mes("B2 Primavera", FIM.year, FIM.month, alterada, fim=FIM,
               destino=PASTA_EXEMPLOS / f"ALTERADA - B2 Primavera {FIM.month:02d}-{FIM.year}.xlsx")
    candoi = dados_por_posto["B2 Candói"]
    com_erro = dict(candoi)
    com_erro["movimento"] = [list(l) for l in candoi["movimento"]]
    for l in com_erro["movimento"]:
        if l[0] == date(FIM.year, FIM.month, 17) and l[1] == D:
            l[5] = -1_850                                   # estoque final negativo
    salvar_mes("B2 Candói", FIM.year, FIM.month, com_erro, fim=FIM, sem_coluna="Custo médio (R$/L)",
               destino=PASTA_EXEMPLOS / f"COM ERRO - B2 Candoi {FIM.month:02d}-{FIM.year}.xlsx")


def salvar_cadastro():
    wb = Workbook()
    ws = wb.active
    ws.title = "POSTOS"
    _cabecalho(ws, ["Pasta", "Posto", "Cidade", "Bairro", "Perfil"])
    for i, (nome, cfg) in enumerate(POSTOS.items(), 2):
        for j, v in enumerate([cfg["pasta"], nome, cfg["cidade"], cfg["bairro"], cfg["perfil"]], 1):
            ws.cell(row=i, column=j, value=v)
    ws.column_dimensions["D"].width = 28
    ws.column_dimensions["E"].width = 40
    ws2 = wb.create_sheet("TANQUES")
    _cabecalho(ws2, ["Posto", "Produto", "Capacidade (L)"])
    r = 2
    for nome, cfg in POSTOS.items():
        for p in P.PRODUTOS:
            ws2.cell(row=r, column=1, value=nome)
            ws2.cell(row=r, column=2, value=p)
            ws2.cell(row=r, column=3, value=cfg["tanques"][p]).number_format = "#,##0"
            r += 1
    PASTA_DADOS.mkdir(exist_ok=True)
    wb.save(PASTA_DADOS / "CADASTRO DOS POSTOS.xlsx")


def salvar_modelo():
    wb = Workbook()
    _instrucoes(wb)
    for aba in (P.ABA_MOVIMENTO, P.ABA_COMPRAS, P.ABA_DESPESAS):
        ws = _aba(wb, aba, [], zebra=False)
        _lista(ws, "B", P.CATEGORIAS_DESPESA if aba == P.ABA_DESPESAS else P.PRODUTOS)
        for r in range(2, 400):
            for c, nome in enumerate(P.COLUNAS[aba], 1):
                fmt = P.FORMATOS.get(nome)
                if fmt:
                    ws.cell(row=r, column=c).number_format = fmt
    PASTA_MODELO.mkdir(exist_ok=True)
    wb.save(PASTA_MODELO / "MODELO - Planilha Mensal do Posto.xlsx")


def simular_com_historia(posto: str) -> dict:
    """O diesel do Candói tem de terminar com ~1 dia de autonomia (a história
    do estoque crítico). Como o dia exato depende das entregas sorteadas,
    procura o tamanho da carga parcial que deixa o tanque nesse ponto."""
    if (posto, D) not in ATRASO_ENTREGA:
        return simular_posto(posto)
    melhor, distancia = None, 99.0
    data_atraso = ATRASO_ENTREGA[(posto, D)][0]
    for carga in range(5_000, 90_001, 2_500):
        ATRASO_ENTREGA[(posto, D)] = (data_atraso, carga)
        dados = simular_posto(posto)
        linhas = [l for l in dados["movimento"] if l[1] == D and l[0] > FIM - timedelta(days=7)]
        media = sum(l[4] for l in linhas) / len(linhas)
        autonomia = linhas[-1][5] / media if media else 0.0
        if abs(autonomia - 1.0) < distancia:
            melhor, distancia = dados, abs(autonomia - 1.0)
        if distancia < .25:
            break
    return melhor


def plantar_controle(posto: str, dados: dict) -> list[dict]:
    """As situações 7–9 (fraude). Devolve o que vai para a trilha de auditoria."""
    trilha = []
    if posto == "B2 Primavera":
        for l in dados["movimento"]:
            if l[1] == C and l[0] in VENDA_BAIXADA_PRIMAVERA:
                antes = l[4]
                l[4] -= VENDA_BAIXADA_PRIMAVERA[l[0]]      # a régua (estoque final) fica igual
                trilha.append({"posto": posto, "data": l[0], "produto": C, "campo": "Vendas", "antes": antes,
                               "depois": l[4], "diferenca": l[4] - antes,
                               "impacto_rs": round((l[4] - antes) * l[7], 2),
                               "dias_depois": (ENVIO_DA_ALTERACAO - l[0]).days, "gravidade": "critico"})
    if posto == "B2 Bonsucesso":
        carga = next(c for c in dados["compras"] if c[1] == C and c[0] >= CARGA_SEM_NOTA_BONSUCESSO)
        dados["compras"].remove(carga)
        dia, produto, a_mais = CORRECAO_NORMAL_BONSUCESSO
        l = next(l for l in dados["movimento"] if l[0] == dia and l[1] == produto)
        trilha.append({"posto": posto, "data": dia, "produto": produto, "campo": "Vendas", "antes": l[4] - a_mais,
                       "depois": l[4], "diferenca": a_mais, "impacto_rs": round(a_mais * l[7], 2),
                       "dias_depois": 0, "gravidade": "normal"})
    if posto == "B2 Índio":
        nota = next(c for c in dados["compras"] if c[1] == E and c[0] >= NOTA_REPETIDA_INDIO)
        dados["compras"].append([nota[0] + timedelta(days=2), *nota[1:]])
        dados["compras"].sort(key=lambda c: c[0])
    return trilha


def semear_auditoria(trilha: list[dict], envios: list[list]):
    """A trilha de auditoria da demonstração, registrada na hora do envio que
    trouxe cada alteração (o mesmo do histórico de envios)."""
    import pandas as pd

    from src import auditoria

    auditoria.ARQ_AUDITORIA.unlink(missing_ok=True)
    quem = {"B2 Primavera": ENVIO_DA_ALTERACAO, "B2 Bonsucesso": CORRECAO_NORMAL_BONSUCESSO[0] + timedelta(days=1)}
    for posto, ate in quem.items():
        mudancas = pd.DataFrame([t for t in trilha if t["posto"] == posto])
        envio = next(e for e in envios if e[1] == posto and e[7] == f"dados até {ate:%d/%m}")
        auditoria.registrar(mudancas, "Envio pelo painel", envio[3], quando=envio[0])


def semear_envios() -> list[list]:
    """Histórico de envios simulado: cada mês fechado enviado no 2º dia do mês
    seguinte e, em setembro, um envio por dia (cada um substitui o anterior)."""
    import csv
    from datetime import datetime

    linhas = []
    for posto, (login, (h, m), atraso) in ENVIOS.items():
        pasta = POSTOS[posto]["pasta"]
        fim = FIM_POSTO.get(posto, FIM)
        for ano, mes in meses():
            nome = f"{posto} {mes:02d}-{ano}.xlsx"
            if (ano, mes) != (FIM.year, FIM.month):
                prox = date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 2)
                quando = datetime(prox.year, prox.month, prox.day, h, m)
                linhas.append([quando, posto, pasta, login, f"{mes:02d}/{ano}", nome,
                               "Processado", f"mês fechado (até {prox - timedelta(days=2):%d/%m})"])
                continue
            d = date(ano, mes, 1)
            while d <= fim:
                envio = d + timedelta(days=atraso)
                hora = h
                if posto == "B2 Primavera" and d < fim:      # horário irregular
                    hora = 9 if rng.random() < CHANCE_CEDO_PRIMAVERA else int(rng.integers(15, 20))
                quando = datetime(envio.year, envio.month, envio.day, hora,
                                  int(rng.integers(0, 59)) if d < fim else m)
                resultado = "Processado" if d == fim else "Substituído"
                linhas.append([quando, posto, pasta, login, f"{mes:02d}/{ano}", nome, resultado,
                               f"dados até {d:%d/%m}"])
                d += timedelta(days=1)
    linhas.sort(key=lambda x: x[0])
    with open(PASTA_DADOS / "envios.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["data_hora", "posto", "pasta", "usuario", "periodo", "arquivo", "resultado", "detalhe"])
        for l in linhas:
            w.writerow([l[0].strftime("%Y-%m-%d %H:%M"), *l[1:]])
    return linhas


def salvar_descontos():
    """O desconto do boleto de cada distribuidora (R$/L): a diferença entre o preço PLANILHA e o preço SISTEMA.

    A Sul cobra mais caro na distribuidora (+R$ 0,015/L) e compensa com o maior desconto; o diesel da Alfa tem desconto
    próprio. É dado simulado: os valores reais vêm dos boletos.
    """
    from src import descontos
    descontos.gravar(descontos.pd.DataFrame(
        [("Distribuidora Alfa", descontos.TODOS, 0.06), ("Distribuidora Alfa", "Diesel S10", 0.08),
         ("Distribuidora Sul", descontos.TODOS, 0.09), ("Distribuidora Paraná", descontos.TODOS, 0.05)],
        columns=descontos.COLUNAS))


def main():
    print("Gerando 12 meses de planilhas simuladas da rede B2 Postos...")
    salvar_cadastro()
    salvar_modelo()
    salvar_descontos()
    # A base anterior sai: comparada com a nova, viraria alteração na auditoria.
    import shutil
    shutil.rmtree(PASTA_DADOS / "base", ignore_errors=True)
    todos, trilha = {}, []
    for posto, cfg in POSTOS.items():
        dados = simular_com_historia(posto)
        trilha += plantar_controle(posto, dados)
        todos[posto] = dados
        n = 0
        for ano, mes in meses():
            salvar_mes(posto, ano, mes, dados)
            n += 1
        fim = FIM_POSTO.get(posto, FIM)
        final = {l[1]: l[5] for l in dados["movimento"] if l[0] == fim}
        resumo = "  ".join(f"{p.split()[-1][:6]} {final[p] / cfg['tanques'][p]:.0%}" for p in P.PRODUTOS)
        print(f"  {posto:<14} {n} planilhas · tanques em {fim:%d/%m}: {resumo}")
    envios = semear_envios()
    semear_auditoria(trilha, envios)
    salvar_exemplos(todos)
    # Marca que a base é a da demonstração: os testes das histórias plantadas
    # só rodam com ela (com dados reais, eles não fazem sentido).
    (PASTA_DADOS / "SIMULADO.txt").write_text("Dados simulados para apresentação. Apague este "
                                             "arquivo quando os dados reais entrarem.\n", encoding="utf-8")
    (PASTA_DADOS / "alertas_enviados.csv").unlink(missing_ok=True)
    # Versões guardadas de envios de teste não fazem parte da demonstração.
    for pasta in PASTA_DADOS.glob("*/_versoes"):
        for v in pasta.glob("*.xlsx"):
            v.unlink()
    print(f"Pronto. Planilhas em {PASTA_DADOS}")
    print(f"Exemplos para testar o envio pelo painel em {PASTA_EXEMPLOS}")
    print("Agora rode o 'Atualizar Dados.bat' (ou: python gerar_base.py) para montar a base do painel.")


if __name__ == "__main__":
    main()
