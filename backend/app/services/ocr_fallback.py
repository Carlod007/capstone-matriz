# app/services/ocr_fallback.py
"""
OCR de respaldo para PDFs escaneados.
Solo se activa cuando el extractor base (pdfminer, etc.) devuelve poco texto.
"""

from pdf2image import convert_from_path
import pytesseract

def ocr_pdf_to_text(pdf_path: str, dpi: int = 300, lang: str = "spa") -> str:
    """
    Convierte un PDF en texto usando OCR.
    - pdf_path: ruta al PDF.
    - lang: idioma (usa 'spa' si instalaste paquete español de Tesseract).
    Retorna texto concatenado de todas las páginas.
    """
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
    except Exception as e:
        raise RuntimeError(f"Error al convertir PDF a imágenes: {e}")

    chunks = []
    for img in pages:
        try:
            txt = pytesseract.image_to_string(img, lang=lang)
            chunks.append(txt)
        except Exception as e:
            chunks.append(f"[ERROR OCR página]: {e}")
    return "\n".join(chunks)
