# app/services/metricas/catalogo.py
"""
Catálogo de métricas: qué significa cada código.

Vive en un solo sitio para que la interfaz no tenga que repetir los nombres
ni las explicaciones. Si una métrica se retira, desaparece de aquí y deja de
mostrarse en todas partes a la vez, sin cabos sueltos.

Cada entrada declara además `mejor`, porque no todas las métricas se leen en
la misma dirección: en unas conviene un valor alto y en otras uno bajo. Sin
ese dato, un panel puede pintar de verde justamente lo que va mal.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

ALTO = "alto"     # mejor cuanto mayor
BAJO = "bajo"     # mejor cuanto menor
NEUTRO = "neutro"  # descriptiva, no es una nota


@dataclass(frozen=True)
class Ficha:
    codigo: str
    nombre: str
    nivel: str
    ambito: str          # brecha | articulo | run
    mejor: str
    rango: str
    descripcion: str
    interpretacion: str

    def dict(self) -> dict:
        return asdict(self)


CATALOGO: dict[str, Ficha] = {f.codigo: f for f in [
    Ficha("N1.2", "Cobertura seccional", "N1 Recuperación", "brecha", ALTO, "0 a 1",
          "Qué proporción de las secciones sustantivas del artículo llegó al modelo.",
          "Un valor bajo significa que el análisis se hizo leyendo poco más que la "
          "introducción, que es la sección más parecida entre artículos distintos."),

    Ficha("N1.3", "Diversidad del contexto", "N1 Recuperación", "brecha", ALTO, "0 a 1",
          "Cuánto se diferencian entre sí los fragmentos entregados al modelo.",
          "Si es baja, el contexto repite la misma idea y desaprovecha la ventana "
          "disponible."),

    Ficha("N2.1", "Fidelidad evidencial", "N2 Fidelidad", "brecha", ALTO, "0 a 1",
          "Qué proporción de las afirmaciones comprobables de la brecha está "
          "respaldada por algún fragmento del artículo.",
          "Es la métrica central del sistema. Una afirmación que describe lo que el "
          "artículo hace y no aparece en ningún fragmento es, por definición, una "
          "alucinación."),

    Ficha("N2.2", "Trazabilidad", "N2 Fidelidad", "brecha", ALTO, "0 a 1",
          "Proporción de afirmaciones que pueden vincularse a un fragmento citable.",
          "Sin esto la herramienta no es auditable: el investigador no puede "
          "comprobar de dónde sale cada frase."),

    Ficha("N2.4", "Equilibrio evidencial", "N2 Fidelidad", "brecha", ALTO, "0 a 1",
          "Qué parte de la brecha describe hechos del artículo, frente a la que "
          "solo concluye.",
          "Una brecha compuesta unicamente por conclusiones no tiene nada que "
          "verificar: es especulación bien redactada. Avisa de ello aunque la "
          "fidelidad salga alta por apoyarse en una sola afirmación."),

    Ficha("N2.5", "Contradicciones", "N2 Fidelidad", "brecha", BAJO, "0 a 1",
          "Proporción de afirmaciones de la brecha a las que algún fragmento del "
          "artículo lleva la contraria.",
          "No es la inversa de la fidelidad y pesa más: una afirmación sin "
          "respaldo significa que el artículo no habla de eso; una contradicha "
          "significa que dice lo opuesto. Se comprueban también las "
          "inferenciales, que no se verifican pero sí pueden ser incompatibles "
          "con lo que el artículo afirma. Sobre datos reales se coló una brecha "
          "que hablaba de «posibles diseños inseguros» en un artículo que "
          "califica el estándar de conservador."),

    Ficha("N2.verificada", "Verificación realizada", "N2 Fidelidad", "brecha", ALTO,
          "0 o 1",
          "Si la comprobación de fidelidad llegó a ejecutarse.",
          "Requiere una llamada adicional al modelo. Cuando no se ejecuta se guarda "
          "el motivo: una medición que no se hizo no equivale a una medición con "
          "resultado cero."),

    Ficha("N5.2", "Reetiquetado automático", "N5 Tipificación", "brecha", BAJO,
          "0 a 1",
          "Con qué frecuencia un contador de palabras clave sobrescribe el tipo que "
          "asignó el modelo.",
          "Un valor alto significa que la etiqueta final la decide una heurística y "
          "no el modelo. Conviene saberlo antes de dar por buena la tipificación: "
          "nunca se comprobó si esa heurística ayuda o perjudica."),

    Ficha("N5.3", "Cobertura de la síntesis", "N5 Síntesis", "proyecto", ALTO,
          "0 a 1",
          "Qué proporción de las brechas del lote está representada en el estado "
          "del arte.",
          "Detecta que la síntesis ignore artículos. Con diez brechas de entrada y "
          "una redacción que recoge seis, el texto parece completo y no lo está."),

    Ficha("N5.5", "Citas sin correspondencia", "N5 Síntesis", "proyecto", BAJO,
          "0 a 1",
          "Proporción de referencias del estado del arte que no corresponde a "
          "ningún artículo del proyecto.",
          "El prompt prohíbe inventar citas y hasta ahora nada verificaba que se "
          "cumpliera. Referencias inventadas son el fallo más grave posible en una "
          "herramienta de revisión de literatura."),

    Ficha("N3.1", "Discriminabilidad", "N3 Especificidad", "run", ALTO, "0 a 1",
          "Cuánto se diferencian las brechas de artículos distintos del mismo proyecto.",
          "Es la métrica más diagnóstica: si el modelo emite la misma brecha genérica "
          "para todos los artículos, este valor se desploma."),

    Ficha("N3.2", "Densidad de anclajes", "N3 Especificidad", "brecha", ALTO,
          "por 100 palabras",
          "Cifras, nombres propios, siglas y vocabulario metodológico en la brecha.",
          "Distingue «faltan estudios en contextos diversos» de «no hay validación "
          "externa en cohortes latinoamericanas»."),

    Ficha("N3.3", "Contenido informativo", "N3 Especificidad", "brecha", ALTO,
          "IDF medio",
          "Cuán poco frecuentes son los términos de la brecha dentro del corpus.",
          "Un valor alto indica vocabulario específico; uno bajo, lugares comunes."),

    Ficha("N3.4", "Redundancia", "N3 Especificidad", "run", BAJO, "0 a 1",
          "Proporción de brechas casi idénticas a otra del proyecto.",
          "Debería ser cero. Valores altos indican que el modelo repite hallazgos."),

    Ficha("N4.1a", "ROUGE-1 precisión", "N4 Resumen", "brecha", ALTO, "0 a 1",
          "Qué proporción de las palabras del resumen aparece en el abstract.",
          "Penaliza que el resumen añada contenido ausente en el original. Solo se "
          "calcula si ambos están en el mismo idioma."),

    Ficha("N4.1b", "ROUGE-1 recall", "N4 Resumen", "brecha", ALTO, "0 a 1",
          "Solape de palabras entre el resumen generado y el abstract del artículo.",
          "Solo se calcula si ambos están en el mismo idioma: entre idiomas distintos "
          "daría casi cero con independencia de la calidad."),

    Ficha("N4.1c", "ROUGE-1 F1", "N4 Resumen", "brecha", ALTO, "0 a 1",
          "Equilibrio entre precisión y exhaustividad del solape de palabras.",
          "Misma condición de idioma que el recall."),

    Ficha("N4.1d", "ROUGE-2 F1", "N4 Resumen", "brecha", ALTO, "0 a 1",
          "Solape de pares de palabras consecutivas.",
          "Más exigente que ROUGE-1: premia que se conserve la formulación."),

    Ficha("N4.1e", "ROUGE-L F1", "N4 Resumen", "brecha", ALTO, "0 a 1",
          "Subsecuencia común más larga entre resumen y abstract.",
          "Tolera que el resumen intercale palabras, a diferencia de ROUGE-2."),

    Ficha("N4.2", "Similitud semántica", "N4 Resumen", "brecha", ALTO, "0 a 1",
          "Cercanía de significado entre el resumen y el abstract.",
          "Capta la paráfrasis correcta que ROUGE penaliza, y es la única de las dos "
          "que sigue siendo válida cuando están en idiomas distintos."),

    Ficha("N4.4", "Densidad léxica", "N4 Resumen", "brecha", NEUTRO, "0 a 1",
          "Proporción de palabras con contenido frente al total.",
          "Es una estadística descriptiva, no una nota: una densidad alta no implica "
          "un resumen mejor."),

    Ficha("N4.ref", "Abstract localizado", "N4 Resumen", "articulo", ALTO, "0 o 1",
          "Si se pudo extraer el abstract real del PDF.",
          "Sin él no se calcula ROUGE, para no producir una cifra sin significado."),
]}


def ficha(codigo: str) -> Ficha | None:
    return CATALOGO.get(codigo)


def nombre(codigo: str) -> str:
    f = CATALOGO.get(codigo)
    return f.nombre if f else codigo


def codigos_por_ambito(ambito: str) -> list[str]:
    return [c for c, f in CATALOGO.items() if f.ambito == ambito]
