# app/utils/text_extractor.py
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz
from pdfminer.high_level import extract_text as pdfminer_extract

from app.services.document_structure import (
    detectar_secciones,
    inicio_referencias,
    nombres_detectados,
)

# Estimación de caracteres por página de un artículo científico maquetado a
# doble columna. Sirve para saber si la extracción recuperó lo esperable.
CHARS_POR_PAGINA = 2600

MAX_PAGINAS = 30


def clean_text(txt: str) -> str:
    """Limpieza básica del texto extraído.

    La versión anterior recortaba con `re.sub(r'References\\b.*', '', DOTALL)`,
    que corta desde la PRIMERA aparición de la palabra en cualquier posición,
    incluido el cuerpo del artículo. Bastaba una frase como "the references
    cited by" para descartar el resto del documento sin dejar rastro (M-09).
    Ahora el corte se delega en la detección de encabezados, que exige inicio
    de línea y una posición avanzada dentro del documento.
    """
    txt = re.sub(r"\n{2,}", "\n", txt)
    txt = re.sub(r"^\s*(Page|Página)\s+\d+\s*$", "", txt, flags=re.IGNORECASE | re.MULTILINE)

    corte = inicio_referencias(txt)
    if corte is not None:
        txt = txt[:corte]

    return txt.strip()


@dataclass
class DiagnosticoExtraccion:
    """Indicadores de calidad de ingesta (nivel N0 de la especificación)."""

    texto: str = ""
    paginas: int = 0
    metodo: str = ""                      # pymupdf | pdfminer | ocr | ninguno
    chars_brutos: int = 0                 # antes de limpiar
    chars_finales: int = 0                # después de limpiar
    cobertura: float = 0.0                # N0.1
    ratio_truncamiento: float = 1.0       # N0.2
    secciones: set[str] = field(default_factory=set)   # N0.3
    legibilidad: float = 0.0              # N0.4
    avisos: list[str] = field(default_factory=list)

    @property
    def utilizable(self) -> bool:
        """Si el artículo puede analizarse con garantías mínimas."""
        return (
            self.chars_finales >= 300
            and self.cobertura >= 0.25
            and self.legibilidad >= 0.60
        )


# Palabras funcionales frecuentes en español e inglés. Su presencia indica que
# el texto es prosa legible y no ruido de una extracción defectuosa.
_FUNCIONALES = {
    "de", "la", "el", "los", "las", "que", "en", "y", "con", "por", "para",
    "una", "un", "del", "se", "es", "al", "como", "su", "lo", "no", "más",
    "the", "of", "and", "to", "in", "a", "is", "that", "for", "with", "on",
    "as", "are", "this", "by", "be", "from", "it", "an", "we", "which",
}

_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")


def legibilidad(texto: str, muestra: int = 20000) -> float:
    """Proporción de palabras funcionales sobre el total (N0.4).

    En prosa normal ronda 0.25–0.45. Un texto con extracción rota o un OCR
    fallido produce cadenas sin palabras funcionales y el valor se desploma.
    """
    fragmento = (texto or "")[:muestra].lower()
    palabras = _PALABRA.findall(fragmento)
    if len(palabras) < 20:
        return 0.0
    funcionales = sum(1 for p in palabras if p in _FUNCIONALES)
    # Se escala para que el rango habitual de prosa quede cerca de 1.0 y los
    # textos degradados caigan claramente por debajo del umbral.
    return min(1.0, (funcionales / len(palabras)) / 0.25)


def _extraer_bruto(pdf_path: str, max_chars: int) -> tuple[str, int, str]:
    """Devuelve (texto_bruto, n_paginas, metodo_usado)."""
    partes: list[str] = []
    paginas = 0
    try:
        with fitz.open(pdf_path) as doc:
            paginas = len(doc)
            for i in range(min(MAX_PAGINAS, paginas)):
                t = doc[i].get_text("text")
                if t:
                    partes.append(t)
                if sum(len(x) for x in partes) > max_chars:
                    break
    except Exception:
        pass

    txt = "\n".join(partes)
    if len(txt.strip()) >= 300:
        return txt, paginas, "pymupdf"

    try:
        txt2 = pdfminer_extract(pdf_path) or ""
        if len(txt2.strip()) > len(txt.strip()):
            txt = txt2
            if len(txt.strip()) >= 300:
                return txt, paginas, "pdfminer"
    except Exception:
        pass

    # PDF escaneado: se recurre al OCR (C-04).
    try:
        from app.services.ocr_fallback import ocr_pdf_to_text, OCRNoDisponible

        try:
            txt3 = ocr_pdf_to_text(pdf_path, max_pages=MAX_PAGINAS, max_chars=max_chars)
            if len(txt3.strip()) > len(txt.strip()):
                return txt3, paginas, "ocr"
        except OCRNoDisponible:
            pass
    except Exception:
        pass

    return txt, paginas, ("pymupdf" if txt.strip() else "ninguno")


def extraer_con_diagnostico(pdf_path: str, max_chars: int = 120_000) -> DiagnosticoExtraccion:
    """Extrae el texto y mide la calidad de la ingesta.

    Es la vía completa; `extract_full_text` se mantiene como envoltorio para
    los llamadores que solo necesitan el texto.
    """
    bruto, paginas, metodo = _extraer_bruto(pdf_path, max_chars)
    d = DiagnosticoExtraccion(paginas=paginas, metodo=metodo)
    d.chars_brutos = len(bruto)

    limpio = clean_text(bruto)
    if len(limpio) > max_chars:
        limpio = limpio[:max_chars]
    d.texto = limpio
    d.chars_finales = len(limpio)

    # N0.1 cobertura de extracción
    esperado = max(1, min(paginas, MAX_PAGINAS)) * CHARS_POR_PAGINA
    d.cobertura = round(min(1.0, d.chars_brutos / esperado), 4) if paginas else 0.0

    # N0.2 ratio de truncamiento
    d.ratio_truncamiento = round(d.chars_finales / d.chars_brutos, 4) if d.chars_brutos else 0.0

    # N0.3 secciones reconocidas
    d.secciones = nombres_detectados(detectar_secciones(limpio))

    # N0.4 legibilidad
    d.legibilidad = round(legibilidad(limpio), 4)

    if metodo == "ninguno" or d.chars_finales < 300:
        d.avisos.append("No se pudo extraer texto suficiente del PDF.")
    if paginas and d.cobertura < 0.25:
        d.avisos.append(
            "Cobertura de extracción muy baja (%.0f%%): el PDF puede estar "
            "protegido o mal generado." % (d.cobertura * 100)
        )
    if d.ratio_truncamiento < 0.30 and d.chars_brutos > 2000:
        d.avisos.append(
            "La limpieza descartó el %.0f%% del texto; revisar el corte de "
            "bibliografía." % ((1 - d.ratio_truncamiento) * 100)
        )
    if d.legibilidad < 0.60 and d.chars_finales >= 300:
        d.avisos.append(
            "Texto poco legible (%.2f): posible extracción defectuosa u OCR de "
            "baja calidad." % d.legibilidad
        )
    if not d.secciones & {"metodo", "resultados", "discusion"}:
        d.avisos.append(
            "No se reconoció ninguna sección sustantiva (método, resultados o "
            "discusión); la recuperación no podrá garantizar cobertura."
        )
    return d


def extract_full_text(pdf_path: str, max_chars: int = 120_000) -> str:
    """Compatibilidad: devuelve solo el texto limpio."""
    return extraer_con_diagnostico(pdf_path, max_chars=max_chars).texto
