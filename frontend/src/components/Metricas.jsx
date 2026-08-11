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
    gris: "bg-hundido text-tinta-media border-borde",
    verde: "bg-bien-claro text-bien border-bien-borde",
    ambar: "bg-aviso-claro text-aviso border-aviso-borde",
    azul: "bg-acento-claro text-acento-fuerte border-acento-borde",
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
    <div className="border border-borde rounded-lg p-3 bg-superficie" title={descripcion}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-tinta-media text-sm leading-tight">{nombre}</div>
        <Etiqueta tono={discrimina ? "verde" : "ambar"}>
          {discrimina ? "discrimina" : "poca variación"}
        </Etiqueta>
      </div>
      <div className="text-2xl font-semibold mt-1">{fmt(mediana)}</div>
      <div className="text-[11px] text-tinta-suave mt-1">
        mediana · IQR {fmt(iqr)} · n={n} · {rango}
      </div>
    </div>
  );
}

/** Explica por qué el estado de validación es "pendiente". */
export function AvisoValidacion() {
  return (
    <div className="rounded-lg border border-aviso-borde bg-aviso-claro p-3 text-sm text-aviso">
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
          ? "border-borde bg-superficie text-tinta-media"
          : "border-mal-borde bg-mal-claro text-mal"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">Consumo de API (24 h)</span>
        <span className="tabular-nums">
          {usadas} / {tope}
        </span>
      </div>

      <div className="mt-2 h-1.5 w-full rounded-full bg-hundido overflow-hidden">
        <div
          className={`h-full ${alcanza ? "bg-acento" : "bg-mal"}`}
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
        className="mt-2 text-[11px] text-acento hover:underline"
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
                <div className="text-tinta-suave">{x.detalle}</div>
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
                <div className="text-tinta-suave">{x.detalle}</div>
              </div>
            ))}
          </div>

          {/* Se dice de dónde sale el número y qué no alcanza a ver. Un
              contador presentado como exacto sin serlo lleva a decisiones
              equivocadas. */}
          {d.exactitud && (
            <div className="border-t pt-2 space-y-1 text-tinta-suave">
              <div>
                <span className="font-medium">Qué cuenta este indicador: </span>
                {d.exactitud.cuenta}
              </div>
              {d.generaciones_fallidas > 0 && (
                <div>
                  De las {usadas} registradas, {d.generaciones_fallidas}{" "}
                  fallaron. Consumen cuota igual.
                </div>
              )}
              <div>
                <span className="font-medium">No cuenta: </span>
                {(d.exactitud.no_cuenta || []).join(" ")}
              </div>
              <div>{d.exactitud.ventana}</div>
              <div>
                Cifra oficial en{" "}
                <a
                  href="https://ai.dev/rate-limit"
                  target="_blank"
                  rel="noreferrer"
                  className="text-acento hover:underline"
                >
                  ai.dev/rate-limit
                </a>
              </div>
            </div>
          )}
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
      <div className="text-sm text-tinta-media border border-borde rounded-lg p-3 bg-superficie">
        No se pudieron cargar las métricas.
      </div>
    );
  }
  if (!datos) {
    return (
      <div className="text-sm text-tinta-suave border border-borde rounded-lg p-3 bg-superficie">
        Cargando métricas…
      </div>
    );
  }
  if (!datos.run) {
    return (
      <div className="text-sm text-tinta-media border border-borde rounded-lg p-3 bg-superficie">
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

      <div className="flex flex-wrap items-center gap-2 text-xs text-tinta-media">
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
        className="text-sm text-acento hover:underline"
      >
        {abierto ? "Ocultar" : "Ver"} las {datos.metricas.length} métricas en detalle
      </button>

      {abierto && <TablaDistribuciones metricas={datos.metricas} />}
    </div>
  );
}

export function TablaDistribuciones({ metricas }) {
  return (
    <div className="overflow-x-auto border border-borde rounded-xl bg-superficie">
      <table className="min-w-full text-sm">
        <thead className="bg-hundido text-left text-tinta-media">
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
            <tr key={m.codigo} className="border-t border-borde align-top">
              <td className="px-3 py-2">
                <div className="font-medium">{m.nombre}</div>
                <div className="text-[11px] text-tinta-suave">
                  {m.codigo} · {m.nivel} · mejor {m.mejor}
                </div>
                <div className="text-[11px] text-tinta-media mt-1 max-w-md">
                  {m.descripcion}
                </div>
              </td>
              <td className="px-3 py-2 font-medium">{fmt(m.mediana)}</td>
              <td className="px-3 py-2 text-tinta-media">{fmt(m.p25)}</td>
              <td className="px-3 py-2 text-tinta-media">{fmt(m.p75)}</td>
              <td className="px-3 py-2 text-tinta-media">{fmt(m.iqr)}</td>
              <td className="px-3 py-2 text-tinta-media">{m.n}</td>
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
        <div className="text-tinta-suave">Tipo de brecha</div>
        <div className="font-medium">{brecha.tipo_brecha}</div>
      </div>

      <div>
        <div className="text-tinta-suave">Brecha</div>
        <p className="whitespace-pre-wrap leading-relaxed">{brecha.brecha}</p>
      </div>

      <div>
        <div className="text-tinta-suave">Oportunidad de innovación</div>
        <p className="whitespace-pre-wrap leading-relaxed">{brecha.oportunidad}</p>
      </div>

      {!brecha.validacion_calibrada && <AvisoValidacion />}

      {/* Trazabilidad: es lo que permite comprobar de dónde sale la brecha. */}
      <details className="border border-borde rounded-lg" open>
        <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg">
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
            <div className="text-tinta-suave">
              No se registró el respaldo de este análisis.
            </div>
          )}
          {respaldo.map((h, i) => (
            <div key={i} className="border border-borde rounded-lg p-2 bg-hundido">
              <div className="flex items-center justify-between text-[11px] text-tinta-suave">
                <span>sección: {h.seccion || "—"}</span>
                <span>relevancia {fmt(h.score, 3)}</span>
              </div>
            </div>
          ))}
        </div>
      </details>

      <details className="border border-borde rounded-lg">
        <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg">
          Métricas de esta brecha ({metricas.length})
        </summary>
        <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
          {metricas.map((m) => (
            <div key={m.codigo} className="border border-borde rounded-lg p-2" title={m.interpretacion}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-tinta-media">{m.nombre}</span>
                <span className="font-medium">{fmt(m.valor)}</span>
              </div>
              <div className="text-[11px] text-tinta-suave mt-1">
                {m.codigo} · mejor {m.mejor} · {m.rango}
              </div>
            </div>
          ))}
          {metricas.length === 0 && (
            <div className="text-tinta-suave">Sin métricas registradas.</div>
          )}
        </div>
      </details>
    </div>
  );
}
