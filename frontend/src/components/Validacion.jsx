import { useCallback, useEffect, useState } from "react";

/**
 * Anotación humana de las brechas (nivel N6).
 *
 * Todas las demás métricas comparan al sistema consigo mismo: dicen si es
 * consistente, no si acierta. Esta pantalla es la única que puede decir lo
 * segundo, y hace falta alguien que se haya leído los artículos.
 *
 * Está diseñada alrededor de la justificación, no del porcentaje. Un «esta
 * está mal» sin motivo no permite corregir el sistema ni sostener la
 * evaluación en una defensa; con el motivo escrito, cada brecha rechazada es
 * una línea del capítulo de resultados.
 */

import { api } from "../sesion";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const VEREDICTOS = [
  {
    valor: "correcta",
    etiqueta: "Correcta",
    ayuda: "La brecha existe y está bien descrita.",
    activo: "border-bien bg-bien-claro text-bien",
  },
  {
    valor: "parcial",
    etiqueta: "Parcial",
    ayuda: "Acierta el problema pero falla en algún matiz.",
    activo: "border-aviso bg-aviso-claro text-aviso",
  },
  {
    valor: "incorrecta",
    etiqueta: "Incorrecta",
    ayuda: "No se sostiene: el artículo no dice eso.",
    activo: "border-mal bg-mal-claro text-mal",
  },
];

function Fila({ brecha, proyectoId, onCambio, onError }) {
  const [veredicto, setVeredicto] = useState(brecha.veredicto || null);
  const [motivo, setMotivo] = useState(brecha.justificacion || "");
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState(null);

  // «Correcta» no necesita motivo: no hay nada que objetar. Los otros dos sí,
  // y el servidor los rechaza sin él; conviene decirlo aquí antes de que el
  // usuario escriba y reciba un error.
  const exigeMotivo = veredicto === "parcial" || veredicto === "incorrecta";
  const puedeGuardar =
    veredicto && (!exigeMotivo || motivo.trim().length > 0) && !guardando;

  async function guardar() {
    setGuardando(true);
    setAviso(null);
    try {
      const r = await api(
        `${API_BASE}/proyectos/${proyectoId}/validacion/${brecha.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ veredicto, justificacion: motivo }),
        },
      );
      const cuerpo = await r.json().catch(() => null);
      if (!r.ok) {
        setAviso(cuerpo?.detail || `No se pudo guardar (error ${r.status})`);
        return;
      }
      setAviso("Guardado");
      onCambio(cuerpo?.resumen);
    } catch (e) {
      onError(e);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <article className="rounded-xl border border-borde bg-superficie p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-tinta">{brecha.articulo}</h3>
        <span className="text-[11px] uppercase tracking-wide text-tinta-suave">
          {brecha.tipo_brecha}
        </span>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-tinta-media">
        {brecha.brecha}
      </p>
      {brecha.oportunidad && (
        <p className="mt-1.5 text-xs leading-relaxed text-tinta-suave">
          <span className="font-medium">Oportunidad:</span> {brecha.oportunidad}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {VEREDICTOS.map((v) => (
          <button
            key={v.valor}
            type="button"
            title={v.ayuda}
            onClick={() => setVeredicto(v.valor)}
            className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
              veredicto === v.valor
                ? v.activo
                : "border-borde bg-hundido text-tinta-media hover:text-tinta"
            }`}
          >
            {v.etiqueta}
          </button>
        ))}
      </div>

      {veredicto && (
        <div className="mt-3">
          <label className="block text-xs text-tinta-suave">
            {exigeMotivo ? "Qué falla (obligatorio)" : "Comentario (opcional)"}
          </label>
          <textarea
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            rows={2}
            placeholder={
              exigeMotivo
                ? "El artículo sí evalúa ese caso, en la sección de resultados…"
                : ""
            }
            className="mt-1 w-full rounded-lg border border-borde bg-superficie px-3 py-2 text-sm text-tinta outline-none transition-colors placeholder:text-tinta-suave focus:border-acento"
          />
          <div className="mt-2 flex items-center gap-3">
            <button
              type="button"
              disabled={!puedeGuardar}
              onClick={guardar}
              className="rounded-lg border border-acento bg-acento px-3 py-1.5 text-sm font-medium text-papel transition-colors hover:bg-acento-fuerte disabled:opacity-45 disabled:cursor-not-allowed"
            >
              {guardando ? "Guardando…" : "Guardar"}
            </button>
            {aviso && (
              <span
                className={`text-xs ${
                  aviso === "Guardado" ? "text-bien" : "text-mal"
                }`}
              >
                {aviso}
              </span>
            )}
            {brecha.otros_anotadores > 0 && (
              <span className="text-[11px] text-tinta-suave">
                Otra persona ya anotó esta brecha. Su veredicto no se muestra
                hasta que emitas el tuyo.
              </span>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

export default function Validacion({ proyectoId, onError }) {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const r = await api(`${API_BASE}/proyectos/${proyectoId}/validacion`);
      setDatos(r.ok ? await r.json() : null);
    } catch (e) {
      onError?.(e);
    } finally {
      setCargando(false);
    }
  }, [proyectoId, onError]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (cargando) {
    return <p className="text-sm text-tinta-suave">Cargando brechas…</p>;
  }
  if (!datos?.brechas?.length) {
    return (
      <p className="text-sm text-tinta-suave">
        Todavía no hay brechas que revisar. Analiza el proyecto primero.
      </p>
    );
  }

  const r = datos.resumen || {};

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-borde bg-superficie p-4">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <div>
            <div className="text-2xl font-semibold tabular-nums text-acento">
              {r.acierto === null || r.acierto === undefined
                ? "—"
                : `${Math.round(r.acierto * 100)} %`}
            </div>
            <div className="text-xs text-tinta-suave">
              de acierto sobre lo que llevas revisado
            </div>
          </div>
          <div className="text-sm text-tinta-media">
            {r.anotadas} de {r.total} brechas revisadas
            {r.pendientes > 0 && (
              <span className="text-tinta-suave"> · faltan {r.pendientes}</span>
            )}
          </div>
        </div>

        {/* La limitación se declara aquí y no en una nota al pie. Con un solo
            anotador no hay acuerdo entre jueces que medir, y esa es la primera
            pregunta que hace un tribunal. Decirlo antes vale más que
            defenderlo después. */}
        <p className="mt-3 border-t border-borde pt-3 text-xs leading-relaxed text-tinta-suave">
          Este porcentaje sale de tu juicio, no del sistema. Se calcula sobre
          las brechas que ya has revisado —«parcial» cuenta medio punto—, así
          que mientras queden pendientes es provisional. Con{" "}
          {r.anotadores === 1 ? "un solo anotador" : `${r.anotadores} anotadores`}{" "}
          no hay acuerdo entre jueces que medir: conviene declararlo como
          limitación del estudio.
        </p>
      </div>

      <div className="space-y-3">
        {datos.brechas.map((b) => (
          <Fila
            key={b.id}
            brecha={b}
            proyectoId={proyectoId}
            onCambio={(resumen) =>
              resumen && setDatos((d) => ({ ...d, resumen }))
            }
            onError={onError}
          />
        ))}
      </div>
    </div>
  );
}
