# app/services/text_cleaning.py
import re, unicodedata

REF_SPLIT = re.compile(r"\n\s*(references|bibliography|referencias)\b.*", re.I | re.S)

def normalize_basic(text: str) -> str:
    """Normaliza texto para métricas: NFKC, minúsculas, quita ruido."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)

    # cortar desde "Referencias/References" para no sesgar métrica
    t = REF_SPLIT.sub("", t)

    # unir cortes por guion al final de línea: "inves-\ntigación" -> "investigación"
    t = re.sub(r"-\s*\n\s*", "", t)

    # volver saltos duros a espacios
    t = t.replace("\r", " ").replace("\n", " ")

    # quitar URLs y correos
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", " ", t)

    # comprimir espacios
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t
