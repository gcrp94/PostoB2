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


def test_visual_antigo_continua_gerando_o_html_de_antes(monkeypatch):
    """Sem sessão do Streamlit o painel cai no clássico: nada de <details>."""
    monkeypatch.setattr(ui, "novo", lambda: False)

    class A:
        nivel, icone, titulo, posto, resumo, detalhes = "critico", "🔴", "ESTOQUE", "B2 Candói", "diesel", ["x"]

    assert 'class="alerta critico"' in ui.alerta_html(A()) and "<details" not in ui.alerta_html(A())
    monkeypatch.setattr(ui, "novo", lambda: True)
    assert "<details" in ui.alerta_html(A())
