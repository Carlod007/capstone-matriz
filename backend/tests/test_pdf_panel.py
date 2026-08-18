# tests/test_pdf_panel.py
"""
El grafico del PDF no dibuja una barra en cero para lo que no aplica.

Es el sitio donde el cero enganoso hacia mas dano. Una tabla admite la palabra
"no aplicable" al lado del nombre; una barra a ras de suelo se entiende de un
vistazo y no admite matices: quien mire el informe leera "los resumenes salieron
pesimos" cuando lo que ocurre es que no habia nada que medir.

`get_float` hacia `float(promedios.get(k, 0.0) or 0.0)`, con lo que un valor
ausente se convertia en 0.0 antes de llegar al grafico. Todo el arreglo del
resto del sistema se perdia en la ultima linea.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

BASE = {
    "avg_sim_promedio": 0.71,
    "avg_val_score": 0.64,
    "avg_entropia_norm": 0.30,
    "avg_rouge1_rec": 0.45,
    "avg_lexical_density": 0.58,
}


def _barras(dibujo):
    """Devuelve {nombre: valor} de las barras dibujadas."""
    grafico = dibujo.contents[0]
    return dict(zip(grafico.categoryAxis.categoryNames, grafico.data[0]))


def _pies(dibujo):
    return " ".join(getattr(c, "text", "") for c in dibujo.contents[1:])


@pytest.fixture
def chart():
    from app.routers.export import _HAS_GRAPHICS, _chart_indicadores_0_1

    if not _HAS_GRAPHICS:
        pytest.skip("ReportLab sin el modulo de graficos")
    return _chart_indicadores_0_1


class TestGraficoDeIndicadores:
    def test_con_todo_medido_dibuja_las_cinco(self, chart):
        """El caso normal, que es lo que las demas pruebas contrastan."""
        b = _barras(chart(BASE))

        assert len(b) == 5
        assert b["ROUGE-1 recall"] == pytest.approx(0.45)
        assert "No aplicable" not in _pies(chart(BASE))

    def test_rouge_no_aplicable_no_se_dibuja_como_cero(self, chart):
        d = chart({**BASE, "avg_rouge1_rec": None})
        b = _barras(d)

        assert "ROUGE-1 recall" not in b, (
            "una barra en cero se lee como un resultado pesimo, no como una "
            "medicion que no aplica")
        assert 0.0 not in b.values()
        assert len(b) == 4
        # Y la ausencia se nombra: omitir sin decirlo tambien desinforma.
        assert "ROUGE-1 recall" in _pies(d)
        assert "No aplicable" in _pies(d)

    def test_las_demas_barras_no_se_desplazan(self, chart):
        """Al quitar una barra, las etiquetas deben seguir sobre su valor.

        El grafico emparejaba `data` con `categoryNames` por posicion. Si se
        filtrara una lista y no la otra, cada barra quedaria rotulada con el
        nombre de la siguiente: peor que el cero, porque el numero es correcto
        y el error es invisible.
        """
        b = _barras(chart({**BASE, "avg_rouge1_rec": None}))

        assert b["Similitud"] == pytest.approx(0.71)
        assert b["Val. Score"] == pytest.approx(0.64)
        assert b["Entropía (norm)"] == pytest.approx(0.30)
        assert b["Densidad léxica"] == pytest.approx(0.58)

    def test_un_cero_de_verdad_si_se_dibuja(self, chart):
        """La distincion es entre "no aplica" y "salio cero", no entre cero y
        el resto: un cero medido es informacion y debe verse."""
        b = _barras(chart({**BASE, "avg_rouge1_rec": 0.0}))

        assert "ROUGE-1 recall" in b
        assert b["ROUGE-1 recall"] == pytest.approx(0.0)

    def test_sin_ningun_indicador_no_devuelve_grafico(self, chart):
        assert chart({k: None for k in BASE}) is None

    def test_un_valor_ilegible_no_pasa_por_cero(self, chart):
        """Antes cualquier excepcion caia en `return 0.0`."""
        b = _barras(chart({**BASE, "avg_rouge1_rec": "no aplicable"}))

        assert "ROUGE-1 recall" not in b

    def test_los_valores_siguen_acotados(self, chart):
        """El recorte a 0..1 estaba antes en un `clamp` aparte."""
        b = _barras(chart({**BASE, "avg_sim_promedio": 1.4,
                           "avg_val_score": -0.2}))

        assert b["Similitud"] == pytest.approx(1.0)
        assert b["Val. Score"] == pytest.approx(0.0)
