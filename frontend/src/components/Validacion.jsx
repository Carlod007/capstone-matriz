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
import { abrirPdfArticulo } from "../utils/abrirPdf";

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

/**
 * Abre el PDF original del artículo en otra pestaña.
 *
 * No sirve un enlace normal: el endpoint pide sesión y el navegador no manda
 * la cabecera de autorización al seguir un `href`. Se descarga con `fetch`,
 * que sí la lleva, y se abre el resultado desde la memoria del navegador.
 *
 * En otra pestaña y no dentro de la página a propósito: al anotar se está
 * leyendo el artículo y decidiendo a la vez, y eso pide dos ventanas, no un
 * recuadro pequeño debajo del formulario.
 */
function Fila({ brecha, proyectoId, onCambio, onError }) {
  const [veredicto, setVeredicto] = useState(brecha.veredicto || null);
  const [motivo, setMotivo] = useState(brecha.justificacion || "");
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState(null);
  const [pdf, setPdf] = useState(null);
  // Cómo se llegó al veredicto. Las dos formas cuentan igual; se registra para
  // que dentro de unos meses se sepa cómo se hizo cada revisión.
  const [origen, setOrigen] = useState(brecha.origen || null);

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
          body: JSON.stringify({ veredicto, justificacion: motivo, origen }),
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

      {/* Junto a la brecha y no en otra pantalla: juzgarla exige tener el
          artículo delante, y hasta ahora había que buscarlo en el ordenador,
          con el riesgo de leer una versión distinta de la analizada. */}
      {brecha.articulo_id && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => abrirPdfArticulo(brecha.articulo_id, setPdf)}
            className="rounded-lg border border-acento-borde bg-acento-claro px-2.5 py-1 text-xs font-medium text-acento-fuerte transition-colors hover:border-acento"
          >
            {pdf === "abriendo" ? "Abriendo…" : "Leer el artículo (PDF)"}
          </button>
          {pdf && pdf !== "abriendo" && (
            <span className="text-[11px] text-mal">{pdf}</span>
          )}
        </div>
      )}

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
          {/* Cómo se revisó. No pondera nada: las dos cuentan igual en el
              porcentaje. Es un dato del procedimiento, y si no se registra al
              anotar se pierde para siempre. */}
          <div className="mt-2.5">
            <span className="block text-xs text-tinta-suave">
              ¿Cómo la revisaste?
            </span>
            <div className="mt-1 flex flex-wrap gap-2">
              {[
                ["lectura", "Leyendo el artículo"],
                ["asistida", "Con ayuda de una herramienta"],
              ].map(([valor, etiqueta]) => (
                <button
                  key={valor}
                  type="button"
                  onClick={() => setOrigen(valor)}
                  className={`rounded-lg border px-2.5 py-1 text-xs transition-colors ${
                    origen === valor
                      ? "border-acento bg-acento-claro text-acento-fuerte"
                      : "border-borde bg-hundido text-tinta-media hover:text-tinta"
                  }`}
                >
                  {etiqueta}
                </button>
              ))}
            </div>
          </div>

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
        {/* Mientras falten brechas no hay resultado que enseñar. Quien anota
            viendo su porcentaje acumulado deja de juzgar cada brecha por
            separado: con cuatro correctas seguidas cuesta poner la quinta en
            duda. El servidor tampoco lo envía, así que la ceguera es del
            procedimiento y no de la maquetación. */}
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          {r.revision_completa ? (
            <div>
              <div className="text-2xl font-semibold tabular-nums text-acento">
                {r.acierto === null || r.acierto === undefined
                  ? "—"
                  : `${Math.round(r.acierto * 100)} %`}
              </div>
              <div className="text-xs text-tinta-suave">
                de acierto sobre las {r.total} brechas
              </div>
            </div>
          ) : (
            <div>
              <div className="text-2xl font-semibold tabular-nums text-tinta">
                {r.anotadas}
                <span className="text-base font-normal text-tinta-suave">
                  {" "}/ {r.total}
                </span>
              </div>
              <div className="text-xs text-tinta-suave">revisadas</div>
            </div>
          )}
          <div className="text-sm text-tinta-media">
            {r.revision_completa ? (
              <>Revisión terminada</>
            ) : (
              <>
                Faltan {r.pendientes}. El resultado aparece al terminar, para
                que tu juicio no quede condicionado por el marcador.
              </>
            )}
          </div>
        </div>

        {/* La limitación se declara aquí y no en una nota al pie. Con un solo
            anotador no hay acuerdo entre jueces que medir, y esa es la primera
            pregunta que hace un tribunal. Decirlo antes vale más que
            defenderlo después. */}
        <p className="mt-3 border-t border-borde pt-3 text-xs leading-relaxed text-tinta-suave">
          {r.revision_completa ? (
            <>
              Este porcentaje sale del juicio humano, no del sistema; «parcial»
              cuenta medio punto.{" "}
            </>
          ) : (
            <>
              Aquí no se muestran las métricas del sistema a propósito: verlas
              antes de decidir condiciona el juicio, y entonces compararlas
              después no mide su acierto sino su eco.{" "}
            </>
          )}
          {r.anotadores === 0
            ? "Todavía no hay anotaciones humanas para esta ejecución."
            : r.anotadores === 1
              ? "Solo una persona ha anotado esta ejecución; no hay acuerdo entre jueces que medir."
              : `${r.anotadores} personas han anotado esta ejecución; el acuerdo entre jueces aún no se calcula.`}{" "}
          Conviene declararlo como limitación del estudio.
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

      {r.revision_completa && (
        <Comparacion proyectoId={proyectoId} onError={onError} />
      )}
    </div>
  );
}

/**
 * El juicio humano junto a lo que midió el sistema.
 *
 * Solo al terminar. Es el premio de haber anotado a ciegas: hasta aquí las dos
 * columnas se formaron sin verse, así que compararlas dice algo. Enseñarlas
 * durante la revisión habría convertido la segunda en un espejo de la primera.
 */
function Comparacion({ proyectoId, onError }) {
  const [datos, setDatos] = useState(null);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    if (!abierto || datos) return;
    (async () => {
      try {
        const r = await api(
          `${API_BASE}/proyectos/${proyectoId}/validacion/comparacion`,
        );
        if (r.ok) setDatos(await r.json());
      } catch (e) {
        onError?.(e);
      }
    })();
  }, [abierto, datos, proyectoId, onError]);

  const etiqueta = {
    correcta: "text-bien",
    parcial: "text-aviso",
    incorrecta: "text-mal",
  };

  return (
    <div className="rounded-xl border border-acento-borde bg-acento-claro p-4">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="text-sm font-medium text-acento-fuerte hover:underline"
      >
        {abierto ? "Ocultar" : "Ver"} tu juicio frente a las métricas
      </button>

      {abierto && datos && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-tinta-suave">
              <tr>
                <th className="py-1 pr-3 font-medium">Artículo</th>
                <th className="py-1 pr-3 font-medium">Tú</th>
                <th className="py-1 pr-3 font-medium tabular-nums">N2.1</th>
                <th className="py-1 pr-3 font-medium tabular-nums">N2.5</th>
                <th className="py-1 font-medium">N2.6</th>
              </tr>
            </thead>
            <tbody className="text-tinta-media">
              {datos.brechas.map((b) => (
                <tr key={b.id} className="border-t border-acento-borde">
                  <td className="max-w-[18rem] truncate py-1.5 pr-3">
                    {b.articulo}
                  </td>
                  <td
                    className={`py-1.5 pr-3 font-medium ${
                      etiqueta[b.veredicto] || ""
                    }`}
                  >
                    {b.veredicto || "—"}
                  </td>
                  <td className="py-1.5 pr-3 tabular-nums">
                    {b.metricas?.["N2.1"]?.toFixed(3) ?? "—"}
                  </td>
                  <td className="py-1.5 pr-3 tabular-nums">
                    {b.metricas?.["N2.5"]?.toFixed(3) ?? "—"}
                  </td>
                  <td className="py-1.5">
                    {b.metricas?.["N2.6"] === 1 ? "ya resuelta" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] leading-relaxed text-acento-fuerte">
            Donde tu veredicto y las métricas discrepan está la información
            útil: o la métrica no ve algo, o lo ve y no sabemos leerlo.
          </p>
        </div>
      )}
    </div>
  );
}
