# app/services/ocr_fallback.py
"""
OCR de respaldo para PDFs escaneados.

Solo se activa cuando la extracción de texto nativa devuelve poco contenido
o contenido ilegible. Nunca se ejecuta sobre PDFs digitales normales, que son
la mayoría del corpus habitual.

Notas de diseño:
- Se usa PyMuPDF para rasterizar en lugar de pdf2image, lo que elimina la
  dependencia de Poppler. Tesseract sigue siendo necesario como binario.
- Si Tesseract no está instalado, el módulo NO falla al importarse ni lanza
  excepción al consultarse: informa que no está disponible, para que el
  sistema pueda seguir funcionando y explicar el motivo al usuario.
"""

import os
import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    _IMPORTS_OK = True
    _IMPORT_ERR = ""
except Exception as e:  # pragma: no cover
    _IMPORTS_OK = False
    _IMPORT_ERR = str(e)

# Permite apuntar al ejecutable en Windows sin tenerlo en el PATH.
_TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()
if _IMPORTS_OK and _TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD


class OCRNoDisponible(RuntimeError):
    """El motor de OCR no está instalado o no es accesible."""


def ocr_disponible() -> tuple[bool, str]:
    """Indica si el OCR puede ejecutarse y, si no, por qué.

    Devuelve (disponible, motivo). El motivo está redactado para poder
    mostrarse directamente al usuario final.
    """
    if not _IMPORTS_OK:
        return False, "Faltan dependencias de Python para OCR (%s)." % _IMPORT_ERR
    try:
        version = pytesseract.get_tesseract_version()
    except Exception:
        return False, (
            "Tesseract OCR no está instalado o no está en el PATH. "
            "Instálalo y, si hace falta, indica su ruta en la variable "
            "TESSERACT_CMD del archivo .env."
        )
    return True, "Tesseract %s disponible." % version


def ocr_pdf_to_text(
    pdf_path: str,
    dpi: int = 300,
    lang: str = "spa+eng",
    max_pages: int = 30,
    max_chars: int = 120_000,
) -> str:
    """Convierte un PDF escaneado en texto mediante OCR.

    - pdf_path: ruta al PDF.
    - lang: idiomas de Tesseract; por defecto español e inglés combinados,
      que cubre el corpus académico habitual.
    - max_pages: tope de páginas, coherente con el extractor nativo.

    Lanza OCRNoDisponible si el motor no está instalado.
    """
    ok, motivo = ocr_disponible()
    if not ok:
        raise OCRNoDisponible(motivo)

    zoom = dpi / 72.0
    matriz = fitz.Matrix(zoom, zoom)

    partes: list[str] = []
    total = 0
    with fitz.open(pdf_path) as doc:
        paginas = min(max_pages, len(doc))
        for i in range(paginas):
            try:
                pix = doc[i].get_pixmap(matrix=matriz)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                txt = pytesseract.image_to_string(img, lang=lang)
            except Exception as e:
                # Una página ilegible no debe abortar el documento completo.
                partes.append("")
                continue
            if txt:
                partes.append(txt)
                total += len(txt)
            if total > max_chars:
                break

    return "\n".join(partes).strip()[:max_chars]
