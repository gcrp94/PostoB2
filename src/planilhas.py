"""O formato das planilhas — o contrato entre o posto e o painel.

Cada posto entrega UMA planilha por mês. A aba principal é o MOVIMENTO
DIÁRIO: uma linha por dia e por combustível, com a conta do LMC que o posto
já faz por obrigação (estoque inicial + compras − vendas = estoque final) e os
dois preços que formam a margem (custo médio e preço médio de venda). O
sistema calcula o resto sozinho: faturamento, margem, perda/sobra, autonomia.

As abas COMPRAS (notas das distribuidoras) e DESPESAS são opcionais: sem
elas o painel funciona, só não mostra a comparação entre distribuidoras e o
resultado depois das despesas.

O gerador de dados simulados, o modelo em branco e o ETL usam as definições
daqui — mudou o nome de uma coluna, muda aqui e os três acompanham.
"""
from __future__ import annotations

ABA_MOVIMENTO = "MOVIMENTO DIÁRIO"
ABA_COMPRAS = "COMPRAS"
ABA_DESPESAS = "DESPESAS"
ABA_INSTRUCOES = "INSTRUÇÕES"

ABAS_OBRIGATORIAS = [ABA_MOVIMENTO]
ABAS_OPCIONAIS = [ABA_COMPRAS, ABA_DESPESAS]

COLUNAS = {
    ABA_MOVIMENTO: ["Data", "Produto", "Estoque inicial (L)", "Compras (L)", "Vendas (L)",
                    "Estoque final (L)", "Custo médio (R$/L)", "Preço médio (R$/L)"],
    ABA_COMPRAS: ["Data", "Produto", "Litros", "Custo (R$/L)", "Valor da nota (R$)",
                  "Nota fiscal", "Distribuidora"],
    ABA_DESPESAS: ["Data", "Categoria", "Descrição", "Valor (R$)"],
}

# Nome da coluna no Excel -> nome interno na base.
RENOMEAR = {
    ABA_MOVIMENTO: {
        "Data": "data", "Produto": "produto", "Estoque inicial (L)": "estoque_inicial",
        "Compras (L)": "compras_l", "Vendas (L)": "vendas_l", "Estoque final (L)": "estoque_final",
        "Custo médio (R$/L)": "custo_medio", "Preço médio (R$/L)": "preco_medio",
    },
    ABA_COMPRAS: {
        "Data": "data", "Produto": "produto", "Litros": "litros", "Custo (R$/L)": "custo",
        "Valor da nota (R$)": "valor", "Nota fiscal": "nota_fiscal", "Distribuidora": "distribuidora",
    },
    ABA_DESPESAS: {
        "Data": "data", "Categoria": "categoria", "Descrição": "descricao", "Valor (R$)": "valor",
    },
}

FORMATOS = {
    "Data": "DD/MM/YYYY",
    "Estoque inicial (L)": "#,##0",
    "Compras (L)": "#,##0",
    "Vendas (L)": "#,##0",
    "Estoque final (L)": "#,##0",
    "Custo médio (R$/L)": '"R$" #,##0.0000',
    "Preço médio (R$/L)": '"R$" #,##0.000',
    "Litros": "#,##0",
    "Custo (R$/L)": '"R$" #,##0.0000',
    "Valor da nota (R$)": '"R$" #,##0.00',
    "Valor (R$)": '"R$" #,##0.00',
}

LARGURAS = {
    "Data": 12, "Produto": 20, "Categoria": 26, "Descrição": 40, "Distribuidora": 22,
    "Nota fiscal": 13,
}

PRODUTOS = ["Gasolina Comum", "Gasolina Aditivada", "Etanol", "Diesel S10"]

# Grafias que aparecem nos sistemas dos postos -> nome oficial.
SINONIMOS_PRODUTO = {
    "gasolina comum": "Gasolina Comum", "gasolina c": "Gasolina Comum", "gc": "Gasolina Comum",
    "gasolina": "Gasolina Comum",
    "gasolina aditivada": "Gasolina Aditivada", "aditivada": "Gasolina Aditivada",
    "gasolina adit": "Gasolina Aditivada", "ga": "Gasolina Aditivada",
    "etanol": "Etanol", "etanol hidratado": "Etanol", "alcool": "Etanol", "álcool": "Etanol",
    "diesel s10": "Diesel S10", "diesel s-10": "Diesel S10", "s10": "Diesel S10",
    "s-10": "Diesel S10", "oleo diesel s10": "Diesel S10", "óleo diesel s10": "Diesel S10",
}

CATEGORIAS_DESPESA = [
    "Folha de pagamento",
    "Aluguel",
    "Energia elétrica",
    "Água e esgoto",
    "Taxas de cartão",
    "Manutenção",
    "Fretes",
    "Sistemas e contabilidade",
    "Marketing",
    "Outras despesas",
]

INSTRUCOES = [
    ("PLANILHA MENSAL DO POSTO — REDE B2 POSTOS", ""),
    ("", ""),
    ("Nome do arquivo", "<Nome do posto> MM-AAAA.xlsx   (ex.: B2 Centro 09-2026.xlsx)"),
    ("Onde salvar", "Na pasta do posto:  data\\b2_centro\\,  data\\b2_bonsucesso\\ ..."),
    ("", ""),
    ("MOVIMENTO DIÁRIO", "Obrigatória. Uma linha por dia e por combustível — a mesma conta do "
                         "LMC: estoque inicial + compras − vendas = estoque final (a medição da "
                         "régua). Custo médio é o custo do litro em estoque; preço médio é o "
                         "preço de venda do dia (encerrantes ÷ litros)."),
    ("COMPRAS", "Opcional. Uma linha por nota fiscal da distribuidora — permite comparar "
                "distribuidoras e acompanhar o custo de cada entrega."),
    ("DESPESAS", "Opcional. As despesas do posto no mês, com a categoria da lista. Com elas o "
                 "painel mostra o resultado depois das despesas; sem elas, só a margem bruta."),
    ("", ""),
    ("O painel calcula", "Faturamento, margem bruta (R$, % e por litro), perda/sobra do LMC, "
                         "estoque, autonomia em dias e os alertas."),
    ("Produtos aceitos", " · ".join(PRODUTOS)),
    ("Categorias de despesa", " · ".join(CATEGORIAS_DESPESA)),
    ("", ""),
    ("Importante", "Não mude o nome das abas nem das colunas. Não deixe linhas de total no "
                   "meio dos dados — o painel soma sozinho."),
]
