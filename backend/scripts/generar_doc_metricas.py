"""Genera docs/Metricas.md a partir del catalogo.

El catalogo en codigo es la unica fuente: es lo que la aplicacion sirve al
panel. Un documento escrito a mano al lado se desincroniza en cuanto alguien
anade una metrica, y este proyecto ya ha pagado dos veces el precio de tener
dos verdades para un mismo hecho.

    python scripts/generar_doc_metricas.py
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRETO", "solo-para-generar-el-documento-" + "x" * 20)
os.environ.setdefault("GEMINI_MODE", "mock")

from app.services.metricas.catalogo import CATALOGO  # noqa: E402

NIVELES = {
    "N0": ("Ingesta", "Qué se pudo leer del PDF y con qué calidad."),
    "N1": ("Recuperación",
           "Qué fragmentos llegaron al modelo. Si aquí falla algo, todo lo "
           "demás mide sobre un texto equivocado."),
    "N2": ("Fidelidad",
           "Si lo que dice la brecha se sostiene en el artículo. Es la capa "
           "que distingue esta herramienta de pedirle un resumen a un chatbot."),
    "N3": ("Especificidad",
           "Si las brechas distinguen un artículo de otro o son "
           "intercambiables."),
    "N4": ("Resumen", "Calidad del resumen generado frente al abstract."),
    "N5": ("Síntesis", "El estado del arte: qué cubre y si inventa citas."),
    "N6": ("Anclaje humano",
           "Lo único que puede decir si el sistema ACIERTA. El resto lo "
           "compara consigo mismo."),
}

DIRECCION = {
    "alto": "↑ mayor es mejor",
    "bajo": "↓ menor es mejor",
    "neutro": "descriptiva (no hay valor mejor)",
}

AMBITO = {
    "brecha": "cada brecha",
    "articulo": "cada artículo",
    "run": "el análisis completo",
    "proyecto": "el proyecto completo",
}

CABECERA = """# Métricas, nivel por nivel

**Este documento se genera.** No lo edites a mano: sale de
`backend/app/services/metricas/catalogo.py`, que es lo que la aplicación sirve
al panel. Para actualizarlo:

```bash
cd backend && python scripts/generar_doc_metricas.py
```

Un documento escrito al lado del código se desincroniza en cuanto alguien añade
una métrica, y aquí ya ha costado caro tener dos verdades para un mismo hecho.

---

## Cómo leer cualquiera de ellas

**Mediana y recorrido intercuartílico, no promedio.** Con pocos artículos un
caso extremo arrastra la media entera. Una mediana de 0.86 con dispersión nula
y otra con dispersión amplia dicen cosas opuestas.

**La dirección no es la misma en todas.** `↓ menor es mejor` significa que un
valor alto es un problema. Leerlas todas como «más es mejor» invierte el
sentido de varias.

**Sin valor no es cero.** Una métrica que no aplica —ROUGE entre idiomas
distintos, por ejemplo— se declara no aplicable. Un cero afirmaría que el
resultado fue pésimo.

**«Separa los casos» habla del instrumento, no del proyecto.** Dice si esa
métrica distingue unos artículos de otros. Un resultado excelente y parejo en
todos sale como «valores parecidos», y no es una mala noticia.

**No hay umbrales de calidad.** No existen valores calibrados que digan qué es
bueno en este dominio: por eso el panel no pinta zonas verdes ni rojas. Eso es
lo que N6 viene a resolver.

---
"""


def main() -> None:
    partes = [CABECERA]
    por_nivel: dict[str, list] = {}
    for f in CATALOGO.values():
        por_nivel.setdefault(f.codigo.split(".")[0], []).append(f)

    for prefijo in sorted(por_nivel, key=lambda p: (len(p), p)):
        nombre, resumen = NIVELES.get(prefijo, (prefijo, ""))
        partes.append("\n## %s — %s\n\n%s\n" % (prefijo, nombre, resumen))
        for f in sorted(por_nivel[prefijo], key=lambda x: x.codigo):
            partes.append(
                "\n### %s · %s\n\n"
                "**Qué mide.** %s\n\n"
                "**Por qué importa.** %s\n\n"
                "| | |\n|---|---|\n"
                "| Escala | %s |\n| Dirección | %s |\n| Se calcula sobre | %s |\n"
                "| Versión de fórmula | v%s |\n"
                % (f.codigo, f.nombre, f.descripcion, f.interpretacion,
                   f.rango, DIRECCION.get(f.mejor, f.mejor),
                   AMBITO.get(f.ambito, f.ambito), f.version_formula)
            )

    # N6 no está en el catálogo: no la calcula el sistema, la aporta una
    # persona. Omitirla dejaría el documento describiendo seis niveles y
    # hablando de siete.
    partes.append("""
## N6 — Anclaje humano

No aparece arriba porque **no la calcula el sistema**. La aporta quien se ha
leído los artículos, desde la pantalla «Tu revisión de las brechas».

Cada brecha se marca como **correcta**, **parcial** —acierta el problema y
falla en un matiz, vale medio punto— o **incorrecta**, y las dos últimas exigen
explicación escrita. Sin el motivo, el dato dice que algo falló pero no qué: no
sirve para corregir el sistema ni para sostener la evaluación.

Los veredictos viven en `validacion_humana`, con una fila por (brecha,
persona), de modo que el acuerdo entre jueces se pueda calcular el día que haya
más de un anotador.

**La limitación que hay que declarar:** con un solo anotador no existe acuerdo
entre jueces. Y validar un modelo de lenguaje con otro modelo de lenguaje es
circular: sirve para localizar pasajes, no para juzgar.
""")

    destino = (pathlib.Path(__file__).resolve().parent.parent.parent
               / "docs" / "Metricas.md")
    destino.write_text("".join(partes), encoding="utf-8")
    print("generado:", destino, "(%d métricas)" % len(CATALOGO))


if __name__ == "__main__":
    main()
