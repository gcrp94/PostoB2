"""O "Painel novo": só aparência. Aqui, o que não pode quebrar sem ninguém ver."""
from __future__ import annotations

from pathlib import Path

import pytest

from src import ui

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def test_miniatura_precisa_de_pontos_suficientes():
    assert ui.sparkline([1, 2]) == ""
    assert ui.sparkline([float("nan"), 1.0, 2.0]) == ""
    svg = ui.sparkline([3, 1, 4, 1, 5, 9, 2, 6])
    assert svg.startswith("<svg") and "polyline" in svg and "nan" not in svg.lower()


def test_miniatura_de_serie_constante_nao_divide_por_zero():
    assert "polyline" in ui.sparkline([5, 5, 5, 5])


@pytest.mark.parametrize("texto,esperado", [
    ("🎯 Central do Proprietário", "Central do Proprietário"),
    ("🛡️ Auditoria", "Auditoria"),
    ("⚙️ Administração", "Administração"),
    ("Sem emoji", "Sem emoji"),
])
def test_titulo_sem_emoji(texto, esperado):
    assert ui.sem_emoji(texto) == esperado


@pytest.mark.parametrize("arquivo", ["style.css", "style_novo.css"])
def test_css_com_chaves_balanceadas(arquivo):
    css = (ASSETS / arquivo).read_text(encoding="utf-8")
    assert css.count("{") == css.count("}")


def test_alerta_e_sempre_a_linha_que_abre_e_o_painel_antigo_nao_existe_mais():
    """O visual é um só (o "painel antigo" saiu em 06/10/2026): nada de cartão de alerta clássico."""
    class A:
        nivel, icone, titulo, posto, resumo, detalhes = "critico", "🔴", "ESTOQUE", "B2 Candói", "diesel", ["x"]

    html = ui.alerta_html(A())
    assert "<details" in html and 'class="alerta critico"' not in html and "Candói" in html
    assert not hasattr(ui, "novo") and not hasattr(ui, "visual")
