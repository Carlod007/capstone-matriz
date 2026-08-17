# app/services/verificacion.py
"""
Nivel N2: fidelidad de la brecha a sus fuentes.

Parte de la distinción que ordena toda la capa de medición: una brecha bien
formulada contiene dos clases de afirmación, y solo una de ellas es
verificable contra el artículo.

  Evidencial   Lo que el artículo sí dice o hace.
               «El estudio valida el modelo con datos de un solo hospital.»
               Debe poder rastrearse hasta un fragmento concreto. Si no
               aparece en ninguno, es una alucinación.

  Inferencial  Lo que se concluye a partir de lo anterior.
               «Por tanto falta evidencia sobre generalización multicéntrica.»
               No puede verificarse contra el artículo, porque afirma
               justamente lo que el artículo no hace. Se valida contra el
               corpus y, en última instancia, contra juicio experto.

Medir ambas con la misma vara —que es lo que hacía la similitud coseno— hace
que ninguna quede bien medida.

Coste: una llamada por artículo. Se descompone, clasifica y verifica todo en
la misma petición en lugar de una por afirmación, porque el nivel gratuito
permite veinte generaciones al día y una verificación por afirmación agotaría
la cuota con dos artículos.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Sequence

MODE = os.getenv("GEMINI_MODE", "mock").lower()
VERIFICAR = os.getenv("VERIFICAR_FIDELIDAD", "1") not in ("0", "false", "False")

EVIDENCIAL = "evidencial"
INFERENCIAL = "inferencial"


SYS_PROMPT = """Eres un verificador de afirmaciones en revisiones de literatura científica.

Recibes una BRECHA de investigación redactada sobre un artículo, y los
FRAGMENTOS numerados de ese artículo que se usaron para redactarla.

Tu tarea tiene tres pasos:

1. DESCOMPONER la brecha en afirmaciones atómicas: cada una debe expresar un
   solo hecho o una sola conclusión.

   Cada afirmación tiene que entenderse SOLA, sin leer las demás. Está
   prohibido empezar por "Esto", "Ello", "Eso", "Dicho", "Lo anterior" o
   cualquier pronombre que remita a otra afirmación: sustituye el pronombre
   por aquello a lo que se refiere, aunque tengas que repetirlo en varias
   afirmaciones. Tampoco uses puntos suspensivos para recortar.

   Mal:  "Esto permite que las predicciones violen restricciones."
   Bien: "La ausencia de restricciones de capacidad enzimática permite que las
         predicciones de flujo violen restricciones bioquímicas."

   Es la regla más importante de este paso: una afirmación que ha perdido su
   sujeto no se puede comprobar contra ningún fragmento, y acabaría marcada
   como no respaldada por un defecto de redacción y no por falta de respaldo.

   Salvo por resolver esos pronombres, no reformules ni añadas nada.

2. CLASIFICAR cada afirmación:
   - "evidencial": describe lo que el artículo hace, dice, mide o reporta.
     Es comprobable contra los fragmentos.
   - "inferencial": concluye lo que falta, lo que no se ha estudiado o lo que
     debería hacerse. No es comprobable contra este artículo, porque afirma
     precisamente lo que el artículo no contiene.

3. VERIFICAR únicamente las evidenciales: indica si algún fragmento la
   respalda. Una afirmación está respaldada solo si el fragmento la sostiene
   de forma directa; que trate del mismo tema no basta.

Reglas:
- No inventes fragmentos. Si ninguno respalda la afirmación, "respaldada" es
  false y "fragmento" es null.
- Las inferenciales llevan siempre "respaldada": null y "fragmento": null.
- La cita debe ser literal del fragmento, como máximo 200 caracteres.
- Responde solo con JSON válido, sin texto adicional.

Formato exacto:
{
  "afirmaciones": [
    {
      "texto": "afirmación atómica",
      "tipo": "evidencial" | "inferencial",
      "respaldada": true | false | null,
      "fragmento": <número de fragmento> | null,
      "cita": "texto literal del fragmento" | null,
      "motivo": "una frase explicando la decisión"
    }
  ]
}"""


# Una afirmación que empieza por un pronombre sin antecedente perdió su sujeto
# al descomponerse. No es comprobable contra ningún fragmento, y contarla como
# "no respaldada" hunde la fidelidad por un defecto de redacción del propio
# verificador. Se detecta aquí para poder excluirla y, sobre todo, para que el
# defecto quede a la vista en lugar de disfrazarse de alucinación.
# Se queda corto a propósito. Solo entran los arranques que no aportan
# absolutamente nada por sí mismos:
#
#   - "Esto / Eso / Ello / Lo anterior": pronombres huecos, sin contenido.
#   - "Dicho / Dicha": significan literalmente "el ya mencionado".
#
# Quedan fuera "Este artículo…", "Estos autores…" o "Estas limitaciones…",
# que aunque remitan al contexto sí traen un sustantivo con el que buscar en
# los fragmentos. Excluirlas sería peor que incluirlas: subiría la fidelidad
# descartando afirmaciones que sí se podían comprobar, y una métrica que se
# infla sola no sirve para nada.
_SIN_SUJETO = re.compile(
    r"^\s*(esto|eso|ello|lo anterior|dicho|dicha|dichos|dichas)\b",
    re.IGNORECASE,
)


def _es_autonoma(texto: str) -> bool:
    """Si la afirmación se entiende sin leer las demás."""
    if _SIN_SUJETO.match(texto):
        return False
    # Los puntos suspensivos delatan un recorte: "se basan en... una
    # superestructura" no es una afirmación, es un fragmento de una.
    return "..." not in texto and "…" not in texto


@dataclass
class Afirmacion:
    texto: str
    tipo: str
    respaldada: bool | None = None
    fragmento: int | None = None
    cita: str | None = None
    motivo: str = ""
    # Se calcula, no lo decide el modelo.
    autonoma: bool = True

    def dict(self) -> dict:
        return asdict(self)


@dataclass
class Verificacion:
    afirmaciones: List[Afirmacion] = field(default_factory=list)
    disponible: bool = False
    motivo: str = ""
    usage: Dict[str, int] = field(default_factory=dict)

    # ---------------- métricas derivadas ----------------
    @property
    def evidenciales(self) -> List[Afirmacion]:
        return [a for a in self.afirmaciones if a.tipo == EVIDENCIAL]

    @property
    def inferenciales(self) -> List[Afirmacion]:
        return [a for a in self.afirmaciones if a.tipo == INFERENCIAL]

    @property
    def dependientes(self) -> List[Afirmacion]:
        """Afirmaciones que perdieron su sujeto al descomponerse."""
        return [a for a in self.afirmaciones if not a.autonoma]

    @property
    def fidelidad(self) -> float:
        """N2.1: proporción de afirmaciones evidenciales respaldadas.

        Es la métrica central del sistema. Una afirmación evidencial sin
        respaldo es, por definición, una alucinación.

        Se excluyen las que perdieron el sujeto al descomponerse. Sobre datos
        reales, cuatro de las cinco brechas de una prueba bajaron de 1.0 por
        afirmaciones como "Esto limita su fiabilidad": sin antecedente no hay
        fragmento que pueda respaldarlas, así que contarlas como alucinación
        atribuye al modelo un fallo que es del propio verificador. Cuántas se
        excluyeron aparece en `resumen()`, para que el defecto se vea en lugar
        de quedar disimulado en el número.
        """
        ev = [a for a in self.evidenciales if a.autonoma]
        if not ev:
            return 0.0
        return round(sum(1 for a in ev if a.respaldada) / len(ev), 4)

    @property
    def trazabilidad(self) -> float:
        """N2.2: proporción de afirmaciones vinculadas a un fragmento citable.

        Sin esto la herramienta no es auditable: el investigador no puede
        comprobar de dónde sale cada frase.
        """
        if not self.afirmaciones:
            return 0.0
        con_cita = sum(1 for a in self.afirmaciones
                       if a.fragmento is not None and (a.cita or "").strip())
        return round(con_cita / len(self.afirmaciones), 4)

    @property
    def equilibrio_evidencial(self) -> float:
        """N2.4: proporción de la brecha que se apoya en hechos del artículo.

        Una brecha compuesta solo por conclusiones no tiene nada que
        verificar: es especulación bien redactada. Un valor muy bajo avisa de
        eso aunque la fidelidad salga alta por tener una única evidencial.
        """
        if not self.afirmaciones:
            return 0.0
        return round(len(self.evidenciales) / len(self.afirmaciones), 4)

    def resumen(self) -> dict:
        return {
            "disponible": self.disponible,
            "motivo": self.motivo,
            "n_afirmaciones": len(self.afirmaciones),
            "n_evidenciales": len(self.evidenciales),
            "n_inferenciales": len(self.inferenciales),
            "n_sin_respaldo": sum(1 for a in self.evidenciales
                                  if a.autonoma and not a.respaldada),
            # Cuántas se descartaron por haber perdido el sujeto. Si esto sube,
            # el problema está en la descomposición, no en el modelo que
            # redactó la brecha.
            "n_dependientes": len(self.dependientes),
            "fidelidad": self.fidelidad,
            "trazabilidad": self.trazabilidad,
            "equilibrio_evidencial": self.equilibrio_evidencial,
            "afirmaciones": [a.dict() for a in self.afirmaciones],
        }


# ---------------------------------------------------------------- utilidades
def _bloque_fragmentos(fragmentos: Sequence[dict]) -> str:
    partes = []
    for i, f in enumerate(fragmentos, start=1):
        texto = " ".join((f.get("texto") or "").split())
        seccion = f.get("seccion") or "otro"
        partes.append("[%d] (%s) %s" % (i, seccion, texto[:1200]))
    return "\n\n".join(partes)


def _oraciones(texto: str) -> list[str]:
    partes = re.split(r"(?<=[\.\?\!])\s+", (texto or "").strip())
    return [p.strip() for p in partes if len(p.strip()) > 15]


# Marcas de conclusión: una afirmación que las contiene suele estar diciendo
# lo que falta, no lo que el artículo hace.
_MARCAS_INFERENCIALES = (
    "falta", "faltan", "carece", "carecen", "no se ha", "no existe",
    "no existen", "ausencia", "ausente", "seria necesario", "sería necesario",
    "se requiere", "deberia", "debería", "limita", "limitando", "impide",
    "por tanto", "por lo tanto", "lo que sugiere", "queda pendiente",
    "no aborda", "sin explorar", "brecha",
)


def _clasificar_heuristica(oracion: str) -> str:
    bajo = oracion.lower()
    return INFERENCIAL if any(m in bajo for m in _MARCAS_INFERENCIALES) else EVIDENCIAL


def _verificacion_simulada(brecha: str, fragmentos: Sequence[dict]) -> Verificacion:
    """Descomposición determinista para modo simulado y pruebas.

    No sustituye al juez: clasifica por palabras clave y comprueba solape de
    vocabulario. Sirve para ejercitar el recorrido completo sin gastar cuota,
    y por eso se marca como no disponible: un valor calculado así no debe
    presentarse como una medición.
    """
    from app.services.metricas.texto import tokens_contenido

    afirmaciones: List[Afirmacion] = []
    vocab = [set(tokens_contenido(f.get("texto") or "")) for f in fragmentos]

    for o in _oraciones(brecha):
        tipo = _clasificar_heuristica(o)
        af = Afirmacion(texto=o, tipo=tipo, motivo="clasificación simulada")
        if tipo == EVIDENCIAL:
            toks = set(tokens_contenido(o))
            mejor, mejor_i = 0.0, None
            for i, v in enumerate(vocab, start=1):
                if not toks or not v:
                    continue
                solape = len(toks & v) / len(toks)
                if solape > mejor:
                    mejor, mejor_i = solape, i
            af.respaldada = mejor >= 0.30
            if af.respaldada:
                af.fragmento = mejor_i
                af.cita = " ".join(
                    (fragmentos[mejor_i - 1].get("texto") or "").split())[:200]
        afirmaciones.append(af)

    return Verificacion(
        afirmaciones=afirmaciones,
        disponible=False,
        motivo=("Verificación simulada: clasifica por palabras clave y solape de "
                "vocabulario, no por comprensión. Los valores no son una medición."),
    )


# ---------------------------------------------------------------- juez real
def verificar(brecha: str, fragmentos: Sequence[dict]) -> Verificacion:
    """Descompone la brecha y comprueba qué parte se sostiene en las fuentes."""
    if not (brecha or "").strip():
        return Verificacion(disponible=False, motivo="La brecha está vacía.")
    if not fragmentos:
        return Verificacion(
            disponible=False,
            motivo="No hay fragmentos recuperados contra los que verificar.")
    if not VERIFICAR:
        return Verificacion(
            disponible=False,
            motivo="Verificación desactivada (VERIFICAR_FIDELIDAD=0).")
    if MODE != "real":
        return _verificacion_simulada(brecha, fragmentos)

    from google.genai import types

    from app.services.gemini_service import CHAT_MODEL, _get_client, _resp_text, _usage
    from app.services.limitador import con_reintentos, limitador_generacion
    from app.services.registro_api import OP_VERIFICACION, anotar

    cliente = _get_client()
    prompt = (
        "BRECHA A VERIFICAR:\n%s\n\n"
        "FRAGMENTOS DEL ARTÍCULO:\n%s"
        % (brecha.strip(), _bloque_fragmentos(fragmentos))
    )

    limitador_generacion.adquirir(1)

    def _llamar():
        try:
            r = cliente.models.generate_content(
                model=CHAT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYS_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0,  # verificar no es tarea creativa
                ),
            )
        except Exception as exc:
            anotar(OP_VERIFICACION, modelo=CHAT_MODEL, exito=False, motivo=str(exc))
            raise
        u = _usage(r)
        anotar(OP_VERIFICACION, modelo=CHAT_MODEL, exito=True,
               tokens_in=u["tokens_in"], tokens_out=u["tokens_out"])
        return r

    try:
        resp = con_reintentos(_llamar, descripcion="verificar fidelidad")
    except Exception as exc:
        # Que falle la verificación no debe invalidar el análisis: es una
        # medición sobre él, no parte del resultado.
        return Verificacion(disponible=False,
                            motivo="No se pudo verificar: %s" % str(exc)[:200])

    return _interpretar(_resp_text(resp), _usage(resp), len(fragmentos))


def _interpretar(bruto: str, usage: dict, n_fragmentos: int) -> Verificacion:
    """Convierte la respuesta del juez en afirmaciones, descartando lo inválido."""
    texto = (bruto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-z]*\s*|\s*```$", "", texto)

    try:
        datos: Any = json.loads(texto)
    except Exception:
        return Verificacion(disponible=False,
                            motivo="El verificador no devolvió JSON válido.")

    crudas = datos.get("afirmaciones") if isinstance(datos, dict) else None
    if not isinstance(crudas, list) or not crudas:
        return Verificacion(disponible=False,
                            motivo="El verificador no devolvió afirmaciones.")

    afirmaciones: List[Afirmacion] = []
    for c in crudas:
        if not isinstance(c, dict):
            continue
        texto_af = (c.get("texto") or "").strip()
        if not texto_af:
            continue
        tipo = c.get("tipo")
        tipo = tipo if tipo in (EVIDENCIAL, INFERENCIAL) else EVIDENCIAL

        frag = c.get("fragmento")
        # Un numero de fragmento fuera de rango sería una cita inventada.
        if not isinstance(frag, int) or not (1 <= frag <= n_fragmentos):
            frag = None

        respaldada = c.get("respaldada")
        if tipo == INFERENCIAL:
            respaldada, frag = None, None
        elif not isinstance(respaldada, bool):
            respaldada = False
        if respaldada is False:
            frag = None

        afirmaciones.append(Afirmacion(
            texto=texto_af,
            tipo=tipo,
            respaldada=respaldada,
            fragmento=frag,
            cita=((c.get("cita") or "").strip()[:200] or None) if frag else None,
            motivo=(c.get("motivo") or "").strip()[:300],
            autonoma=_es_autonoma(texto_af),
        ))

    if not afirmaciones:
        return Verificacion(disponible=False,
                            motivo="Ninguna afirmación del verificador era utilizable.")

    return Verificacion(afirmaciones=afirmaciones, disponible=True, usage=usage)
