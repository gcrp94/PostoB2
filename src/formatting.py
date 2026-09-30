"""Números no padrão brasileiro — nunca formate valor para a tela fora daqui.

Herdado do Painel de Finanças, com as mesmas regras aprendidas lá: vírgula
decimal, ponto de milhar, zero sem sinal, NaN vira travessão.
"""


def _milhar(texto: str) -> str:
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def format_brl(value: float | None, casas: int = 2) -> str:
    """R$ 1.234.567,89"""
    if value is None:
        return "R$ 0,00"
    if value != value:
        return "—"
    sinal = "-" if value < 0 else ""
    return f"{sinal}R$ {_milhar(f'{abs(value):,.{casas}f}')}"


def format_brl_curto(value: float | None) -> str:
    """R$ 2,34 mi / R$ 45,2 mil — para rótulo de gráfico e cartão compacto."""
    if value is None or value != value:
        return "—"
    sinal = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1_000_000:
        return f"{sinal}R$ {_milhar(f'{v / 1_000_000:,.2f}')} mi"
    if v >= 1_000:
        return f"{sinal}R$ {_milhar(f'{v / 1_000:,.1f}')} mil"
    return format_brl(value)


def format_int(value: float | int | None) -> str:
    """18.304"""
    if value is None or value != value:
        return "—"
    return f"{int(round(value)):,}".replace(",", ".")


def format_litros(value: float | None) -> str:
    """12.345 L"""
    if value is None or value != value:
        return "—"
    return f"{format_int(value)} L"


def format_litros_curto(value: float | None) -> str:
    """388,4 mil L / 1,21 mi L"""
    if value is None or value != value:
        return "—"
    v = abs(value)
    sinal = "-" if value < 0 else ""
    if v >= 1_000_000:
        return f"{sinal}{_milhar(f'{v / 1_000_000:,.2f}')} mi L"
    if v >= 10_000:
        return f"{sinal}{_milhar(f'{v / 1_000:,.1f}')} mil L"
    return format_litros(value)


def format_rs_litro(value: float | None, casas: int = 2) -> str:
    """R$ 0,62/L"""
    if value is None or value != value:
        return "—"
    return f"{format_brl(value, casas)}/L"


def format_pct(value: float | None, casas: int = 1) -> str:
    """Variação com sinal: +12,3% / -5,7%. Zero sai sem sinal."""
    if value is None or value != value:
        return "—"
    if round(value, casas) == 0:
        return f"0,{'0' * casas}%" if casas else "0%"
    sinal = "+" if value > 0 else ""
    return f"{sinal}{value:.{casas}f}".replace(".", ",") + "%"


def format_pct_simples(value: float | None, casas: int = 1) -> str:
    """Participação/margem SEM o "+": 12,3%"""
    if value is None or value != value:
        return "—"
    return f"{value:.{casas}f}".replace(".", ",") + "%"


def format_pp(value: float | None, casas: int = 1) -> str:
    """Pontos percentuais com sinal: +0,4 p.p."""
    if value is None or value != value:
        return "—"
    if round(value, casas) == 0:
        return f"0,{'0' * casas} p.p."
    sinal = "+" if value > 0 else ""
    return f"{sinal}{value:.{casas}f}".replace(".", ",") + " p.p."


def format_decimal(value: float | None, casas: int = 1) -> str:
    """6,0"""
    if value is None or value != value:
        return "—"
    return _milhar(f"{value:,.{casas}f}")


def variacao_pct(atual: float, anterior: float) -> float | None:
    """Variação percentual; None quando não há base para comparar."""
    if not anterior or anterior != anterior or anterior <= 0:
        return None
    return (atual - anterior) / anterior * 100


MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def nome_mes(mes: int, ano: int | None = None, curto: bool = False) -> str:
    nome = (MESES_CURTOS if curto else MESES)[mes - 1]
    if ano is None:
        return nome
    return f"{nome}/{str(ano)[2:]}" if curto else f"{nome}/{ano}"
