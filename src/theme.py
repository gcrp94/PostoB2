"""Design system do painel B2 Postos — fonte única de verdade para cores.

As cores da marca saíram da própria logo (LOGO.jfif), medidas pixel a pixel:
o fundo azul-marinho é #041243 e a faixa laranja fica entre #d56229 e #e55c2e.

As cores dos COMBUSTÍVEIS foram validadas pelo validador de paleta da skill
de visualização (daltonismo e contraste, todos os pares): pior separação para
daltônicos ΔE 9,2 e para visão normal ΔE 16,3 — passa. O etanol fica abaixo
de 3:1 de contraste sobre o branco, e por isso todo gráfico com combustível
tem legenda e tabela ao lado (nunca a cor sozinha).

**Cor segue o combustível, nunca a posição.** Etanol é sempre verde-água,
Diesel S10 sempre violeta — em todo gráfico, em qualquer filtro.
"""

COLORS = {
    # Marca
    "navy": "#041243",          # fundo da logo
    "navy_2": "#0b1f63",        # degradê do cabeçalho
    "navy_ui": "#1d3278",       # barras e realces sobre fundo claro
    "orange": "#e4612a",        # faixa laranja da logo
    "orange_soft": "#fdebe2",
    # Superfícies e texto
    "bg": "#f3f5f9",
    "surface": "#ffffff",
    "border": "#e2e6ef",
    "grid": "#edf0f5",
    "text_primary": "#0f1b3d",
    "text_secondary": "#5a6683",
    "text_muted": "#8a93a8",
    "neutral_bar": "#b8c0d2",
    # Estado (reservadas: nunca usadas como cor de série)
    "ok": "#12813a",
    "ok_soft": "#e6f4ea",
    "atencao": "#a05f0a",
    "atencao_soft": "#fdf3dc",
    "critico": "#c53030",
    "critico_soft": "#fbe9e9",
}

FONTE_FAMILIA = "Inter, 'Segoe UI', system-ui, -apple-system, Arial, sans-serif"

# Ordem fixa dos combustíveis — é a ordem das pilhas, das legendas e das tabelas.
COMBUSTIVEIS = ["Gasolina Comum", "Gasolina Aditivada", "Etanol", "Diesel S10"]

CORES_COMBUSTIVEL = {
    "Gasolina Comum": "#eb6834",
    "Gasolina Aditivada": "#2a78d6",
    "Etanol": "#1baf7a",
    "Diesel S10": "#4a3aa7",
}

# A mesma identificação em toda tela: ícone + nome + cor.
ICONES_COMBUSTIVEL = {
    "Gasolina Comum": "⛽",
    "Gasolina Aditivada": "⛽",
    "Etanol": "🌱",
    "Diesel S10": "🚛",
}

# Rótulo curto para legenda de gráfico estreito (celular).
ROTULO_CURTO = {
    "Gasolina Comum": "Gas. Comum",
    "Gasolina Aditivada": "Gas. Aditivada",
    "Etanol": "Etanol",
    "Diesel S10": "Diesel S10",
}

POSTOS = ["B2 Centro", "B2 Bonsucesso", "B2 Primavera", "B2 Índio", "B2 Candói"]

# Situação: cor + ícone + palavra, sempre os três juntos.
STATUS = {
    "ok": {"cor": COLORS["ok"], "fundo": COLORS["ok_soft"], "icone": "●", "rotulo": "Normal"},
    "atencao": {"cor": COLORS["atencao"], "fundo": COLORS["atencao_soft"], "icone": "▲", "rotulo": "Atenção"},
    "critico": {"cor": COLORS["critico"], "fundo": COLORS["critico_soft"], "icone": "■", "rotulo": "Crítico"},
}


def css_root_variables() -> str:
    """`:root { --navy: ...; }` a partir de COLORS — o CSS só usa var(--nome)."""
    linhas = [f"  --{k.replace('_', '-')}: {v};" for k, v in COLORS.items()]
    linhas += [f"  --comb-{i}: {CORES_COMBUSTIVEL[c]};" for i, c in enumerate(COMBUSTIVEIS, 1)]
    return ":root {\n" + "\n".join(linhas) + "\n}"
