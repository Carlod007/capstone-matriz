# app/utils/chunker.py
"""
Fragmentación del texto de un artículo.

Además del texto de cada fragmento se devuelve su posición en el documento
original, lo que permite atribuirle una sección y, más adelante, enlazar una
afirmación generada con el párrafo exacto que la sustenta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Fragmento:
    texto: str
    inicio: int  # desplazamiento en el texto de origen
    fin: int


def split_into_chunks(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """Compatibilidad: devuelve solo el texto de cada fragmento."""
    return [f.texto for f in fragmentar(text, max_chars=max_chars, overlap=overlap)]


def fragmentar(text: str, max_chars: int = 1200, overlap: int = 200) -> list[Fragmento]:
    """Divide el texto conservando la posición de cada fragmento.

    Se corta en el final de oración más cercano al límite. A diferencia de la
    versión anterior, el solapamiento se aplica siempre: antes, la expresión
    `start = max(cut - overlap, cut)` se resolvía invariablemente en `cut`, de
    modo que el solapamiento configurado nunca llegaba a aplicarse y las
    oraciones que caían justo en el corte quedaban partidas entre fragmentos
    sin contexto compartido.
    """
    if not text:
        return []

    # Se normalizan los espacios conservando la correspondencia de posiciones
    # con el texto original mediante un mapa de índices.
    limpio_chars: list[str] = []
    mapa: list[int] = []
    espacio_previo = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if espacio_previo:
                continue
            limpio_chars.append(" ")
            mapa.append(i)
            espacio_previo = True
        else:
            limpio_chars.append(ch)
            mapa.append(i)
            espacio_previo = False

    limpio = "".join(limpio_chars).strip()
    if not limpio:
        return []

    # Ajusta el mapa si strip() eliminó espacios al inicio.
    desfase = len("".join(limpio_chars)) - len("".join(limpio_chars).lstrip())
    mapa = mapa[desfase:desfase + len(limpio)]

    fragmentos: list[Fragmento] = []
    n = len(limpio)
    inicio = 0
    paso_minimo = max(1, max_chars - overlap)

    while inicio < n:
        fin = min(inicio + max_chars, n)
        if fin < n:
            corte = limpio.rfind(". ", inicio + int(max_chars * 0.5), fin)
            if corte != -1:
                fin = corte + 1
        cuerpo = limpio[inicio:fin].strip()
        if cuerpo:
            ini_orig = mapa[inicio] if inicio < len(mapa) else 0
            fin_orig = mapa[min(fin, len(mapa)) - 1] + 1 if mapa else 0
            fragmentos.append(Fragmento(cuerpo, ini_orig, fin_orig))
        if fin >= n:
            break
        inicio = max(inicio + paso_minimo, fin - overlap)

    return fragmentos
