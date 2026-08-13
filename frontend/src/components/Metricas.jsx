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

import { api } from "../sesion";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/* ---------------------------------------------------------------- utilidades */
function fmt(v, decimales = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(decimales);
}

/** Métricas destacadas en las tarjetas superiores, por orden de interés. */
const DESTACADAS = ["N3.1", "N1.2", "N3.2", "N4.2"];

/** Segundos a "3h 21m 47s", omitiendo las unidades que no aportan. */
function duracion(seg) {
  const s = Math.max(0, Math.floor(seg));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h) return `${h} h ${String(m).padStart(2, "0")} min ${String(r).padStart(2, "0")} s`;
  if (m) return `${m} min ${String(r).padStart(2, "0")} s`;
  return `${r} s`;
}

/**
 * Cuenta atrás anclada al reloj del servidor.
 *
 * El navegador puede ir desfasado respecto a la base de datos, así que en vez
 * de comparar contra la hora local se calcula una sola vez la diferencia entre
 * ambos relojes y se descuenta sobre ella. De lo contrario un ordenador con la
 * hora mal puesta mostraría una cuenta atrás falsa sin que nada lo delatara.
 */
function useCuentaAtras(momentoISO, ahoraServidorISO = null) {
  const [segundos, setSegundos] = useState(null);

  useEffect(() => {
    if (!momentoISO) {
      setSegundos(null);
      return;
    }
    const destino = new Date(momentoISO).getTime();

    // Con instante de referencia del servidor se corrige el desfase entre
    // relojes: hace falta cuando la marca viene sin huso, como las de MySQL.
    // Sin él, la marca ya lleva huso propio y basta el reloj del navegador.
    const desfase = ahoraServidorISO
      ? Date.now() - new Date(ahoraServidorISO).getTime()
      : 0;

    const recalcular = () =>
      setSegundos(Math.max(0, Math.round((destino - (Date.now() - desfase)) / 1000)));

    recalcular();
    const t = setInterval(recalcular, 1000);
    return () => clearInterval(t);
  }, [momentoISO, ahoraServidorISO]);

  return segundos;
}

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

/**
 * Explica por qué el estado de validación es "pendiente".
 *
 * Va plegado: el texto es necesario la primera vez y estorba a partir de la
 * segunda, y aparecía repetido en el panel y en cada brecha. Un titular basta
 * para saber que hay algo que leer.
 */
export function AvisoValidacion() {
  return (
    <details className="rounded-lg border border-aviso-borde bg-aviso-claro text-aviso text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 font-medium marker:text-current">
        Validación automática pendiente de calibrar
      </summary>
      <p className="px-3 pb-3 leading-relaxed opacity-90">
        Las reglas anteriores se apoyaban en umbrales que nunca llegaban a
        activarse, de modo que casi toda brecha acababa marcada como aceptada
        sin haber sido validada. Hasta calibrarlos contra criterio experto, el
        sistema prefiere declararse indeciso antes que dar por buena una brecha
        que no ha comprobado.
      </p>
    </details>
  );
}

/**
 * Consumo de API frente al límite diario del nivel gratuito.
 *
 * Incluye el desglose porque decir "cuesta 6" sin explicar de dónde sale ese
 * 6 obliga a adivinar si depende del número de artículos, de su tamaño o de
 * los PDF indexados.
 */
export function IndicadorConsumo({ proyectoId, compacto = false }) {
  const [d, setD] = useState(null);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    let vivo = true;
    // Sin proyecto se consulta la cuota de la clave a secas, que es lo que
    // interesa desde la lista: el margen es el mismo para todos los proyectos.
    const url = proyectoId
      ? `${API_BASE}/proyectos/${proyectoId}/consumo`
      : `${API_BASE}/consumo`;
    api(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((x) => vivo && setD(x))
      .catch(() => {
        // Incluye la sesión caducada, que `api` ya gestionó cerrándola: aquí
        // no hay nada que mostrar, el indicador simplemente no aparece.
      });
    return () => {
      vivo = false;
    };
  }, [proyectoId]);

  // Los hooks van antes de cualquier retorno: su orden debe ser estable
  // entre renderizados.
  const ahoraServidor = d?.ahora_servidor ?? null;
  const segProxima = useCuentaAtras(d?.renovaciones?.[0]?.momento, ahoraServidor);
  const segEjecucion = useCuentaAtras(
    d?.disponible_para_ejecucion_en?.momento,
    ahoraServidor
  );
  // El reinicio del proveedor llega como instante absoluto en UTC, así que
  // no necesita corrección de desfase.
  const segReinicio = useCuentaAtras(d?.reinicio_proveedor?.momento_utc);

  if (!d) return null;
  const usadas = d.generaciones_estimadas;
  const tope = d.limite_diario_nivel_gratuito;
  const restantes = d.restantes_estimadas;
  const pct = Math.min(100, Math.round((usadas / Math.max(1, tope)) * 100));
  // Sin proyecto no hay coste de ejecucion con el que comparar, asi que el
  // aviso se basa en el margen restante.
  const alcanza = proyectoId ? d.alcanza_para_otra_ejecucion : restantes > 0;

  if (compacto) {
    return (
      <div
        className="inline-flex items-center gap-2.5 rounded-full border border-borde bg-superficie pl-3 pr-3.5 py-1.5"
        title={
          segProxima != null
            ? `Se recupera 1 generación en ${duracion(segProxima)}`
            : undefined
        }
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            alcanza ? "bg-acento" : "bg-mal"
          }`}
        />
        <span className="text-xs text-tinta-media">
          API · <span className="tabular-nums">{usadas}</span> de{" "}
          <span className="tabular-nums">{tope}</span> hoy
        </span>
        <span className="w-16 h-1 rounded-full bg-hundido overflow-hidden">
          <span
            className={`block h-full ${alcanza ? "bg-acento" : "bg-mal"}`}
            style={{ width: `${pct}%` }}
          />
        </span>
        {!alcanza && segReinicio != null && (
          <span className="text-xs text-mal tabular-nums">
            {duracion(segReinicio)}
          </span>
        )}
      </div>
    );
  }

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
        {proyectoId ? (
          <>
            Analizar este proyecto cuesta{" "}
            <b>{d.coste_de_una_ejecucion} generaciones</b>.{" "}
            {alcanza
              ? `Quedan ${restantes}: alcanza para otra ejecución.`
              : `Quedan ${restantes}, faltan ${d.generaciones_que_faltan}.`}
          </>
        ) : (
          <>Quedan {restantes} generaciones disponibles hoy.</>
        )}
      </div>

      {/* Dos referencias distintas, y conviene no confundirlas: el proveedor
          reinicia su cuota de golpe a medianoche de su huso; nuestra ventana
          móvil libera una generación cada vez que una llamada cumple 24 h. */}
      {(segReinicio != null || segProxima != null || segEjecucion != null) && (
        <div className="mt-2.5 rounded-lg border border-borde bg-hundido/60 px-2.5 py-2 text-[11px] leading-relaxed space-y-1.5">
          {segReinicio != null && (
            <div>
              <span className="text-tinta-suave">
                La cuota vuelve a {d.limite_diario_nivel_gratuito} en{" "}
              </span>
              <span className="font-medium tabular-nums">
                {duracion(segReinicio)}
              </span>
              {/* Se muestra la hora local equivalente: "medianoche UTC-8" se
                  lee como "medianoche" a secas, y con tres horas de diferencia
                  eso lleva a esperar el reinicio cuando no toca. */}
              <div className="text-tinta-suave">
                Es medianoche en {d.reinicio_proveedor?.huso}, el huso del panel
                de AI Studio; aquí serán las{" "}
                {new Date(d.reinicio_proveedor?.momento_utc).toLocaleTimeString(
                  undefined,
                  { hour: "2-digit", minute: "2-digit" }
                )}
                .
              </div>
            </div>
          )}

          {(segProxima != null || segEjecucion != null) && (
            <div className="border-t border-borde pt-1.5">
              {!alcanza && segEjecucion != null ? (
                <>
                  <span className="text-tinta-suave">
                    Nuestra estimación alcanzaría para analizar en{" "}
                  </span>
                  <span className="font-medium tabular-nums">
                    {duracion(segEjecucion)}
                  </span>
                </>
              ) : (
                segProxima != null && (
                  <>
                    <span className="text-tinta-suave">
                      Nuestra estimación recupera 1 en{" "}
                    </span>
                    <span className="font-medium tabular-nums">
                      {duracion(segProxima)}
                    </span>
                  </>
                )
              )}
              <div className="text-tinta-suave">
                Ventana móvil de 24 h de esta aplicación. Manda el reinicio del
                proveedor.
              </div>
            </div>
          )}
        </div>
      )}

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

          {/* La cuota es de la clave, no del proyecto: conviene decirlo donde
              se muestra el número, para que nadie suponga que cada proyecto
              tiene su propio margen. */}
          {d.exactitud?.ambito && (
            <div className="text-tinta-suave">{d.exactitud.ambito}</div>
          )}

          {d.desglose && (
            <div className="border-t pt-2">
              <div className="font-medium mb-1">Sí cuentan</div>
              {d.desglose.map((x, i) => (
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
          )}

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
    api(`${API_BASE}/proyectos/${proyectoId}/metricas`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((x) => vivo && setDatos(x))
      // Una sesión caducada no es un error de este panel: `api` ya la cerró y
      // la aplicación entera vuelve a la pantalla de entrada.
      .catch((e) => vivo && !e?.sesionCaducada && setError(e));
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

/* ------------------------------------------------------------ fidelidad */

/**
 * Desglose de la verificación de fidelidad (nivel N2).
 *
 * Muestra la brecha descompuesta en afirmaciones y, de cada una, si se
 * sostiene en el artículo. Es la diferencia entre decir «esta brecha es
 * fiable» y poder señalar qué frase sale de qué párrafo.
 *
 * Las afirmaciones se separan en dos grupos porque no se comprueban igual:
 * las evidenciales describen lo que el artículo hace y deben rastrearse hasta
 * un fragmento; las inferenciales concluyen lo que falta, y no pueden
 * verificarse contra el propio artículo porque afirman justo lo que no
 * contiene.
 */
export function Fidelidad({ verificacion }) {
  if (!verificacion) return null;

  const {
    disponible,
    motivo,
    afirmaciones = [],
    fidelidad,
    trazabilidad,
    equilibrio_evidencial: equilibrio,
    n_sin_respaldo: sinRespaldo,
  } = verificacion;

  const evidenciales = afirmaciones.filter((a) => a.tipo === "evidencial");
  const inferenciales = afirmaciones.filter((a) => a.tipo === "inferencial");

  return (
    <details className="border border-borde rounded-lg" open={sinRespaldo > 0}>
      <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg">
        <span className="font-medium">Fidelidad a las fuentes</span>
        {disponible ? (
          <span className="text-tinta-suave">
            {" "}· {Math.round((fidelidad ?? 0) * 100)}% de las afirmaciones
            comprobables está respaldada
            {sinRespaldo > 0 && (
              <span className="text-mal"> · {sinRespaldo} sin respaldo</span>
            )}
          </span>
        ) : (
          <span className="text-tinta-suave"> · sin verificar</span>
        )}
      </summary>

      <div className="p-3 space-y-3">
        {!disponible && (
          <p className="text-tinta-suave leading-relaxed">
            {motivo ||
              "La verificación no llegó a ejecutarse, así que no hay medición."}
          </p>
        )}

        {disponible && (
          <div className="grid grid-cols-3 gap-2">
            {[
              ["Fidelidad", fidelidad],
              ["Trazabilidad", trazabilidad],
              ["Base factual", equilibrio],
            ].map(([k, v]) => (
              <div
                key={k}
                className="border border-borde rounded-lg px-2 py-1.5 text-center"
              >
                <div className="text-[11px] text-tinta-suave">{k}</div>
                <div className="font-medium tabular-nums">{fmt(v, 2)}</div>
              </div>
            ))}
          </div>
        )}

        {evidenciales.length > 0 && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave mb-1.5">
              Comprobables contra el artículo
            </div>
            <div className="space-y-1.5">
              {evidenciales.map((a, i) => (
                <div
                  key={i}
                  className={`rounded-lg border px-2.5 py-2 ${
                    a.respaldada
                      ? "border-borde bg-hundido/50"
                      : "border-mal-borde bg-mal-claro"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                        a.respaldada ? "bg-bien" : "bg-mal"
                      }`}
                    />
                    <div className="min-w-0">
                      <p className="leading-snug">{a.texto}</p>
                      {a.respaldada ? (
                        <p className="text-[11px] text-tinta-suave mt-1">
                          Fragmento {a.fragmento}
                          {a.cita && <>: «{a.cita}»</>}
                        </p>
                      ) : (
                        <p className="text-[11px] text-mal mt-1">
                          Sin respaldo en los fragmentos consultados.
                          {a.motivo && <> {a.motivo}</>}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {inferenciales.length > 0 && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave mb-1.5">
              Conclusiones
            </div>
            <div className="space-y-1.5">
              {inferenciales.map((a, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-borde bg-hundido/50 px-2.5 py-2"
                >
                  <p className="leading-snug">{a.texto}</p>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-tinta-suave mt-1.5 leading-relaxed">
              Afirman lo que el artículo no cubre, así que no pueden
              comprobarse contra él. Su validez se decide con criterio experto.
            </p>
          </div>
        )}
      </div>
    </details>
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

      {/* Fidelidad antes que el respaldo bruto: interesa más saber qué
          afirmaciones se sostienen que qué fragmentos se consultaron. */}
      <Fidelidad verificacion={brecha.verificacion} />

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
