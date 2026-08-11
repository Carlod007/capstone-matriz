import { useEffect, useState } from "react";

/**
 * Presentación de la capa de medición v2.
 *
 * El panel anterior mostraba entropía, similitud y score de validación, que
 * son las tres métricas retiradas: llegaban siempre en cero y la interfaz
 * parecía averiada sin estarlo.
 *
 * Aquí se aplican dos criterios:
 *
 * 1. Cada métrica se muestra con su nombre y su dirección de lectura. No
 *    todas mejoran al subir, y pintar de verde lo que va mal es peor que no
 *    pintar nada.
 * 2. Se muestra el rango intercuartílico junto a la mediana. Una media de
 *    0.86 con dispersión nula y otra con dispersión amplia dicen cosas
 *    opuestas, y presentarlas igual fue lo que ocultó el problema original.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/* ---------------------------------------------------------------- utilidades */
function fmt(v, decimales = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(decimales);
}

/** Métricas destacadas en las tarjetas superiores, por orden de interés. */
const DESTACADAS = ["N3.1", "N1.2", "N3.2", "N4.2"];

/* ---------------------------------------------------------------- piezas */
function Etiqueta({ children, tono = "gris" }) {
  const tonos = {
    gris: "bg-gray-100 text-gray-700 border-gray-200",
    verde: "bg-green-50 text-green-800 border-green-200",
    ambar: "bg-amber-50 text-amber-800 border-amber-200",
    azul: "bg-blue-50 text-blue-800 border-blue-200",
  };
  return (
    <span
      className={`inline-block text-[11px] leading-none px-2 py-[3px] rounded-full border ${
        tonos[tono] || tonos.gris
      }`}
    >
      {children}
    </span>
  );
}

function Tarjeta({ metrica }) {
  if (!metrica) return null;
  const { nombre, mediana, iqr, discrimina, descripcion, rango, n } = metrica;
  return (
    <div className="border rounded-lg p-3 bg-white shadow-sm" title={descripcion}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-gray-600 text-sm leading-tight">{nombre}</div>
        <Etiqueta tono={discrimina ? "verde" : "ambar"}>
          {discrimina ? "discrimina" : "poca variación"}
        </Etiqueta>
      </div>
      <div className="text-2xl font-semibold mt-1">{fmt(mediana)}</div>
      <div className="text-[11px] text-gray-500 mt-1">
        mediana · IQR {fmt(iqr)} · n={n} · {rango}
      </div>
    </div>
  );
}

/** Explica por qué el estado de validación es "pendiente". */
export function AvisoValidacion() {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <div className="font-medium mb-1">
        La validación automática está desactivada a propósito
      </div>
      <p className="leading-relaxed">
        Las reglas anteriores se apoyaban en umbrales que nunca llegaban a
        activarse, de modo que casi toda brecha acababa marcada como aceptada
        sin haber sido validada. Hasta calibrarlos contra criterio experto, el
        sistema prefiere declararse indeciso antes que dar por buena una
        brecha que no ha comprobado.
      </p>
    </div>
  );
}

/**
 * Consumo de API frente al límite diario del nivel gratuito.
 *
 * Incluye el desglose porque decir "cuesta 6" sin explicar de dónde sale ese
 * 6 obliga a adivinar si depende del número de artículos, de su tamaño o de
 * los PDF indexados.
 */
export function IndicadorConsumo({ proyectoId }) {
  const [d, setD] = useState(null);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    let vivo = true;
    fetch(`${API_BASE}/proyectos/${proyectoId}/consumo`)
      .then((r) => (r.ok ? r.json() : null))
      .then((x) => vivo && setD(x))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [proyectoId]);

  if (!d) return null;
  const alcanza = d.alcanza_para_otra_ejecucion;
  const usadas = d.generaciones_estimadas;
  const tope = d.limite_diario_nivel_gratuito;
  const pct = Math.min(100, Math.round((usadas / Math.max(1, tope)) * 100));

  return (
    <div
      className={`rounded-lg border p-3 text-sm ${
        alcanza
          ? "border-gray-200 bg-white text-gray-700"
          : "border-red-300 bg-red-50 text-red-800"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">Consumo de API (24 h)</span>
        <span className="tabular-nums">
          {usadas} / {tope}
        </span>
      </div>

      <div className="mt-2 h-1.5 w-full rounded-full bg-gray-200 overflow-hidden">
        <div
          className={`h-full ${alcanza ? "bg-blue-500" : "bg-red-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="text-[11px] mt-2 leading-relaxed">
        Analizar este proyecto cuesta{" "}
        <b>{d.coste_de_una_ejecucion} generaciones</b>.{" "}
        {alcanza
          ? `Quedan ${d.restantes_estimadas}: alcanza para otra ejecución.`
          : `Quedan ${d.restantes_estimadas}: no alcanza hasta mañana.`}
      </div>

      <button
        onClick={() => setAbierto((v) => !v)}
        className="mt-2 text-[11px] text-blue-700 hover:underline"
      >
        {abierto ? "Ocultar" : "¿Qué cuenta como generación?"}
      </button>

      {abierto && (
        <div className="mt-2 space-y-2 text-[11px] leading-relaxed">
          <div>
            Una <b>generación</b> es una llamada al modelo de lenguaje. El nivel
            gratuito permite {tope} al día. Los cálculos que no llaman al modelo
            no cuentan.
          </div>

          <div className="border-t pt-2">
            <div className="font-medium mb-1">Sí cuentan</div>
            {(d.desglose || []).map((x, i) => (
              <div key={i} className="mb-1.5">
                <div className="flex justify-between gap-2">
                  <span>{x.concepto}</span>
                  <span className="tabular-nums font-medium">×{x.cantidad}</span>
                </div>
                <div className="text-gray-500">{x.detalle}</div>
              </div>
            ))}
            <div className="flex justify-between gap-2 border-t pt-1 mt-1 font-medium">
              <span>Total por ejecución</span>
              <span className="tabular-nums">{d.coste_de_una_ejecucion}</span>
            </div>
          </div>

          <div className="border-t pt-2">
            <div className="font-medium mb-1">No cuentan</div>
            {(d.no_cuentan || []).map((x, i) => (
              <div key={i} className="mb-1.5">
                <div>{x.concepto}</div>
                <div className="text-gray-500">{x.detalle}</div>
              </div>
            ))}
          </div>

          <div className="border-t pt-2 text-gray-500">{d.nota}</div>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- panel */
export function PanelMetricas({ proyectoId }) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    let vivo = true;
    fetch(`${API_BASE}/proyectos/${proyectoId}/metricas`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((x) => vivo && setDatos(x))
      .catch((e) => vivo && setError(e));
    return () => {
      vivo = false;
    };
  }, [proyectoId]);

  if (error) {
    return (
      <div className="text-sm text-gray-600 border rounded-lg p-3 bg-white">
        No se pudieron cargar las métricas.
      </div>
    );
  }
  if (!datos) {
    return (
      <div className="text-sm text-gray-500 border rounded-lg p-3 bg-white">
        Cargando métricas…
      </div>
    );
  }
  if (!datos.run) {
    return (
      <div className="text-sm text-gray-600 border rounded-lg p-3 bg-white">
        {datos.aviso || "El proyecto todavía no se ha analizado."}
      </div>
    );
  }

  const porCodigo = Object.fromEntries(datos.metricas.map((m) => [m.codigo, m]));
  const discriminan = datos.metricas.filter((m) => m.discrimina);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {DESTACADAS.map((c) => (
          <Tarjeta key={c} metrica={porCodigo[c]} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <Etiqueta tono="azul">{datos.conteos.brechas} brechas</Etiqueta>
        <Etiqueta tono="azul">{datos.conteos.articulos} artículos</Etiqueta>
        <Etiqueta>
          {discriminan.length} de {datos.metricas.length} métricas discriminan
        </Etiqueta>
        <Etiqueta>
          {(datos.run.tokens_in + datos.run.tokens_out).toLocaleString("es")} tokens
        </Etiqueta>
        {datos.estado_arte && (
          <Etiqueta tono="verde">
            estado del arte v{datos.estado_arte.version}
          </Etiqueta>
        )}
      </div>

      {!datos.validacion_calibrada && <AvisoValidacion />}

      <button
        onClick={() => setAbierto((v) => !v)}
        className="text-sm text-blue-700 hover:underline"
      >
        {abierto ? "Ocultar" : "Ver"} las {datos.metricas.length} métricas en detalle
      </button>

      {abierto && <TablaDistribuciones metricas={datos.metricas} />}
    </div>
  );
}

export function TablaDistribuciones({ metricas }) {
  return (
    <div className="overflow-x-auto border rounded-xl bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-100 text-left">
          <tr>
            <th className="px-3 py-2">Métrica</th>
            <th className="px-3 py-2 w-20">Mediana</th>
            <th className="px-3 py-2 w-20">P25</th>
            <th className="px-3 py-2 w-20">P75</th>
            <th className="px-3 py-2 w-20">IQR</th>
            <th className="px-3 py-2 w-14">n</th>
            <th className="px-3 py-2">Lectura</th>
          </tr>
        </thead>
        <tbody>
          {metricas.map((m) => (
            <tr key={m.codigo} className="border-t align-top">
              <td className="px-3 py-2">
                <div className="font-medium">{m.nombre}</div>
                <div className="text-[11px] text-gray-500">
                  {m.codigo} · {m.nivel} · mejor {m.mejor}
                </div>
                <div className="text-[11px] text-gray-600 mt-1 max-w-md">
                  {m.descripcion}
                </div>
              </td>
              <td className="px-3 py-2 font-medium">{fmt(m.mediana)}</td>
              <td className="px-3 py-2 text-gray-600">{fmt(m.p25)}</td>
              <td className="px-3 py-2 text-gray-600">{fmt(m.p75)}</td>
              <td className="px-3 py-2 text-gray-600">{fmt(m.iqr)}</td>
              <td className="px-3 py-2 text-gray-600">{m.n}</td>
              <td className="px-3 py-2">
                <Etiqueta tono={m.discrimina ? "verde" : "ambar"}>
                  {m.veredicto}
                </Etiqueta>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------------------------------------------------------- brecha */
export function DetalleBrecha({ brecha }) {
  if (!brecha) return null;
  const metricas = brecha.metricas || [];
  const respaldo = brecha.respaldo || [];

  return (
    <div className="space-y-4 text-sm">
      <div>
        <div className="text-gray-500">Tipo de brecha</div>
        <div className="font-medium">{brecha.tipo_brecha}</div>
      </div>

      <div>
        <div className="text-gray-500">Brecha</div>
        <p className="whitespace-pre-wrap leading-relaxed">{brecha.brecha}</p>
      </div>

      <div>
        <div className="text-gray-500">Oportunidad de innovación</div>
        <p className="whitespace-pre-wrap leading-relaxed">{brecha.oportunidad}</p>
      </div>

      {!brecha.validacion_calibrada && <AvisoValidacion />}

      {/* Trazabilidad: es lo que permite comprobar de dónde sale la brecha. */}
      <details className="border rounded-lg" open>
        <summary className="cursor-pointer select-none px-3 py-2 bg-gray-50 rounded-t-lg">
          En qué se apoyó el análisis ({respaldo.length} fragmentos del artículo)
        </summary>
        <div className="p-3 space-y-2">
          {brecha.secciones_consultadas?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {brecha.secciones_consultadas.map((s) => (
                <Etiqueta key={s} tono="azul">
                  {s}
                </Etiqueta>
              ))}
            </div>
          )}
          {respaldo.length === 0 && (
            <div className="text-gray-500">
              No se registró el respaldo de este análisis.
            </div>
          )}
          {respaldo.map((h, i) => (
            <div key={i} className="border rounded p-2 bg-gray-50">
              <div className="flex items-center justify-between text-[11px] text-gray-500">
                <span>sección: {h.seccion || "—"}</span>
                <span>relevancia {fmt(h.score, 3)}</span>
              </div>
            </div>
          ))}
        </div>
      </details>

      <details className="border rounded-lg">
        <summary className="cursor-pointer select-none px-3 py-2 bg-gray-50 rounded-t-lg">
          Métricas de esta brecha ({metricas.length})
        </summary>
        <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
          {metricas.map((m) => (
            <div key={m.codigo} className="border rounded-lg p-2" title={m.interpretacion}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-gray-600">{m.nombre}</span>
                <span className="font-medium">{fmt(m.valor)}</span>
              </div>
              <div className="text-[11px] text-gray-500 mt-1">
                {m.codigo} · mejor {m.mejor} · {m.rango}
              </div>
            </div>
          ))}
          {metricas.length === 0 && (
            <div className="text-gray-500">Sin métricas registradas.</div>
          )}
        </div>
      </details>
    </div>
  );
}
