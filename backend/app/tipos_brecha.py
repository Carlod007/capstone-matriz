"""Taxonomía transversal de brechas de investigación.

Las etiquetas describen el foco predominante del vacío, no la carrera del
proyecto. Mantenerlas en un solo lugar evita que el modelo de datos acepte una
categoría que el analizador luego descarte (o al revés).
"""

CRITERIOS_TIPOS_BRECHA: dict[str, str] = {
    "metodológica": (
        "fallas en cómo se diseña, mide, muestrea, valida o documenta el "
        "procedimiento; incluye reproducibilidad"
    ),
    "temática": (
        "el tema, caso, población, sector, región o ámbito está poco cubierto "
        "o mal delimitado"
    ),
    "teórica": (
        "faltan marcos conceptuales, modelos explicativos, constructos o "
        "hipótesis"
    ),
    "tecnológica": (
        "faltan herramientas, sistemas, arquitecturas o capacidades técnicas "
        "de implementación y rendimiento"
    ),
    "empírica": (
        "faltan datos, casos, observaciones, evidencia experimental o "
        "replicaciones externas, aunque el procedimiento pueda ser adecuado"
    ),
    "aplicada": (
        "falta transferir el resultado a la práctica o comprobar su adopción, "
        "usabilidad, viabilidad económica, regulatoria u operativa"
    ),
    "otra": "ninguna de las categorías anteriores describe el foco principal",
}

TIPOS_BRECHA: tuple[str, ...] = tuple(CRITERIOS_TIPOS_BRECHA)


def tipos_para_prompt() -> str:
    """Lista estable para las instrucciones que recibe el modelo."""
    return ", ".join(TIPOS_BRECHA)


def criterios_para_prompt() -> str:
    """Definiciones breves y mutuamente distinguibles para el prompt."""
    return "\n".join(
        f"- {tipo}: {criterio}."
        for tipo, criterio in CRITERIOS_TIPOS_BRECHA.items()
    )
