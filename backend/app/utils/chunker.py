# app/utils/chunker.py
import re

def split_into_chunks(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        # intenta cortar en punto cercano
        cut = text.rfind('.', start, end)
        if cut == -1 or cut <= start + 300:
            cut = end
        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)
        start = max(cut - overlap, cut)
    return chunks
