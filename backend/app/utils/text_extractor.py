# app/utils/text_extractor.py
import re, fitz
from pdfminer.high_level import extract_text as pdfminer_extract

def clean_text(txt: str) -> str:
    """Limpieza básica: elimina saltos duplicados, números de página y secciones de referencias."""
    txt = re.sub(r'\n{2,}', '\n', txt)  # colapsa saltos
    txt = re.sub(r'Page \d+|Página \d+', '', txt, flags=re.IGNORECASE)
    txt = re.sub(r'References\b.*', '', txt, flags=re.IGNORECASE | re.DOTALL)  # corta referencias
    return txt.strip()

def extract_full_text(pdf_path: str, max_chars: int = 120_000) -> str:
    # 1) PyMuPDF
    out = []
    try:
        with fitz.open(pdf_path) as doc:
            pages = min(30, len(doc))
            for i in range(pages):
                text = doc[i].get_text("text")
                if text:
                    out.append(text)
                if sum(len(x) for x in out) > max_chars:
                    break
    except Exception:
        pass
    txt = "\n".join(out)

    # 2) Si PyMuPDF falla o da poco texto, usa pdfminer
    if len(txt.strip()) < 300:
        try:
            txt = pdfminer_extract(pdf_path) or ""
        except Exception:
            pass

    # 3) Limpiar texto
    txt = clean_text(txt)
    if len(txt) > max_chars:
        txt = txt[:max_chars]
    return txt
