# app/services/metricas/texto.py
"""
Utilidades de texto para la capa de medición.

Aquí vive lo que comparten varias métricas: tokenización, palabras vacías,
las variantes de ROUGE y el contenido informativo. Se separa del cálculo de
cada métrica para que la definición de "palabra de contenido" sea una sola en
todo el sistema y no tres distintas según el módulo.
"""

from __future__ import annotations

import collections
import math
import re
import unicodedata
from typing import Iterable, Sequence

# ---------------------------------------------------------------- vacías
# La lista anterior tenía unas 65 entradas mezclando ambos idiomas, lo que
# inflaba la densidad léxica y la volvía casi constante (M-06). Estas son
# listas de tamaño realista y separadas por idioma.
VACIAS_ES = {
    "a", "al", "algo", "algun", "alguna", "algunas", "alguno", "algunos", "ante",
    "antes", "aquel", "aquella", "aquellas", "aquello", "aquellos", "aqui", "asi",
    "aun", "aunque", "bajo", "bien", "cada", "casi", "como", "con", "contra",
    "cual", "cuales", "cualquier", "cuando", "cuanto", "cuyo", "de", "debe",
    "deben", "del", "demas", "dentro", "desde", "donde", "dos", "durante", "e",
    "el", "ella", "ellas", "ello", "ellos", "en", "entonces", "entre", "era",
    "eran", "eres", "es", "esa", "esas", "ese", "eso", "esos", "esta", "estaba",
    "estaban", "estan", "estas", "este", "esto", "estos", "estoy", "fue",
    "fueron", "gran", "ha", "haber", "habia", "han", "hasta", "hay", "he",
    "hemos", "incluso", "la", "las", "le", "les", "lo", "los", "luego", "mas",
    "me", "mediante", "menos", "mi", "mientras", "mis", "misma", "mismo", "mucha",
    "mucho", "muy", "nada", "ni", "no", "nos", "nosotros", "nuestra", "nuestro",
    "o", "otra", "otras", "otro", "otros", "para", "pero", "poco", "por",
    "porque", "pues", "que", "quien", "quienes", "se", "sea", "sean", "segun",
    "ser", "si", "sido", "siempre", "sin", "sino", "sobre", "solo", "son", "su",
    "sus", "tal", "tambien", "tampoco", "tan", "tanto", "te", "tiene", "tienen",
    "toda", "todas", "todo", "todos", "tras", "tu", "un", "una", "unas", "uno",
    "unos", "usted", "va", "van", "varios", "ya", "yo",
}

VACIAS_EN = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "him", "his", "how", "however", "i", "if", "in", "into", "is", "it", "its",
    "itself", "just", "may", "me", "might", "more", "most", "must", "my", "no",
    "nor", "not", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "out", "over", "own", "same", "shall", "she", "should", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them", "then",
    "there", "therefore", "these", "they", "this", "those", "through", "thus",
    "to", "too", "under", "until", "up", "us", "very", "was", "we", "were",
    "what", "when", "where", "whether", "which", "while", "who", "whom", "why",
    "will", "with", "would", "you", "your", "yours",
}

VACIAS = VACIAS_ES | VACIAS_EN

_PALABRA = re.compile(r"[0-9]+(?:[.,][0-9]+)?|[^\W\d_]+", re.UNICODE)


def sin_tildes(texto: str) -> str:
    """Quita diacríticos para que 'metodología' y 'metodologia' se unifiquen."""
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenizar(texto: str, normalizar: bool = True) -> list[str]:
    """Palabras y números del texto, en minúsculas."""
    t = (texto or "").lower()
    if normalizar:
        t = sin_tildes(t)
    return _PALABRA.findall(t)


def tokens_contenido(texto: str) -> list[str]:
    """Tokens que aportan significado: sin palabras vacías ni tokens de 1 letra."""
    return [t for t in tokenizar(texto) if t not in VACIAS and len(t) > 1]


# ---------------------------------------------------------------- ROUGE
def _ngramas(tokens: Sequence[str], n: int) -> collections.Counter:
    if len(tokens) < n:
        return collections.Counter()
    return collections.Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def rouge_n(referencia: str, generado: str, n: int = 1) -> tuple[float, float, float]:
    """ROUGE-N: precisión, exhaustividad y F1 sobre n-gramas.

    La referencia debe ser el abstract real del artículo. Con las primeras
    palabras del PDF —portada, autores y afiliaciones— el valor no significa
    nada, que es el fallo M-02.
    """
    ref, gen = tokenizar(referencia), tokenizar(generado)
    cr, cg = _ngramas(ref, n), _ngramas(gen, n)
    if not cr or not cg:
        return 0.0, 0.0, 0.0
    solape = sum(min(cg[g], cr[g]) for g in cg)
    prec = solape / max(1, sum(cg.values()))
    rec = solape / max(1, sum(cr.values()))
    f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return prec, rec, f1


def _lcs(a: Sequence[str], b: Sequence[str]) -> int:
    """Longitud de la subsecuencia común más larga, en memoria O(min)."""
    if not a or not b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    previa = [0] * (len(b) + 1)
    for x in a:
        actual = [0]
        for j, y in enumerate(b):
            actual.append(previa[j] + 1 if x == y else max(previa[j + 1], actual[j]))
        previa = actual
    return previa[-1]


def rouge_l(referencia: str, generado: str) -> tuple[float, float, float]:
    """ROUGE-L: basado en la subsecuencia común más larga.

    A diferencia de ROUGE-N no exige que las palabras sean contiguas, así que
    tolera la reordenación propia de un resumen abstractivo.
    """
    ref, gen = tokenizar(referencia), tokenizar(generado)
    if not ref or not gen:
        return 0.0, 0.0, 0.0
    l = _lcs(ref, gen)
    prec = l / len(gen)
    rec = l / len(ref)
    f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return prec, rec, f1


# ---------------------------------------------------------------- densidad
# ---------------------------------------------------------------- idioma
def idioma(texto: str, minimo: int = 12) -> str:
    """Detecta si el texto es español, inglés o indeterminado.

    Se apoya en las palabras funcionales, que son las más frecuentes y las
    que menos varían con el tema. No hace falta una biblioteca externa para
    distinguir dos idiomas tan separados.

    Es necesario porque ROUGE mide solape léxico: comparar un resumen en
    español con un abstract en inglés da casi cero por construcción, con
    independencia de lo fiel que sea el resumen. Sin esta comprobación, la
    cifra parece una medida de calidad y no lo es.
    """
    toks = tokenizar(texto, normalizar=True)
    if len(toks) < minimo:
        return "indeterminado"
    solo_es = VACIAS_ES - VACIAS_EN
    solo_en = VACIAS_EN - VACIAS_ES
    es = sum(1 for t in toks if t in solo_es)
    en = sum(1 for t in toks if t in solo_en)
    if es == 0 and en == 0:
        return "indeterminado"
    if es >= en * 1.5:
        return "es"
    if en >= es * 1.5:
        return "en"
    return "indeterminado"


def densidad_lexica(texto: str) -> float:
    """Proporción de palabras de contenido (N4.4).

    Se conserva como estadística descriptiva, no como indicador de calidad:
    una densidad alta no implica un resumen mejor.
    """
    toks = tokenizar(texto)
    if not toks:
        return 0.0
    return len([t for t in toks if t not in VACIAS and len(t) > 1]) / len(toks)


# ---------------------------------------------------------------- IDF
def idf(documentos: Iterable[Sequence[str]]) -> dict[str, float]:
    """IDF suavizado a partir de una colección de documentos ya tokenizados."""
    docs = [set(d) for d in documentos]
    n = len(docs)
    if n == 0:
        return {}
    frecuencia: collections.Counter = collections.Counter()
    for d in docs:
        frecuencia.update(d)
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in frecuencia.items()}


def contenido_informativo(texto: str, tabla_idf: dict[str, float]) -> float:
    """Contenido informativo medio por palabra de contenido (N3.3).

    Es lo que la entropía de Shannon pretendía capturar y nunca capturó: se
    mide sobre unidades con significado, no sobre caracteres, y por eso sí
    distingue un texto específico de uno genérico.
    """
    toks = tokens_contenido(texto)
    if not toks:
        return 0.0
    if not tabla_idf:
        return 0.0
    valores = [tabla_idf.get(t, max(tabla_idf.values())) for t in toks]
    return sum(valores) / len(valores)


# ---------------------------------------------------------------- anclajes
# Marcas de concreción: cifras, porcentajes, siglas, años, nombres propios y
# vocabulario metodológico. Distinguen "faltan estudios en contextos diversos"
# de "no hay validación externa en cohortes latinoamericanas".
_CIFRA = re.compile(r"\b\d+(?:[.,]\d+)?\s*%?\b")
_ANIO = re.compile(r"\b(19|20)\d{2}\b")
_SIGLA = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,}[A-ZÁÉÍÓÚÑ0-9\-]*\b")
_PROPIO = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b", re.MULTILINE)

TERMINOS_METODO = {
    "muestra", "muestral", "muestreo", "cohorte", "cohortes", "ensayo", "control",
    "aleatorizado", "longitudinal", "transversal", "cualitativo", "cuantitativo",
    "mixto", "encuesta", "entrevista", "corpus", "dataset", "conjunto", "validacion",
    "cruzada", "externa", "interna", "replicacion", "reproducibilidad", "kappa",
    "correlacion", "regresion", "significancia", "intervalo", "confianza",
    "sensibilidad", "especificidad", "precision", "exhaustividad", "metrica",
    "protocolo", "instrumento", "escala", "constructo", "variable", "covariable",
    "sesgo", "confusion", "poblacion", "participantes", "sujetos", "anotadores",
}


def densidad_anclajes(texto: str) -> float:
    """Anclajes concretos por cada 100 palabras (N3.2).

    Detecta la genericidad, que es el modo de falla real de estos sistemas:
    texto correcto, verificable y aplicable a cualquier artículo.
    """
    toks = tokenizar(texto)
    if len(toks) < 5:
        return 0.0
    anclajes = 0
    anclajes += len(_CIFRA.findall(texto or ""))
    anclajes += len(_ANIO.findall(texto or ""))
    anclajes += len(_SIGLA.findall(texto or ""))
    anclajes += len(_PROPIO.findall(texto or ""))
    anclajes += sum(1 for t in toks if t in TERMINOS_METODO)
    return round(100.0 * anclajes / len(toks), 4)
