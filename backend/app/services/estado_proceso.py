"""Estado visible de una ejecución, derivado de los datos que ya existen.

`run.estado == completado` significa que todos los artículos terminaron. No
significa necesariamente que la síntesis posterior ya exista: el trabajador
cierra primero el lote para no perder las brechas si falla esa última llamada.

Las fases de este módulo no se guardan en otra columna. Se calculan a partir de
la ejecución y del estado del arte asociado a ella, evitando mantener dos
fuentes para el mismo hecho.
"""

from app.models.run import EstadoRun, Run


ANALIZANDO = "analizando"
GENERANDO_ESTADO_ARTE = "generando_estado_arte"
RESULTADOS_LISTOS = "resultados_listos"
ESTADO_ARTE_FALLIDO = "estado_arte_fallido"
ANALISIS_LISTO = "analisis_listo"
FALLIDO = "fallido"

PREFIJO_FALLO_ESTADO_ARTE = (
    "El analisis termino, pero no se pudo generar el estado del arte:"
)


def fase_run(run: Run, tiene_estado_arte: bool = False) -> str:
    """Devuelve la etapa que puede explicar la interfaz al usuario."""
    estado = run.estado.value if hasattr(run.estado, "value") else run.estado

    if estado in (EstadoRun.creado.value, EstadoRun.en_progreso.value):
        return ANALIZANDO
    if estado == EstadoRun.fallido.value:
        return FALLIDO
    if estado != EstadoRun.completado.value:
        return ANALIZANDO

    # La fila ligada a esta ejecución es la prueba de que su síntesis terminó.
    # Una síntesis histórica de otro run no convierte la actual en "lista".
    if tiene_estado_arte:
        return RESULTADOS_LISTOS
    if not run.genera_estado_arte:
        return ANALISIS_LISTO
    if (run.error_msg or "").startswith(PREFIJO_FALLO_ESTADO_ARTE):
        return ESTADO_ARTE_FALLIDO
    return GENERANDO_ESTADO_ARTE


def mensaje_fallo_estado_arte(error: Exception) -> str:
    """Mantiene identificable el fallo sin perder su motivo técnico."""
    return f"{PREFIJO_FALLO_ESTADO_ARTE} {error}"[:2000]
