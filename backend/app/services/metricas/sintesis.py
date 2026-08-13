# app/services/metricas/sintesis.py
"""
Nivel N5: tipificación y síntesis.

Son las dos salidas del sistema que hasta ahora no tenían ninguna métrica: el
tipo asignado a cada brecha y el estado del arte redactado a partir de todas.

De la tipificación no se puede medir todavía la exactitud, porque hace falta
un conjunto anotado por expertos y eso llega en N6. Sí se puede medir algo que
estaba sin comprobar desde el principio: el reclasificador por palabras clave
sobrescribe la decisión del modelo, y nadie sabía con qué frecuencia lo hace.
Conservarlo sin medirlo es una suposición, no una decisión.

Del estado del arte se mide lo que puede comprobarse sin juicio experto: si
representa todas las brechas del lote y si inventa referencias bibliográficas.
El prompt prohíbe inventarlas; hasta ahora nada verificaba que se cumpliera.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Sequence

from app.services.embedding_service import _cos, _embed_texts
from app.services.metricas.texto import sin_tildes, tokens_contenido


# ================================================================ N5.2
def n5_2_efecto_reclasificador(tipo_modelo: str | None, tipo_final: str | None) -> float:
    """1.0 si el reclasificador cambió la decisión del modelo, 0.0 si no.

    Agregado sobre el proyecto da la tasa de intervención. Un valor alto
    significa que la etiqueta final la decide un contador de palabras clave y
    no el modelo, lo que conviene saber antes de dar por buena la
    tipificación.
    """
    if not tipo_modelo or not tipo_final:
        return 0.0
    return 1.0 if tipo_modelo != tipo_final else 0.0


# ================================================================ N5.3
def _parrafos(texto: str, minimo: int = 120) -> List[str]:
    crudos = re.split(r"\n\s*\n|\n(?=#)", texto or "")
    salida = []
    for c in crudos:
        limpio = " ".join(c.split())
        if len(limpio) >= minimo:
            salida.append(limpio)
    return salida or ([" ".join((texto or "").split())] if (texto or "").strip() else [])


def n5_3_cobertura_sintesis(estado_arte: str, brechas: Sequence[str],
                            umbral: float = 0.55) -> tuple[float, dict]:
    """Qué proporción de las brechas está representada en el estado del arte.

    Detecta que la síntesis ignore artículos: con diez brechas de entrada y
    una redacción que solo recoge seis, el texto parece completo y no lo está.
    """
    textos = [b for b in brechas if (b or "").strip()]
    parrafos = _parrafos(estado_arte)
    if not textos or not parrafos:
        return 0.0, {"motivo": "faltan brechas o estado del arte"}

    vectores = _embed_texts(textos + parrafos)
    v_brechas = vectores[:len(textos)]
    v_parrafos = vectores[len(textos):]

    detalle = []
    representadas = 0
    for i, vb in enumerate(v_brechas):
        if not vb:
            continue
        mejor = max((_cos(vb, vp) for vp in v_parrafos if vp), default=0.0)
        if mejor >= umbral:
            representadas += 1
        detalle.append({"brecha": textos[i][:90], "mejor_similitud": round(mejor, 4)})

    detalle.sort(key=lambda d: d["mejor_similitud"])
    return round(representadas / len(textos), 4), {
        "umbral": umbral,
        "n_brechas": len(textos),
        "n_representadas": representadas,
        "menos_representadas": detalle[:5],
    }


# ================================================================ N5.5
# Formas habituales de cita. El prompt de sintesis prohibe inventar
# referencias, asi que cualquiera de estas en el texto generado merece
# revision: o procede de los articulos del proyecto o esta inventada.
_PATRONES_CITA = (
    ("doi", re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")),
    ("numerica", re.compile(r"\[\d{1,3}(?:\s*[,\-]\s*\d{1,3})*\]")),
    ("autor_anio", re.compile(
        r"\(([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\-]+(?:\s+(?:et\s+al\.?|y|and|&)\s*"
        r"[A-Za-zÁÉÍÓÚÑáéíóúñ\-]*)?),?\s*(19|20)\d{2}[a-z]?\)")),
    ("et_al", re.compile(
        r"\b[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\-]+\s+et\s+al\.?\s*\((19|20)\d{2}\)")),
)


@dataclass
class Citas:
    encontradas: List[dict] = field(default_factory=list)
    reconocidas: int = 0
    inventadas: int = 0

    def dict(self) -> dict:
        return asdict(self)


def n5_5_citas_fabricadas(estado_arte: str,
                          articulos: Sequence[dict]) -> tuple[float, dict]:
    """Proporción de citas del estado del arte que no corresponde a un artículo.

    Devuelve 0.0 cuando no hay ninguna cita, que es lo esperado: el prompt las
    prohíbe. Un valor alto indica referencias inventadas, el fallo más grave
    posible en una herramienta de revisión de literatura.
    """
    texto = estado_arte or ""
    dois = {(a.get("doi") or "").lower().strip() for a in articulos if a.get("doi")}
    titulos = [sin_tildes((a.get("titulo") or "").lower()) for a in articulos]
    vocab_titulos = [set(tokens_contenido(t)) for t in titulos if t]

    c = Citas()
    for clase, patron in _PATRONES_CITA:
        for m in patron.finditer(texto):
            bruto = m.group(0)
            reconocida = False

            if clase == "doi":
                reconocida = bruto.lower().strip(".,;)") in dois
            else:
                # Una cita de autor o numerica se acepta si el entorno remite a
                # alguno de los articulos del proyecto; si no, no hay forma de
                # saber a que apunta.
                ventana = sin_tildes(
                    texto[max(0, m.start() - 220):m.end() + 220].lower())
                toks = set(tokens_contenido(ventana))
                for v in vocab_titulos:
                    if v and len(toks & v) / max(1, len(v)) >= 0.30:
                        reconocida = True
                        break

            c.encontradas.append({"clase": clase, "texto": bruto[:120],
                                  "reconocida": reconocida})
            if reconocida:
                c.reconocidas += 1
            else:
                c.inventadas += 1

    if not c.encontradas:
        return 0.0, {"n_citas": 0,
                     "nota": "Sin citas en el texto, que es lo que pide el prompt."}
    return round(c.inventadas / len(c.encontradas), 4), {
        "n_citas": len(c.encontradas),
        "reconocidas": c.reconocidas,
        "sin_correspondencia": c.inventadas,
        "muestra": c.encontradas[:12],
    }
