# app/services/document_structure.py
"""
Detección de la estructura de un artículo científico.

Identifica dónde empieza y termina cada sección canónica (resumen, método,
resultados, discusión, referencias...) sobre el texto ya extraído del PDF.

Sirve a tres propósitos:
  1. Cortar la bibliografía sin mutilar el cuerpo del artículo (M-09).
  2. Medir qué secciones se reconocieron, como indicador de calidad de
     ingesta (N0.3).
  3. Etiquetar cada fragmento para poder exigir cobertura de método,
     resultados y discusión en la recuperación (M-10).

El enfoque es deliberadamente conservador: solo se acepta un encabezado si
aparece al principio de una línea y la línea es corta, como corresponde a un
título de sección. Una mención de la palabra "results" dentro de un párrafo
no dispara nada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Orden aproximado de aparición en un artículo. "otro" no se detecta: es el
# valor por defecto para el texto anterior a cualquier encabezado reconocido.
SECCIONES = (
    "resumen",
    "introduccion",
    "relacionados",
    "metodo",
    "resultados",
    "discusion",
    "limitaciones",
    "conclusion",
    "cuerpo",
    "agradecimientos",
    "referencias",
)

# Secciones que concentran la información útil para detectar una brecha.
# "cuerpo" son secciones numeradas de primer nivel con título propio del
# dominio —"Finite element analysis", "Machine learning framework",
# "System description"— que no encajan en ninguna categoría canónica pero
# contienen el desarrollo técnico. Enumerar todos sus nombres posibles sería
# imposible; reconocerlas por su forma sí.
SECCIONES_SUSTANTIVAS = ("metodo", "resultados", "discusion", "limitaciones",
                         "conclusion", "cuerpo")

# Patrones por sección. Se comparan contra el texto de la línea ya despojado
# de numeración ("3.", "IV.", "1.2") y en minúsculas.
_PATRONES: list[tuple[str, str]] = [
    ("resumen",         r"^(abstract|resumen|summary)$"),
    ("introduccion",    r"^(introduction|introduccion|introducción)$"),
    ("relacionados",    r"^(related work|background|literature review|state of the art|"
                        r"trabajos relacionados|antecedentes|marco teorico|marco teórico|"
                        r"revision de literatura|revisión de literatura|estado del arte)$"),
    ("metodo",          r"^(methods?|methodology|methodological approach|"
                        r"materials?\s+and\s+methods?|methods?\s+and\s+materials?|"
                        r"experimental\s+(setup|methodology|method|procedure|design)|"
                        r"research\s+method(ology)?|proposed\s+(approach|method(ology)?|framework)|"
                        r"metodo|método|metodos|métodos|metodologia|metodología|"
                        r"materiales y metodos|materiales y métodos|"
                        r"diseno metodologico|diseño metodológico|"
                        r"metodologia experimental|metodología experimental)$"),
    ("resultados",      r"^(results?|findings|results?\s+and\s+discussions?|"
                        r"experimental\s+results?|results?\s+and\s+analysis|"
                        r"resultados?|hallazgos|resultados y discusion(es)?|"
                        r"resultados y discusión|resultados experimentales)$"),
    ("discusion",       r"^(discussion|analysis and discussion|discusion|discusión|"
                        r"analisis|análisis)$"),
    ("limitaciones",    r"^(limitations?|limitations and future (work|research)|threats to validity|"
                        r"limitaciones?|limitaciones y trabajo futuro|trabajo futuro|future work)$"),
    ("conclusion",      r"^(conclusions?|concluding remarks|conclusion and future work|"
                        r"conclusion(es)?|conclusiones y trabajo futuro)$"),
    ("agradecimientos", r"^(acknowledge?ments?|funding|agradecimientos?|financiacion|financiación)$"),
    ("referencias",     r"^(references?|bibliography|works cited|literature cited|"
                        r"referencias?|bibliografia|bibliografía)$"),
]

_COMPILADOS = [(nombre, re.compile(pat, re.IGNORECASE)) for nombre, pat in _PATRONES]

# Numeración inicial: "3.", "3.1", "IV.", "(2)", "Capítulo 3"
#
# El número romano exige separador detrás. Sin esa condición, y al comparar
# sin distinguir mayúsculas, `[IVXLC]+` devoraba la primera letra de cualquier
# título que empezara por esas letras: "Conclusions" quedaba en "onclusions" e
# "Introduction" en "ntroduction". Solo se detectaban por ir numeradas, y un
# encabezado suelto pasaba inadvertido.
_NUMERACION = re.compile(
    r"^\s*(?:capitulo|capítulo|chapter|section|seccion|sección)?\s*"
    r"(?:"
    r"\(?\d+(?:\.\d+)*\)?\s*[\.\)\-–—:]*"      # 3   3.1   (3)   3.
    r"|[IVXLC]{1,7}\s*[\.\)\-–—:]+"            # IV.  X)   — separador obligatorio
    r")\s*",
    re.IGNORECASE,
)

# Ruido tipográfico frecuente en encabezados extraídos de PDF.
_RUIDO = re.compile(r"[\s\*\#_·•▪\-–—:]+$")

LONGITUD_MAX_ENCABEZADO = 60


@dataclass(frozen=True)
class Seccion:
    """Un tramo del documento atribuido a una sección canónica."""
    nombre: str
    inicio: int  # desplazamiento en caracteres, inclusive
    fin: int     # desplazamiento en caracteres, exclusivo

    def __len__(self) -> int:
        return max(0, self.fin - self.inicio)


# Encabezado con las letras separadas: "A B S T R A C T". Es el estilo
# tipográfico de varias editoriales y, al extraer el texto, llega tal cual.
# Los cinco artículos del primer lote real lo usaban, de modo que el resumen
# no se detectaba en ninguno y ROUGE no llegaba a calcularse nunca.
_ESPACIADO = re.compile(r"^\s*(?:[^\W\d_]\s+){2,}[^\W\d_]\s*$")

# Encabezado numerado de primer nivel: "3. Machine learning framework".
_NUMERADO_NIVEL1 = re.compile(r"^\s*(\d{1,2})[\.\)]?\s+([^\W\d_][^\n]{2,55})$")


def _colapsar_espaciado(linea: str) -> str:
    """Une las letras de un encabezado espaciado, si lo es."""
    if _ESPACIADO.match(linea or ""):
        return re.sub(r"\s+", "", linea)
    return linea


def _normalizar_encabezado(linea: str) -> str:
    """Deja la línea lista para comparar: sin numeración ni ruido."""
    t = _colapsar_espaciado(linea).strip()
    t = _NUMERACION.sub("", t)
    t = _RUIDO.sub("", t)
    return t.strip()


def _es_encabezado_estructural(linea: str) -> bool:
    """Encabezado numerado de primer nivel, aunque su título no sea canónico.

    Los artículos de ingeniería titulan sus secciones según el dominio, no
    según un vocabulario fijo. Reconocer la forma —número, título corto, sin
    punto final— captura ese desarrollo técnico que de otro modo quedaría
    etiquetado como "otro" y fuera de la cuota seccional.
    """
    s = (linea or "").strip()
    if not s or len(s) > LONGITUD_MAX_ENCABEZADO or s.endswith((".", ",", ";", ":")):
        return False
    m = _NUMERADO_NIVEL1.match(s)
    if not m:
        return False
    if int(m.group(1)) > 12:          # numeraciones altas suelen ser listas
        return False
    titulo = m.group(2).strip()
    # Un título de sección no acaba en preposición ni contiene demasiadas
    # palabras: eso delataría una frase partida por el salto de línea.
    return 1 <= len(titulo.split()) <= 7


def _clasificar_linea(linea: str) -> str | None:
    """Devuelve la sección si la línea es un encabezado reconocible."""
    bruta = linea.strip()
    if not bruta or len(bruta) > LONGITUD_MAX_ENCABEZADO:
        return None
    # Un encabezado no termina en punto ni en coma.
    if bruta.endswith((".", ",", ";")) and not bruta.endswith(".."):
        # Excepción: "3. Metodología." con punto final es admisible si es corta.
        if len(bruta) > 40:
            return None
    t = _normalizar_encabezado(linea)
    if not t:
        return None
    for nombre, patron in _COMPILADOS:
        if patron.match(t):
            return nombre
    # Sin coincidencia de vocabulario, pero con forma de sección numerada.
    if _es_encabezado_estructural(linea):
        return "cuerpo"
    return None


def detectar_secciones(texto: str) -> list[Seccion]:
    """Divide el texto en secciones según los encabezados reconocidos.

    El texto anterior al primer encabezado se atribuye a "otro": típicamente
    portada, autores y afiliaciones.
    """
    if not texto:
        return []

    marcas: list[tuple[int, str]] = []  # (desplazamiento, seccion)
    desplazamiento = 0
    for linea in texto.splitlines(keepends=True):
        nombre = _clasificar_linea(linea)
        if nombre is not None:
            marcas.append((desplazamiento, nombre))
        desplazamiento += len(linea)

    if not marcas:
        return [Seccion("otro", 0, len(texto))]

    secciones: list[Seccion] = []
    if marcas[0][0] > 0:
        secciones.append(Seccion("otro", 0, marcas[0][0]))

    for i, (ini, nombre) in enumerate(marcas):
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(texto)
        if fin > ini:
            secciones.append(Seccion(nombre, ini, fin))
    return secciones


def seccion_en(secciones: list[Seccion], posicion: int) -> str:
    """Sección a la que pertenece un desplazamiento del texto."""
    for s in secciones:
        if s.inicio <= posicion < s.fin:
            return s.nombre
    return "otro"


def nombres_detectados(secciones: list[Seccion]) -> set[str]:
    """Secciones canónicas presentes, excluyendo el relleno 'otro'."""
    return {s.nombre for s in secciones if s.nombre != "otro"}


def inicio_referencias(texto: str, fraccion_minima: float = 0.5) -> int | None:
    """Posición donde empieza la bibliografía, o None si no se localiza.

    Solo se acepta un encabezado situado más allá de `fraccion_minima` del
    documento. Esto evita el fallo de la implementación anterior, que cortaba
    en la primera aparición de la palabra "References" en cualquier posición
    —incluido el cuerpo del texto— y podía descartar la mayor parte del
    artículo sin dejar rastro (M-09).
    """
    if not texto:
        return None

    umbral = int(len(texto) * fraccion_minima)
    candidato: int | None = None

    desplazamiento = 0
    for linea in texto.splitlines(keepends=True):
        if _clasificar_linea(linea) == "referencias" and desplazamiento >= umbral:
            candidato = desplazamiento
            break
        desplazamiento += len(linea)

    return candidato


def extraer_abstract(texto: str, min_chars: int = 200, max_chars: int = 3000) -> str | None:
    """Devuelve el texto del resumen del artículo, si se identificó.

    Es la referencia correcta para calcular ROUGE, en lugar de las primeras
    180 palabras del PDF, que son portada y afiliaciones (M-02).
    """
    for s in detectar_secciones(texto):
        if s.nombre != "resumen":
            continue
        cuerpo = texto[s.inicio:s.fin]
        # Quita la propia línea del encabezado.
        partes = cuerpo.split("\n", 1)
        cuerpo = partes[1] if len(partes) > 1 else cuerpo
        cuerpo = re.sub(r"\s+", " ", cuerpo).strip()
        if len(cuerpo) >= min_chars:
            return cuerpo[:max_chars]
    return None
