import { useCallback, useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  DetalleBrecha,
  IndicadorConsumo,
  PanelMetricas,
} from "./components/Metricas";
import {
  Estado,
  Fila,
  Panel,
  Progreso,
  ProveedorAvisos,
  Recorte,
  Seccion,
  Tabla,
  Td,
  Th,
  Vacio,
  ZonaArchivos,
} from "./components/UI";
import { useAviso } from "./components/avisos";
import Login from "./components/Login";
import { alExpirar, api, cerrarSesion, leerSesion } from "./sesion";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/* ---------------- UI core ---------------- */
function Page({ title, subtitle, children }) {
  return (
    <div className="min-h-screen bg-papel">
      <div className="max-w-6xl mx-auto px-4 py-10">
        <h1 className="text-3xl font-semibold mb-1 text-tinta tracking-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="text-sm text-tinta-media mb-8 max-w-2xl leading-relaxed">
            {subtitle}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}

function Btn({ children, kind = "ghost", ...props }) {
  const base =
    "rounded-lg px-4 py-2 text-sm transition-colors disabled:opacity-45 " +
    "disabled:cursor-not-allowed";
  const k = {
    // Contorno: la acción corriente, presente sin reclamar atención.
    ghost:
      `${base} border border-borde bg-superficie text-tinta hover:bg-hundido`,
    // Acento: acciones de consulta y navegación.
    blue:
      `${base} border border-acento-borde bg-acento-claro text-acento-fuerte ` +
      "hover:border-acento",
    green:
      `${base} border border-bien-borde bg-bien-claro text-bien hover:border-bien`,
    // Dorado: reservado a la acción principal de cada pantalla, para que el
    // usuario sepa siempre cuál es sin tener que leerlas todas.
    yellow:
      "rounded-lg px-4 py-2 text-sm font-medium bg-oro text-white shadow-[var(--sombra-1)] " +
      "hover:bg-oro-fuerte transition-[background-color,transform] " +
      "active:scale-[0.985] disabled:opacity-45 disabled:cursor-not-allowed " +
      "disabled:hover:bg-oro",
    gray: `${base} border border-borde bg-hundido text-tinta-media hover:text-tinta`,
    danger:
      `${base} border border-mal-borde bg-mal-claro text-mal hover:border-mal`,
  };
  return (
    <button className={k[kind] || k.ghost} {...props}>
      {children}
    </button>
  );
}

/* Modal general (ancho grande + scroll interno) */
function Modal({ open, onClose, title, children, footer, ancho = "max-w-5xl" }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-tinta/35 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`w-full ${ancho} rounded-2xl bg-lienzo border border-borde overflow-hidden`}
        style={{ boxShadow: "var(--sombra-3)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-borde bg-superficie">
          <h3 className="text-lg font-semibold text-tinta leading-snug">
            {title}
          </h3>
        </div>
        <div className="p-6 max-h-[78vh] overflow-y-auto">{children}</div>
        <div className="px-5 py-4 border-t border-borde flex flex-wrap gap-2 justify-end bg-hundido">
          {footer}
        </div>
      </div>
    </div>
  );
}

/* Overlay de carga */
function LoadingOverlay({ show, text = "Procesando…" }) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-tinta/35 backdrop-blur-[2px]" />
      <div className="absolute inset-0 flex items-center justify-center p-6">
        <div
          className="w-full max-w-md rounded-2xl bg-lienzo border border-borde p-7 text-center"
          style={{ boxShadow: "var(--sombra-3)" }}
        >
          <div className="mx-auto mb-4 h-9 w-9 rounded-full border-[3px] border-borde border-t-acento animate-spin" />
          <p className="text-tinta font-medium">{text}</p>
          <p className="text-xs text-tinta-suave mt-2 leading-relaxed">
            Este proceso puede tardar según la cantidad de artículos.
          </p>
        </div>
      </div>
    </div>
  );
}

/* Modal de error detallado */
function ErrorModal({ error, onClose }) {
  return (
    <Modal
      open={!!error}
      onClose={onClose}
      title="Error"
      footer={
        <Btn kind="gray" onClick={onClose}>
          Cerrar
        </Btn>
      }
    >
      <div className="text-sm text-mal leading-relaxed">
        {typeof error === "string"
          ? error
          : error?.message || "Ocurrió un error"}
      </div>
      {error?.detail && (
        <pre className="mt-3 text-xs p-3 bg-mal-claro border border-mal-borde text-tinta-media rounded-lg whitespace-pre-wrap overflow-x-auto">
          {JSON.stringify(error.detail, null, 2)}
        </pre>
      )}
    </Modal>
  );
}

/* -------------- API helpers -------------- */

/**
 * Lee el cuerpo de una respuesta fallida sin romperse por el camino.
 *
 * El patrón anterior era `try { await r.json() } catch { await r.text() }`, y
 * tiene un defecto que solo aparece cuando el servidor no devuelve JSON: el
 * cuerpo de una respuesta se puede leer UNA sola vez. Cuando `r.json()` falla
 * ya ha consumido el flujo, así que el `r.text()` del catch lanza «body stream
 * already read».
 *
 * Y esa excepción salía por encima del código que avisaba del error, de modo
 * que la pantalla se quedaba muda justo cuando más falta hacía el mensaje: un
 * 500 con una traza HTML —el caso exacto que lo destapó— se veía como si no
 * hubiera pasado nada.
 *
 * Se lee texto una vez y se intenta interpretar después.
 */
async function leerDetalle(r) {
  let txt;
  try {
    txt = await r.text();
  } catch {
    return null;
  }
  if (!txt) return null;
  try {
    return JSON.parse(txt);
  } catch {
    return txt;
  }
}

async function jget(url) {
  const r = await api(url);
  if (!r.ok) {
    const err = new Error(`GET ${url} → ${r.status}`);
    err.detail = await leerDetalle(r);
    throw err;
  }
  return r.json();
}
async function jpost(url, body) {
  const r = await api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  const txt = await r.text();
  if (!r.ok) {
    let detail;
    try {
      detail = JSON.parse(txt);
    } catch {
      detail = txt;
    }
    const err = new Error(`POST ${url} → ${r.status}`);
    err.detail = detail;
    throw err;
  }
  return txt ? JSON.parse(txt) : {};
}
async function downloadFile(url, filename) {
  const r = await api(url);
  if (!r.ok) {
    const err = new Error(`DOWNLOAD ${url} → ${r.status}`);
    err.detail = await leerDetalle(r);
    throw err;
  }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ================ 0) WELCOME ================ */
function WelcomeScreen({ onStart, onList }) {
  return (
    <div className="min-h-screen bg-papel">
      <div className="max-w-5xl mx-auto px-4 py-16">
        <div
          className="rounded-3xl bg-lienzo border border-borde overflow-hidden"
          style={{ boxShadow: "var(--sombra-2)" }}
        >
          <div className="p-8 md:p-12 grid md:grid-cols-2 gap-10 items-center">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-acento-claro text-acento-fuerte text-xs font-medium mb-5 border border-acento-borde">
                <span className="h-1.5 w-1.5 rounded-full bg-acento"></span>
                Matriz de brechas con IA generativa
              </div>
              <h1 className="text-3xl md:text-4xl font-bold text-tinta leading-tight tracking-tight">
                Bienvenido
              </h1>
              <p className="mt-4 text-tinta-media leading-relaxed">
                Carga artículos científicos, analízalos y obtén las brechas de
                investigación y el estado del arte. Puedes empezar creando un
                tema o revisar tus proyectos existentes.
              </p>

              <ul className="mt-7 space-y-3 text-sm text-tinta-media">
                {[
                  "Define el tema, el objetivo y la metodología",
                  "Sube los PDFs y ejecuta el análisis",
                  "Consulta brechas, oportunidades y su respaldo documental",
                  "Descarga la matriz y las métricas del proyecto",
                ].map((t, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-acento" />
                    <span className="leading-relaxed">{t}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-9 flex flex-wrap gap-3">
                <Btn kind="yellow" onClick={onStart}>
                  Comenzar
                </Btn>
                <Btn kind="blue" onClick={onList}>
                  Ir a proyectos
                </Btn>
              </div>
            </div>

            <div className="rounded-2xl border border-borde bg-superficie p-6">
              <div className="text-xs text-tinta-suave font-medium uppercase tracking-wide">
                Vista previa
              </div>
              <div className="mt-4 space-y-2 text-xs">
                {[
                  ["Proyecto", "IA aplicada a procesos de ingeniería"],
                  ["Artículos", "5 / 5"],
                  ["Brechas detectadas", "5"],
                  ["Estado del arte", "versión 1"],
                ].map(([k, v]) => (
                  <div
                    key={k}
                    className="rounded-lg border border-borde bg-lienzo px-3 py-2.5"
                  >
                    <div className="text-tinta-suave">{k}</div>
                    <div className="font-medium text-tinta mt-0.5">{v}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-[10px] text-tinta-suave">
                Ilustrativo
              </div>
            </div>
          </div>

          <div className="px-8 py-4 bg-hundido border-t border-borde text-xs text-tinta-suave">
            Requiere el backend en ejecución para procesar artículos.
          </div>
        </div>
      </div>
    </div>
  );
}

/* Iconos mínimos de la lista de proyectos. Son decorativos: la información
   importante también aparece como texto para no depender del color o del dibujo. */
function Icono({ tipo, className = "h-5 w-5" }) {
  const trazos = {
    documento: (
      <>
        <path d="M6 3.75h8l4 4V20.25H6z" />
        <path d="M14 3.75v4h4M9 12h6M9 15.5h6" />
      </>
    ),
    brecha: (
      <>
        <circle cx="12" cy="12" r="3.2" />
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.7 5.7l2.8 2.8M15.5 15.5l2.8 2.8M18.3 5.7l-2.8 2.8M8.5 15.5l-2.8 2.8" />
      </>
    ),
    analisis: (
      <>
        <path d="M5 19.5V10M12 19.5V5M19 19.5v-7" />
        <path d="M3.5 19.5h17" />
      </>
    ),
    libro: (
      <>
        <path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h5v16H7a2.5 2.5 0 0 0-2.5 2z" />
        <path d="M19.5 5.5A2.5 2.5 0 0 0 17 3h-5v16h5a2.5 2.5 0 0 1 2.5 2z" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 10.5v5M12 7.5h.01" />
      </>
    ),
    objetivo: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <circle cx="12" cy="12" r="4.5" />
        <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
      </>
    ),
    idea: (
      <>
        <path d="M9 18h6M10 21h4" />
        <path d="M8.5 14.5a6 6 0 1 1 7 0c-.8.6-1.3 1.5-1.5 2.5h-5c-.2-1-.7-1.9-1.5-2.5Z" />
      </>
    ),
  };

  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {trazos[tipo] || trazos.info}
    </svg>
  );
}

function EtiquetaCampo({ children, ayuda, ayudaId }) {
  return (
    <>
      <span className="text-sm font-medium text-tinta">{children}</span>
      {ayuda && (
        <p
          id={ayudaId}
          className="mt-1 flex items-start gap-1.5 text-xs leading-relaxed text-tinta-suave"
        >
          <span className="mt-0.5 shrink-0 text-acento" aria-hidden="true">
            <Icono tipo="info" className="h-3.5 w-3.5" />
          </span>
          <span>{ayuda}</span>
        </p>
      )}
    </>
  );
}

function Pista({ children }) {
  return (
    <span
      className="inline-grid h-4 w-4 place-items-center rounded-full border border-acento-borde text-[10px] font-semibold text-acento"
      title={children}
      aria-label={children}
    >
      i
    </span>
  );
}

function IndicadorProyecto({ tipo, label, valor, apoyo, ayuda }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2 text-sm text-tinta-media">
        <span className="text-acento">
          <Icono tipo={tipo} className="h-5 w-5" />
        </span>
        <span>{label}</span>
        {ayuda && <Pista>{ayuda}</Pista>}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-tinta tabular-nums">
        {valor}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-tinta-suave">{apoyo}</p>
    </div>
  );
}

/* ================ 1) LISTA ================ */
function Lista({ goCreate, goProyecto }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  // modal SOTA
  const [sotaModal, setSotaModal] = useState({ open: false, data: null });

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      // El listado ya trae los recuentos. Antes esta pantalla pedía, por cada
      // proyecto, sus artículos y su estado del arte: tantas peticiones como
      // tarjetas, cada vez que se abría. Y las brechas no las pedía en
      // absoluto, así que su indicador no podía mostrar nada.
      const proyectos = await jget(`${API_BASE}/proyectos`);
      setRows(
        proyectos.map((p) => ({
          ...p,
          articulos_count: p.n_articulos ?? 0,
          brechas_count: p.n_brechas ?? 0,
          // `tiene_estado_arte` y no `estado_arte_generado`: esa columna del
          // proyecto no la actualiza nadie y es siempre falsa. Usarla hizo
          // desaparecer el «Generado» y el enlace «ver» de un proyecto que sí
          // tenía su síntesis.
          tiene_sota: !!p.tiene_estado_arte,
        }))
      );
    } catch (e) {
      setRows([]);
      setErr(e);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function verSOTA(id) {
    try {
      const data = await jget(`${API_BASE}/proyectos/${id}/estado_arte/latest`);
      setSotaModal({ open: true, data });
    } catch (e) {
      setErr(e);
    }
  }

  return (
    <Page
      title="Proyectos"
      subtitle="Organiza tus artículos, brechas y estado del arte en un solo lugar."
    >
      <Seccion
        acciones={
          <>
            {/* La cuota es de la clave y se comparte entre proyectos, asi que
                se muestra aqui: no hace falta entrar en uno para saber cuanto
                margen queda. */}
            <IndicadorConsumo compacto />
            <Btn kind="yellow" onClick={goCreate}>
              Nuevo proyecto
            </Btn>
          </>
        }
      >
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-acento-borde bg-acento-claro px-4 py-3 text-sm text-acento-fuerte">
          <span className="mt-0.5 shrink-0 text-acento">
            <Icono tipo="info" className="h-5 w-5" />
          </span>
          <p className="leading-relaxed">
            El consumo de API es compartido por tus proyectos y se renueva
            automáticamente. Los indicadores te ayudan a entender qué está
            listo y qué falta revisar.
          </p>
        </div>

        {loading ? (
          <div className="rounded-xl border border-borde bg-superficie px-4 py-10 text-center text-sm text-tinta-suave">
            Cargando…
          </div>
        ) : rows.length === 0 ? (
          <Vacio
            titulo="Todavía no hay proyectos"
            accion={
              <Btn kind="yellow" onClick={goCreate}>
                Crear el primero
              </Btn>
            }
          >
            Un proyecto define el tema y el objetivo de tu revisión. A partir de
            ahí subes los artículos y el sistema detecta las brechas.
          </Vacio>
        ) : (
          <div>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-tinta-media">
              Tus proyectos
            </h2>
            <div className="space-y-4">
              {rows.map((p) => {
                const articulos = p.articulos_count ?? 0;
                const objetivo = p.n_articulos_objetivo ?? "—";
                const listo = p.tiene_sota;
                const brechas = p.brechas_count ?? 0;

                return (
                  <article
                    key={p.id}
                    className="overflow-hidden rounded-2xl border border-borde bg-superficie transition-[border-color,box-shadow] hover:border-borde-fuerte"
                    style={{ boxShadow: "var(--sombra-1)" }}
                  >
                    <div className="p-5 md:p-6">
                      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                        <div className="flex min-w-0 items-start gap-4">
                          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-acento-claro text-acento">
                            <Icono tipo="documento" className="h-7 w-7" />
                          </span>
                          <div className="min-w-0">
                            <h3 className="text-xl font-semibold leading-tight tracking-tight text-tinta">
                              <Recorte lineas={2}>
                                {p.tema_principal || "(Sin tema)"}
                              </Recorte>
                            </h3>
                            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                              <span className="inline-flex items-center gap-2 rounded-lg bg-hundido px-3 py-1.5 text-tinta-media">
                                <Icono tipo="documento" className="h-4 w-4" />
                                {articulos} {articulos === 1 ? "artículo" : "artículos"} incorporados
                              </span>
                              <span className="hidden h-5 w-px bg-borde sm:block" />
                              {listo ? (
                                <button
                                  type="button"
                                  onClick={() => verSOTA(p.id)}
                                  className="rounded-lg bg-bien-claro px-3 py-1.5 text-left text-bien transition-colors hover:bg-bien-borde"
                                  title="Ver el estado del arte generado"
                                >
                                  <Estado tono="bien">Estado del arte listo · ver</Estado>
                                </button>
                              ) : (
                                <span className="rounded-lg bg-hundido px-3 py-1.5">
                                  <Estado tono="neutro">Estado del arte pendiente</Estado>
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="mt-6 grid gap-6 border-t border-borde pt-5 md:grid-cols-3 md:gap-0">
                        <IndicadorProyecto
                          tipo="documento"
                          label="Artículos"
                          valor={
                            <>
                              {articulos} <span className="text-base font-normal text-tinta-suave">/ {objetivo}</span>
                            </>
                          }
                          apoyo="Estudios incorporados al proyecto"
                          ayuda="Cantidad de artículos que has agregado frente al objetivo inicial."
                        />
                        <div className="border-b border-borde pb-6 md:border-b-0 md:border-l md:px-6 md:pb-0">
                          {/* El valor era un guion fijo: nunca llegó a
                              conectarse con el dato. Y un guion en una columna
                              de resultados no se lee como «no consultado», se
                              lee como «no se detectó ninguna». */}
                          <IndicadorProyecto
                            tipo="brecha"
                            label="Brechas detectadas"
                            valor={articulos === 0 ? "—" : brechas}
                            apoyo={
                              articulos === 0
                                ? "Primero sube artículos"
                                : brechas === 0
                                  ? "Se calculan al ejecutar el análisis"
                                  : brechas === articulos
                                    ? "Una por cada artículo analizado"
                                    : `De ${articulos} artículos del proyecto`
                            }
                            ayuda="Son vacíos o problemas identificados al comparar los artículos."
                          />
                        </div>
                        <div className="md:border-l md:px-6">
                          <IndicadorProyecto
                            tipo="analisis"
                            label="Estado del análisis"
                            valor={listo ? "Generado" : "Pendiente"}
                            apoyo={listo ? "Síntesis del estado del arte disponible" : "Aún falta analizar los artículos"}
                            ayuda="Indica si ya puedes revisar la síntesis y sus resultados."
                          />
                        </div>
                      </div>

                      <div className="mt-6 flex flex-col gap-4 border-t border-borde pt-5 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-start gap-3 text-sm text-tinta-media">
                          <span className="mt-0.5 shrink-0 text-bien">
                            <Icono tipo="libro" className="h-5 w-5" />
                          </span>
                          <p className="leading-relaxed">
                            {listo
                              ? "Puedes revisar la matriz de brechas y la síntesis generada."
                              : "Sube tus artículos para comenzar a construir la matriz de brechas."}
                          </p>
                        </div>
                        <Btn kind="yellow" onClick={() => goProyecto(p)}>
                          Abrir proyecto <span aria-hidden="true" className="ml-1 text-lg leading-none">›</span>
                        </Btn>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </Seccion>

      {/* Modal SOTA */}
      <Modal
        open={sotaModal.open}
        onClose={() => setSotaModal({ open: false, data: null })}
        title="Estado del arte"
        footer={
          <>
            <Btn
              kind="gray"
              onClick={() => setSotaModal({ open: false, data: null })}
            >
              Cerrar
            </Btn>
          </>
        }
      >
        {sotaModal.data ? (
          <div className="space-y-2 text-sm">
            <div className="text-tinta-media">
              Versión:{" "}
              <span className="font-medium">{sotaModal.data.version}</span> ·{" "}
              Fecha:{" "}
              <span className="font-medium">
                {new Date(sotaModal.data.created_at).toLocaleString()}
              </span>
            </div>
            <article className="whitespace-pre-wrap leading-relaxed border border-borde rounded-lg p-4 bg-hundido text-tinta text-justify">
              {sotaModal.data.texto}
            </article>
          </div>
        ) : (
          <div className="text-tinta-suave">Cargando…</div>
        )}
      </Modal>

      {/* Modal de error */}
      <ErrorModal error={err} onClose={() => setErr(null)} />
    </Page>
  );
}

/* ============ 2) CREAR PROYECTO ============ */
function CrearProyecto({ goBack }) {
  const [err, setErr] = useState(null);
  const avisar = useAviso();

  return (
    <Page
      title="Nuevo proyecto"
      subtitle="El objetivo es el campo que más influye en el resultado: orienta qué fragmentos de cada artículo se entregan al modelo."
    >
      <div className="mb-6 flex justify-end">
        <div className="inline-flex items-center gap-2 rounded-full border border-acento-borde bg-acento-claro px-3 py-1.5 text-xs text-acento">
          <span className="h-1.5 w-1.5 rounded-full bg-acento" aria-hidden="true" />
          <span className="font-medium">Paso 1 de 2</span>
          <span className="text-acento-fuerte/80">· Define tu proyecto</span>
        </div>
      </div>

      <div className="mb-6 h-px bg-borde" aria-hidden="true" />

      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setErr(null);
          const fd = new FormData(e.currentTarget);
          const payload = {
            tema_principal: fd.get("tema_principal"),
            metodologia_txt: fd.get("metodologia_txt"),
            sector_txt: fd.get("sector_txt"),
            objetivo: fd.get("objetivo"),
            n_articulos_objetivo: parseInt(fd.get("n_articulos") || "5", 10),
          };
          try {
            await jpost(`${API_BASE}/proyectos`, payload);
            avisar("Proyecto creado", "bien");
            goBack();
          } catch (e2) {
            setErr(e2);
          }
        }}
        className="space-y-6"
      >
        <section aria-labelledby="datos-proyecto-titulo">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-acento-claro text-acento">
              <Icono tipo="documento" className="h-5 w-5" />
            </span>
            <div>
              <h2 id="datos-proyecto-titulo" className="text-base font-semibold text-tinta">
                Datos del proyecto
              </h2>
              <p className="mt-0.5 text-sm text-tinta-suave">
                Define el contexto que guiará la búsqueda y el análisis.
              </p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
            <label className="block">
              <EtiquetaCampo ayuda="Delimita el tema que analizarás" ayudaId="ayuda-tema">
                Tema principal
              </EtiquetaCampo>
              <input
                name="tema_principal"
                aria-describedby="ayuda-tema"
                className="mt-3 w-full rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta placeholder:text-tinta-suave focus:border-acento focus:outline-none focus:ring-2 focus:ring-acento/20"
                required
                placeholder="Ej: IA generativa en educación"
              />
            </label>

            <label className="block">
              <EtiquetaCampo ayuda="Indica cómo organizarás la revisión" ayudaId="ayuda-metodologia">
                Metodología
              </EtiquetaCampo>
              <input
                name="metodologia_txt"
                aria-describedby="ayuda-metodologia"
                className="mt-3 w-full rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta placeholder:text-tinta-suave focus:border-acento focus:outline-none focus:ring-2 focus:ring-acento/20"
                placeholder="PRISMA / DSRM / Mixta"
              />
            </label>
          </div>
        </section>

        <section className="rounded-xl border border-acento-borde bg-acento-claro/45 p-5 md:p-6" aria-labelledby="objetivo-proyecto-titulo">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-superficie text-acento shadow-[var(--sombra-1)]">
              <Icono tipo="objetivo" className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 id="objetivo-proyecto-titulo" className="text-base font-semibold text-tinta">
                Objetivo de investigación
              </h2>
              <p className="mt-0.5 text-sm text-tinta-suave">
                Explica qué quieres conocer o demostrar.
              </p>
            </div>
          </div>

          <textarea
            name="objetivo"
            rows={4}
            aria-label="Objetivo de investigación"
            className="mt-4 w-full resize-y rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta placeholder:text-tinta-suave focus:border-acento focus:outline-none focus:ring-2 focus:ring-acento/20"
            placeholder="Describe el objetivo principal…"
          />

          <div className="mt-4 flex items-start gap-2 rounded-lg border border-oro-borde bg-oro-claro px-3 py-2.5 text-xs leading-relaxed text-tinta-media">
            <span className="mt-0.5 shrink-0 text-oro-fuerte" aria-hidden="true">
              <Icono tipo="idea" className="h-4 w-4" />
            </span>
            <p>
              <span className="font-medium text-tinta">Consejo:</span> escribe un objetivo concreto; orientará la búsqueda de evidencia y la detección de brechas.
            </p>
          </div>
        </section>

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <label className="block">
            <EtiquetaCampo ayuda="Ayuda a contextualizar los artículos" ayudaId="ayuda-sector">
              Sector de investigación
            </EtiquetaCampo>
            <input
              name="sector_txt"
              aria-describedby="ayuda-sector"
              className="mt-3 w-full rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta placeholder:text-tinta-suave focus:border-acento focus:outline-none focus:ring-2 focus:ring-acento/20"
              placeholder="Educación / Salud / Industria"
            />
          </label>

          <label className="block">
            <EtiquetaCampo ayuda="Define cuántos estudios esperas incorporar" ayudaId="ayuda-articulos">
              Número de artículos (5–10)
            </EtiquetaCampo>
            <input
              name="n_articulos"
              type="number"
              min={5}
              max={10}
              defaultValue={5}
              aria-describedby="ayuda-articulos"
              className="mt-3 w-full rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta placeholder:text-tinta-suave focus:border-acento focus:outline-none focus:ring-2 focus:ring-acento/20"
            />
          </label>
        </div>

        <div className="flex items-center justify-between border-t border-borde pt-5">
          <Btn kind="gray" type="button" onClick={goBack}>
            Volver
          </Btn>
          <Btn kind="yellow" type="submit">
            Crear
          </Btn>
        </div>
      </form>

      <ErrorModal error={err} onClose={() => setErr(null)} />
    </Page>
  );
}

/* ============ 3) SUBIR ARTÍCULOS ============ */
function SubirArticulos({ proyecto, goBack }) {
  const [arts, setArts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [subiendo, setSubiendo] = useState(null); // { hecho, total, nombre }
  // El id del artículo que se está quitando, no un booleano: así el botón que
  // espera es solo el de esa fila y las demás siguen disponibles.
  const [quitando, setQuitando] = useState(null);
  const [confirmarQuitar, setConfirmarQuitar] = useState(null);
  const [fase, setFase] = useState(null); // { etapa, hecho, total, detalle }
  const [err, setErr] = useState(null);
  const avisar = useAviso();

  // useCallback y no una función suelta: el efecto la necesita como
  // dependencia, y sin memorizar se recrea en cada render, recargando la
  // lista en bucle.
  const load = useCallback(async () => {
    try {
      const data = await jget(`${API_BASE}/proyectos/${proyecto.id}/articulos`);
      setArts(Array.isArray(data) ? data : []);
    } catch (e) {
      setArts([]);
      setErr(e);
    }
  }, [proyecto.id]);

  useEffect(() => {
    load();
  }, [load]);

  // Reengancha un análisis que quedó en marcha.
  //
  // El progreso vivía solo en la memoria de la pestaña: quien lanzaba el
  // análisis y salía de la pantalla no volvía a verlo, así que el trabajo
  // seguía en el servidor pero la interfaz lo daba por perdido. Al abrir el
  // proyecto se pregunta si hay alguno en curso y, si lo hay, se sigue.
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const activo = await jget(`${API_BASE}/proyectos/${proyecto.id}/run_activo`);
        if (vivo && activo) {
          setBusy(true);
          await seguirRun(activo.id, activo.n_items_total, { reenganche: true });
        }
      } catch {
        // Sin análisis en curso o sin poder preguntarlo: la pantalla funciona
        // igual, solo que sin reenganche.
      } finally {
        if (vivo) setBusy(false);
      }
    })();
    return () => {
      vivo = false;
    };
    // Solo al abrir el proyecto: `seguirRun` se recrea en cada render y
    // ponerla aquí relanzaría el seguimiento sin parar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proyecto.id]);

  const objetivo = proyecto.n_articulos_objetivo ?? 0;
  // Antes se exigía el número exacto declarado al crear el proyecto. Ahora
  // basta con tener artículos: el objetivo orienta, no bloquea.
  const puedeAnalizar = arts.length > 0 && !busy;

  async function subirVarios(archivos) {
    setErr(null);
    setBusy(true);
    let ok = 0;
    let repetidos = 0;
    // Se actualiza durante el lote: `arts` es el estado de la última carga y
    // no cambia entre dos archivos seleccionados en la misma operación.
    const articulosConocidos = new Set(arts.map((a) => a.id));
    try {
      for (let i = 0; i < archivos.length; i++) {
        const f = archivos[i];
        setSubiendo({ hecho: i, total: archivos.length, nombre: f.name });
        const fd = new FormData();
        fd.append("pdf", f);
        // Sin Content-Type a mano: el navegador lo pone con el separador que
        // necesita el formulario multiparte.
        const r = await api(`${API_BASE}/proyectos/${proyecto.id}/archivos`, {
          method: "POST",
          body: fd,
        });
        if (!r.ok) {
          // El detalle se lee con el ayudante, no a mano: la versión anterior
          // reventaba al leer el cuerpo dos veces y la excepción se llevaba
          // por delante el `avisar` de abajo, así que un fallo del servidor se
          // veía como si no hubiera pasado nada.
          const detail = await leerDetalle(r);
          avisar(`No se pudo subir «${f.name}» (error ${r.status})`, "mal");
          console.error("Fallo al subir", f.name, r.status, detail);
          continue;
        }
        const cuerpo = await r.json();
        // El backend deduplica por hash: el mismo PDF dos veces no crea dos
        // artículos, y conviene decirlo en lugar de fingir que se subió.
        if (cuerpo?.articulo_id && articulosConocidos.has(cuerpo.articulo_id)) {
          repetidos++;
        } else {
          ok++;
          if (cuerpo?.articulo_id) articulosConocidos.add(cuerpo.articulo_id);
        }
      }
      await load();
      if (ok) avisar(`${ok} artículo${ok > 1 ? "s" : ""} añadido${ok > 1 ? "s" : ""}`, "bien");
      if (repetidos)
        avisar(`${repetidos} ya estaba${repetidos > 1 ? "n" : ""} en el proyecto`, "aviso");
    } finally {
      setSubiendo(null);
      setBusy(false);
    }
  }

  /**
   * Quita un artículo del proyecto.
   *
   * La confirmación se muestra como un modal del propio sistema para explicar
   * el alcance del borrado sin bloquear la página con `window.confirm`.
   */
  async function quitarArticulo(a) {
    if (!a) return;
    setQuitando(a.id);
    try {
      const r = await api(`${API_BASE}/proyectos/${proyecto.id}/articulos/${a.id}`, {
        method: "DELETE",
      });
      if (!r.ok) {
        const detail = await leerDetalle(r);
        // El 409 es el caso previsto —el artículo está en un análisis en
        // marcha—, y el servidor ya explica por qué. Repetirlo con palabras
        // propias solo serviría para que las dos versiones se separen.
        const motivo =
          (detail && (detail.detail || detail.message)) ||
          `No se pudo quitar (error ${r.status})`;
        avisar(motivo, r.status === 409 ? "aviso" : "mal");
        return;
      }
      await load();
      avisar("Artículo quitado", "bien");
    } catch (e) {
      setErr(e);
    } finally {
      setQuitando(null);
      // La confirmación se cierra pase lo que pase, y no solo al acertar.
      // Al pasar de `window.confirm` al modal propio dejó de cerrarse: tras
      // borrar con éxito seguía en pantalla, describiendo un artículo que ya
      // no existe y ofreciendo quitarlo otra vez —lo que daría un 404—. En el
      // 409 tampoco servía dejarla abierta: el aviso ya explica que hay un
      // análisis en marcha, y reintentar daría el mismo 409.
      setConfirmarQuitar(null);
    }
  }

  /**
   * Encola el análisis y sigue su avance.
   *
   * Antes el navegador conducía el trabajo: indexaba, pedía artículo por
   * artículo y sintetizaba al final. Funcionaba, pero exigía tener la pestaña
   * abierta de principio a fin, y cerrarla a mitad dejaba el lote colgado.
   *
   * Ahora se encola y quien procesa es `trabajador.py`. Esta pantalla solo
   * pregunta cómo va. Cerrarla no detiene nada: el estado vive en la base, y
   * al volver se recupera desde donde iba.
   */
  async function analizar() {
    setErr(null);
    setBusy(true);
    try {
      setFase({ etapa: "Poniendo el análisis en cola", hecho: 0, total: arts.length });
      const encolado = await jpost(`${API_BASE}/proyectos/${proyecto.id}/analizar_todo`, {});
      await seguirRun(encolado.run_id, arts.length);
    } catch (e) {
      // Si ya había uno en marcha, el backend responde 409 con su
      // identificador: se sigue ese en lugar de tratarlo como error.
      const enCurso = e?.detail?.detail?.run_id || e?.detail?.run_id;
      if (enCurso) {
        avisar("Ya había un análisis en curso; se muestra su avance.", "info");
        try {
          await seguirRun(enCurso, arts.length);
          return;
        } catch (e2) {
          setErr(e2);
          return;
        }
      }
      setErr(e);
    } finally {
      setFase(null);
      setBusy(false);
    }
  }

  /** Consulta el avance hasta que la ejecución termina. */
  async function seguirRun(runId, total, { reenganche = false } = {}) {
    // Dos segundos: lo bastante ágil para que el avance se vea moverse y lo
    // bastante espaciado para no castigar al servidor durante los minutos
    // que dura un lote.
    const INTERVALO = 2000;
    // Cuántas consultas seguidas puede pasar sin que nada avance antes de
    // sospechar que no hay ningún trabajador en marcha. Treinta segundos: un
    // artículo puede tardar más, pero no sin que ninguno esté siquiera
    // tomado.
    const VUELTAS_SIN_SENAL = 15;

    let quieto = 0;
    let ultimo = -1;

    if (reenganche) {
      avisar("Hay un análisis en curso; se muestra su avance.", "info");
    }

    for (;;) {
      const estado = await jget(`${API_BASE}/proyectos/runs/${runId}`);
      const hecho = estado.n_items_ok ?? 0;

      quieto = hecho === ultimo ? quieto + 1 : 0;
      ultimo = hecho;

      setFase({
        etapa: "Analizando artículos",
        hecho,
        total: estado.n_items_total ?? total,
        detalle:
          quieto >= VUELTAS_SIN_SENAL
            ? "Sin avance. Comprueba que el trabajador esté en marcha: python trabajador.py"
            : "Puedes cerrar esta página; el análisis sigue en el servidor.",
      });

      if (estado.estado === "completado") {
        avisar("Análisis completado", "bien");
        goBack();
        return;
      }
      if (estado.estado === "fallido") {
        avisar("El análisis no pudo completarse.", "mal");
        return;
      }
      await new Promise((r) => setTimeout(r, INTERVALO));
    }
  }

  return (
    <Page
      title="Artículos del proyecto"
      subtitle={proyecto.tema_principal}
    >
      <Seccion
        titulo="Carga de documentos"
        apoyo={`El proyecto se planteó con ${objetivo} artículos. Puedes subir más o analizar con los que tengas.`}
      >
        <ZonaArchivos
          onArchivos={subirVarios}
          disabled={busy}
          texto="Arrastra aquí los PDF o haz clic para elegirlos"
          apoyo="Puedes seleccionar varios a la vez. Se detectan título y DOI automáticamente."
        />

        {subiendo && (
          <div className="mt-4">
            <Progreso
              hecho={subiendo.hecho}
              total={subiendo.total}
              etiqueta={`Subiendo · ${subiendo.nombre}`}
            />
          </div>
        )}
      </Seccion>

      <Seccion
        titulo={`Artículos cargados (${arts.length})`}
        acciones={
          <>
            <Btn kind="gray" onClick={goBack} disabled={busy}>
              Volver
            </Btn>
            <Btn
              kind="yellow"
              onClick={analizar}
              disabled={!puedeAnalizar}
              title={
                arts.length === 0 ? "Sube al menos un artículo" : "Analizar el proyecto"
              }
            >
              {busy ? "Procesando…" : "Analizar"}
            </Btn>
          </>
        }
      >
        {arts.length === 0 ? (
          <Vacio titulo="Todavía no hay artículos">
            Sube los PDF de los artículos que quieras analizar. El sistema
            extraerá su título y su DOI, y localizará las secciones de cada uno.
          </Vacio>
        ) : (
          <Tabla>
            <thead>
              <tr>
                <Th>Artículo</Th>
                <Th ancho="15rem">DOI</Th>
                <Th ancho="8rem">Estado</Th>
                <Th ancho="7rem" className="text-right">
                  <span className="sr-only">Acciones</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {arts.map((a) => (
                <Fila key={a.id}>
                  <Td className="text-tinta">
                    <Recorte>{a.titulo || "(sin título detectado)"}</Recorte>
                  </Td>
                  <Td className="text-tinta-suave text-xs font-mono">
                    {a.doi || "—"}
                  </Td>
                  <Td>
                    <Estado tono="bien">Cargado</Estado>
                  </Td>
                  <Td className="text-right">
                    <Btn
                      kind="gray"
                      disabled={busy || quitando === a.id}
                      onClick={() => setConfirmarQuitar(a)}
                    >
                      {quitando === a.id ? "Quitando…" : "Quitar"}
                    </Btn>
                  </Td>
                </Fila>
              ))}
            </tbody>
          </Tabla>
        )}

        {arts.length > 0 && arts.length < objetivo && (
          <p className="mt-3 text-xs text-tinta-suave">
            Faltan {objetivo - arts.length} para alcanzar los {objetivo}{" "}
            planteados. Puedes analizar igualmente.
          </p>
        )}
      </Seccion>

      <Modal
        open={!!confirmarQuitar}
        onClose={() => {
          if (!quitando) setConfirmarQuitar(null);
        }}
        title="Quitar artículo del proyecto"
        ancho="max-w-lg"
        footer={
          <>
            <Btn
              kind="gray"
              type="button"
              disabled={!!quitando}
              onClick={() => setConfirmarQuitar(null)}
            >
              Cancelar
            </Btn>
            <Btn
              kind="danger"
              type="button"
              disabled={!!quitando}
              onClick={() => quitarArticulo(confirmarQuitar)}
            >
              {quitando ? "Quitando…" : "Quitar artículo"}
            </Btn>
          </>
        }
      >
        {confirmarQuitar && (
          <div className="space-y-4 text-sm">
            <div className="flex items-start gap-3">
              {/* El icono acompaña al aviso: en rojo solo cuando de verdad se
                  pierde algo. Un proyecto sin analizar no merece la señal de
                  alarma. */}
              <span
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
                  confirmarQuitar.tiene_analisis
                    ? "bg-mal-claro text-mal"
                    : "bg-hundido text-tinta-suave"
                }`}
              >
                <Icono tipo="documento" className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <p className="font-medium text-tinta">¿Quieres quitar este artículo?</p>
                <Recorte lineas={3}>{confirmarQuitar.titulo || "(sin título detectado)"}</Recorte>
              </div>
            </div>

            {/* El aviso se ajusta a lo que hay. Antes enumeraba «análisis,
                brechas, resúmenes, embeddings y métricas» siempre, también en
                un proyecto recién cargado donde nada de eso existe todavía:
                asustaba con la pérdida de algo que no había, justo en la
                pantalla donde lo normal es quitar un PDF equivocado antes de
                analizar. Una advertencia que exagera se acaba ignorando, y
                entonces no avisa el día que sí importa. */}
            {confirmarQuitar.tiene_analisis ? (
              <div className="rounded-lg border border-mal-borde bg-mal-claro px-3.5 py-3 leading-relaxed text-tinta-media">
                <p>
                  Este artículo ya se analizó. Se eliminarán el PDF del servidor
                  y todo lo obtenido de él: sus brechas, su resumen y sus
                  métricas.
                </p>
                <p className="mt-2 font-medium text-mal">
                  No se puede deshacer, y volver a subir el PDF no recupera el
                  análisis: habría que analizarlo de nuevo, gastando cuota.
                </p>
              </div>
            ) : (
              <div className="rounded-lg border border-borde bg-hundido px-3.5 py-3 leading-relaxed text-tinta-media">
                <p>
                  Todavía no se ha analizado, así que no se pierde ningún
                  resultado. Solo se elimina el PDF del servidor.
                </p>
                <p className="mt-2 text-tinta-suave">
                  Puedes volver a subirlo cuando quieras.
                </p>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Progreso real por etapa, en vez de un giro indefinido sin
          información de por dónde va el proceso. */}
      {fase && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-tinta/35 backdrop-blur-[2px]" />
          <div className="absolute inset-0 flex items-center justify-center p-6">
            <div
              className="w-full max-w-md rounded-2xl bg-lienzo border border-borde p-6"
              style={{ boxShadow: "var(--sombra-3)" }}
            >
              <div className="flex items-center gap-3 mb-5">
                <div className="h-8 w-8 shrink-0 rounded-full border-[3px] border-borde border-t-acento animate-spin" />
                <div className="min-w-0">
                  <p className="text-tinta font-medium leading-tight">
                    {fase.etapa}
                  </p>
                  {fase.detalle && (
                    <p className="text-xs text-tinta-suave truncate mt-0.5">
                      {fase.detalle}
                    </p>
                  )}
                </div>
              </div>

              <Progreso
                hecho={fase.hecho}
                total={fase.total}
                etiqueta="Progreso"
              />

              <p className="text-xs text-tinta-suave mt-4 leading-relaxed">
                Puede tardar unos minutos. El proceso avanza artículo por
                artículo, así que no se pierde lo ya hecho si algo falla.
              </p>
            </div>
          </div>
        </div>
      )}

      <ErrorModal error={err} onClose={() => setErr(null)} />
    </Page>
  );
}

/* ============ 4) BRECHAS DETECTADAS ============ */
function BrechasProyecto({ proyecto, goBack }) {
  const [arts, setArts] = useState([]);
  const [modal, setModal] = useState({ open: false, title: "", payload: null });
  const [err, setErr] = useState(null);
  const [ocupado, setOcupado] = useState(null); // "verificar" | "analizar"
  const [recarga, setRecarga] = useState(0);
  const avisar = useAviso();

  /**
   * Verifica la fidelidad de las brechas ya analizadas.
   *
   * Un proyecto analizado antes de que existiera N2 tiene sus brechas pero
   * sin verificar. Reanalizarlo entero costaría el doble de generaciones y
   * ademas sustituiría unos resultados que estaban bien, así que se verifica
   * sobre lo existente: una llamada por brecha en vez de dos.
   */
  async function verificarFidelidad(rehacer = false) {
    setErr(null);
    setOcupado(rehacer ? "rehacer" : "verificar");
    try {
      const r = await jpost(
        `${API_BASE}/proyectos/${proyecto.id}/verificar${
          rehacer ? "?rehacer=true" : ""
        }`
      );
      const sinRespaldo = (r.detalle || []).reduce(
        (n, d) => n + (d.sin_respaldo || 0),
        0
      );

      // `verificadas` cuenta las que se verificaron *en esta llamada*, no las
      // que están verificadas. Decir "0 de 5" cuando las cinco ya lo estaban
      // hacía pensar que había fallado, y era justo lo contrario: no había
      // nada que rehacer. La cuota es cara, así que no repetirlo es la
      // conducta correcta; solo hacía falta contarlo bien.
      const nuevas = r.verificadas ?? 0;
      const yaEstaban = (r.brechas ?? 0) - nuevas;

      let mensaje;
      if (nuevas === 0 && yaEstaban > 0) {
        mensaje =
          `Ya estaban verificadas las ${yaEstaban} brechas; no se repitió ` +
          "ninguna. Usa «Volver a verificar» si quieres rehacerlas.";
      } else {
        mensaje = `${nuevas} ${nuevas === 1 ? "brecha" : "brechas"} verificadas`;
        if (yaEstaban > 0) mensaje += ` · ${yaEstaban} ya lo estaban`;
      }
      if (sinRespaldo) {
        mensaje += ` · ${sinRespaldo} ${
          sinRespaldo === 1 ? "afirmación" : "afirmaciones"
        } sin respaldo en los fragmentos`;
      }

      avisar(mensaje, sinRespaldo ? "aviso" : "bien", 8000);
      setRecarga((v) => v + 1);
    } catch (e) {
      setErr(e);
    } finally {
      setOcupado(null);
    }
  }

  /** Vuelve a encolar el análisis completo del proyecto. */
  async function reanalizar() {
    setErr(null);
    setOcupado("analizar");
    try {
      const encolado = await jpost(
        `${API_BASE}/proyectos/${proyecto.id}/analizar_todo`, {});
      const runId = encolado.run_id;

      for (;;) {
        const estado = await jget(`${API_BASE}/proyectos/runs/${runId}`);
        if (estado.estado === "completado") break;
        if (estado.estado === "fallido") {
          avisar("El análisis no pudo completarse.", "mal");
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }

      avisar("Análisis completado", "bien");
      setRecarga((v) => v + 1);
    } catch (e) {
      const enCurso = e?.detail?.detail?.run_id || e?.detail?.run_id;
      if (enCurso) {
        avisar("Ya hay un análisis en curso para este proyecto.", "aviso");
        return;
      }
      setErr(e);
    } finally {
      setOcupado(null);
    }
  }

  // Matriz
  const [mx, setMx] = useState({
    open: false,
    rows: [],
    loading: false,
  });

  useEffect(() => {
    (async () => {
      try {
        const data = await jget(
          `${API_BASE}/proyectos/${proyecto.id}/articulos`
        );
        setArts(Array.isArray(data) ? data : []);
      } catch (e) {
        setArts([]);
        setErr(e);
      }
      // Las métricas las carga PanelMetricas desde /metricas, que sirve la
      // capa v2. El endpoint /metrics/resumen leía las columnas retiradas.
    })();
  }, [proyecto.id]);

  async function verBrechas(art) {
    try {
      const rows = await jget(`${API_BASE}/articulos/${art.id}/brechas`);
      if (!rows?.length) {
        setErr(new Error("Este artículo todavía no tiene brechas analizadas."));
        return;
      }
      // Antes se tomaba rows[0] y se descartaba el resto en silencio.
      setModal({ open: true, title: art.titulo || "Brecha", payload: rows });
    } catch (e) {
      setErr(e);
    }
  }

  async function abrirMatriz() {
    setErr(null);
    setMx((s) => ({ ...s, open: true, loading: true, rows: [] }));
    try {
      const data = await jget(
        `${API_BASE}/export/proyectos/${proyecto.id}/matriz.json`
      );
      setMx({
        open: true,
        rows: Array.isArray(data) ? data : [],
        loading: false,
      });
    } catch (e) {
      setMx({ open: true, rows: [], loading: false });
      setErr(e);
    }
  }

  return (
    <Page title="Resultados" subtitle={proyecto.tema_principal}>
      <Seccion
        titulo="Indicadores del proyecto"
        acciones={
          <>
            {/* Verificar cuesta la mitad que reanalizar y no sustituye unos
                resultados que ya estaban bien, asi que va primero. */}
            <Btn
              kind="blue"
              onClick={() => verificarFidelidad(false)}
              disabled={ocupado}
              title="Verifica solo las brechas que aún no lo estén"
            >
              {ocupado === "verificar" ? "Verificando…" : "Verificar fidelidad"}
            </Btn>

            {/* Rehacer una verificación ya pagada solo tiene sentido cuando el
                verificador ha mejorado, así que va aparte y avisando del coste.
                Sin este botón no había forma de aprovechar una mejora: el
                camino normal ve que están hechas y no toca nada. */}
            <Btn
              kind="ghost"
              onClick={() => {
                const n = arts.length || 0;
                const aviso =
                  `Se volverán a verificar todas las brechas desde cero.\n\n` +
                  `Cuesta aproximadamente ${n || "una"} ${
                    n === 1 ? "generación" : "generaciones"
                  } de tu cuota diaria.\n\n` +
                  "Tiene sentido si el verificador ha cambiado; si no, el " +
                  "resultado será el mismo y habrás gastado cuota.";
                if (window.confirm(aviso)) verificarFidelidad(true);
              }}
              disabled={ocupado}
              title="Rehace la verificación aunque ya esté hecha. Consume cuota."
            >
              {ocupado === "rehacer" ? "Rehaciendo…" : "Volver a verificar"}
            </Btn>

            <Btn kind="ghost" onClick={reanalizar} disabled={ocupado}>
              {ocupado === "analizar" ? "Analizando…" : "Volver a analizar"}
            </Btn>
          </>
        }
      >
        <div className="grid lg:grid-cols-[1fr_15rem] gap-5 items-start">
          <PanelMetricas key={recarga} proyectoId={proyecto.id} />
          <div className="flex flex-col gap-3">
            <IndicadorConsumo key={recarga} proyectoId={proyecto.id} />
            <Panel className="p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave mb-2">
                Exportar
              </div>
              <div className="flex flex-col gap-2">
                <Btn kind="ghost" onClick={abrirMatriz}>
                  Ver matriz
                </Btn>
                <Btn
                  kind="ghost"
                  onClick={async () => {
                    try {
                      await downloadFile(
                        `${API_BASE}/export/proyectos/${proyecto.id}/matriz.pdf`,
                        `matriz_${proyecto.id}.pdf`
                      );
                    } catch (e) {
                      setErr(e);
                    }
                  }}
                >
                  Matriz en PDF
                </Btn>
                <Btn
                  kind="ghost"
                  onClick={async () => {
                    try {
                      await downloadFile(
                        `${API_BASE}/export/proyectos/${proyecto.id}/brechas.csv`,
                        `brechas_${proyecto.id}.csv`
                      );
                    } catch (e) {
                      setErr(e);
                    }
                  }}
                >
                  Brechas en CSV
                </Btn>
              </div>
            </Panel>
          </div>
        </div>
      </Seccion>

      <Seccion
        titulo={`Artículos analizados (${arts.length})`}
        apoyo="Abre cualquiera para ver su brecha, su oportunidad y los fragmentos del artículo en los que se apoyó el análisis."
        acciones={
          <Btn kind="gray" onClick={goBack}>
            Volver
          </Btn>
        }
      >
        {arts.length === 0 ? (
          <Vacio titulo="Sin artículos en este proyecto" />
        ) : (
          <Tabla>
            <thead>
              <tr>
                <Th>Artículo</Th>
                <Th ancho="14rem">DOI</Th>
                <Th ancho="7rem" className="text-right">
                  <span className="sr-only">Acciones</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {arts.map((a) => (
                <Fila key={a.id}>
                  <Td className="text-tinta">
                    <Recorte>{a.titulo || "(sin título)"}</Recorte>
                  </Td>
                  <Td className="text-tinta-suave text-xs font-mono">
                    {a.doi || "—"}
                  </Td>
                  <Td className="text-right">
                    <Btn kind="blue" onClick={() => verBrechas(a)}>
                      Ver brecha
                    </Btn>
                  </Td>
                </Fila>
              ))}
            </tbody>
          </Tabla>
        )}
      </Seccion>

      {/* Modal detalle de una brecha */}
      <Modal
        open={modal.open}
        onClose={() => setModal({ open: false, title: "", payload: null })}
        title={modal.title}
        footer={
          <Btn
            kind="gray"
            onClick={() => setModal({ open: false, title: "", payload: null })}
          >
            Cerrar
          </Btn>
        }
      >
        {/* Se destaca la brecha vigente y las anteriores quedan plegadas.
            Cada análisis del proyecto genera una brecha nueva y se conserva
            el histórico, pero mostrarlas todas al mismo nivel hacía parecer
            que el artículo tenía varias brechas simultáneas. */}
        {Array.isArray(modal.payload) && modal.payload.length > 0 && (
          <div className="space-y-4">
            <DetalleBrecha brecha={modal.payload[0]} />

            {modal.payload.length > 1 && (
              <details className="border rounded-lg">
                <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg text-sm">
                  Análisis anteriores de este artículo (
                  {modal.payload.length - 1})
                </summary>
                <div className="p-3 space-y-6">
                  <p className="text-xs text-tinta-media">
                    Cada vez que se analiza el proyecto se genera una brecha
                    nueva y se conserva la anterior, de modo que puedas
                    comparar cómo cambia el resultado al ajustar el sistema.
                    Arriba se muestra siempre la más reciente.
                  </p>
                  {modal.payload.slice(1).map((b) => (
                    <div key={b.id} className="border-t pt-4">
                      <div className="text-xs text-tinta-suave mb-2">
                        {new Date(b.creado_en).toLocaleString()}
                      </div>
                      <DetalleBrecha brecha={b} />
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </Modal>

      {/* Modal de Matriz */}
      <Modal
        open={mx.open}
        onClose={() => setMx({ open: false, rows: [], loading: false })}
        title="Matriz de brechas (Artículo • DOI • Brecha • Oportunidad)"
        footer={
          <>
            <Btn
              kind="yellow"
              onClick={async () => {
                try {
                  await downloadFile(
                    `${API_BASE}/export/proyectos/${proyecto.id}/matriz.pdf`,
                    `matriz_${proyecto.id}.pdf`
                  );
                } catch (e) {
                  console.error(e);
                }
              }}
            >
              Descargar (PDF)
            </Btn>
            <Btn
              kind="gray"
              onClick={() => setMx({ open: false, rows: [], loading: false })}
            >
              Cerrar
            </Btn>
          </>
        }
      >
        {mx.loading ? (
          <div className="text-tinta-media">Cargando matriz…</div>
        ) : mx.rows.length === 0 ? (
          <div className="text-tinta-media">No hay datos para la matriz.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-hundido text-left text-tinta-media">
                <tr>
                  <th className="px-3 py-2">Artículo</th>
                  <th className="px-3 py-2">DOI</th>
                  <th className="px-3 py-2">Brecha</th>
                  <th className="px-3 py-2">Oportunidad</th>
                </tr>
              </thead>
              <tbody>
                {mx.rows.map((r, i) => (
                  <tr
                    key={i}
                    className="border-t border-borde align-top hover:bg-hundido/60"
                  >
                    <td className="px-3 py-2">{r.titulo}</td>
                    <td className="px-3 py-2">{r.doi}</td>
                    <td className="px-3 py-2 whitespace-pre-wrap">
                      {r.brecha}
                    </td>
                    <td className="px-3 py-2 whitespace-pre-wrap">
                      {r.oportunidad}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      <ErrorModal error={err} onClose={() => setErr(null)} />
    </Page>
  );
}

/* ============== CARGA DE UN PROYECTO POR SU URL ============== */
/**
 * Resuelve el proyecto que nombra la dirección y monta la pantalla.
 *
 * Antes el proyecto llegaba como objeto desde la lista, así que solo se podía
 * entrar pasando por ella. Con direcciones propias hay que poder llegar de
 * frente: pegando el enlace, recargando o volviendo con el botón atrás. En
 * esos casos lo único que se tiene es el identificador, y el proyecto hay que
 * pedirlo.
 */
function useProyectoDeLaUrl() {
  const { id } = useParams();
  const [proyecto, setProyecto] = useState(null);
  const [estado, setEstado] = useState("cargando"); // cargando | listo | ausente

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const p = await jget(`${API_BASE}/proyectos/${id}`);
        if (!vivo) return;
        setProyecto(p);
        setEstado("listo");
      } catch {
        // Un proyecto ajeno responde 404 igual que uno inexistente, así que
        // aquí no se puede —ni se debe— distinguir: para quien pregunta, no
        // existe.
        if (vivo) setEstado("ausente");
      }
    })();
    return () => {
      vivo = false;
    };
  }, [id]);

  return { proyecto, estado };
}

/** Lo que se ve mientras se busca el proyecto, o si no aparece. */
function ProyectoNoDisponible({ estado, onVolver }) {
  if (estado === "cargando") {
    return (
      <Page title="Cargando…">
        <Panel>
          <div className="p-6 text-sm text-tinta-media">Buscando el proyecto…</div>
        </Panel>
      </Page>
    );
  }
  return (
    <Page
      title="Proyecto no encontrado"
      subtitle="Puede que el enlace esté mal, que el proyecto se haya borrado o que no sea de tu cuenta."
    >
      <Panel>
        <div className="p-6">
          <Btn kind="blue" onClick={onVolver}>
            Ir a mis proyectos
          </Btn>
        </div>
      </Panel>
    </Page>
  );
}

function RutaArticulos() {
  const { proyecto, estado } = useProyectoDeLaUrl();
  const navegar = useNavigate();
  const volver = () => navegar("/proyectos");

  if (estado !== "listo") {
    return <ProyectoNoDisponible estado={estado} onVolver={volver} />;
  }
  return <SubirArticulos proyecto={proyecto} goBack={volver} />;
}

function RutaBrechas() {
  const { proyecto, estado } = useProyectoDeLaUrl();
  const navegar = useNavigate();
  const volver = () => navegar("/proyectos");

  if (estado !== "listo") {
    return <ProyectoNoDisponible estado={estado} onVolver={volver} />;
  }
  return <BrechasProyecto proyecto={proyecto} goBack={volver} />;
}

/* ============== APP ============== */
export default function App() {
  const [fontSize, setFontSize] = useState(16); // tamaño base
  const navegar = useNavigate();
  const lugar = useLocation();

  // Sesión. Se lee de localStorage al arrancar para que recargar la página no
  // obligue a volver a entrar.
  const [sesion, setSesion] = useState(() => leerSesion());

  // El módulo de sesión avisa cuando el servidor rechaza el token. Se
  // registra una sola vez: si cada pantalla tuviera que interpretar el 401,
  // unas lo harían y otras mostrarían un error incomprensible.
  useEffect(() => {
    alExpirar(() => setSesion(null));
  }, []);

  function salir() {
    cerrarSesion();
    setSesion(null);
    navegar("/", { replace: true });
  }

  // Tema claro u oscuro. Se respeta la preferencia del sistema la primera vez
  // y se recuerda la elección: en sesiones largas de lectura es lo primero
  // que se ajusta y molesta tener que repetirlo.
  const [tema, setTema] = useState(() => {
    const guardado = localStorage.getItem("tema");
    if (guardado) return guardado;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "oscuro"
      : "claro";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-tema", tema);
    localStorage.setItem("tema", tema);
  }, [tema]);

  const increaseFont = () => {
    setFontSize((prev) => (prev < 22 ? prev + 2 : prev));
  };

  const decreaseFont = () => {
    setFontSize((prev) => (prev > 14 ? prev - 2 : prev));
  };

  const goCreate = () => navegar("/proyectos/nuevo");
  const goList = () => navegar("/proyectos");

  /**
   * Abre un proyecto por la puerta que le corresponde.
   *
   * Con estado del arte ya generado interesan las brechas; sin él, lo que toca
   * es subir artículos. La comprobación se hace aquí y no dentro de las
   * pantallas para que la dirección resultante sea explícita: quien copie el
   * enlace se lleva la vista concreta, no un "depende".
   */
  async function goProyecto(p) {
    let tieneSota = false;
    try {
      await jget(`${API_BASE}/proyectos/${p.id}/estado_arte/latest`);
      tieneSota = true;
    } catch {
      // Sin estado del arte todavía: se entra por la pantalla de subida.
    }
    navegar(`/proyectos/${p.id}/${tieneSota ? "brechas" : "articulos"}`);
  }

  // Sin sesión no se monta nada más: el backend rechazaría cada llamada y la
  // pantalla se llenaría de errores en lugar de pedir que entres.
  //
  // La dirección a la que se quería ir se guarda para volver a ella después de
  // entrar. Sin eso, abrir el enlace de un proyecto con la sesión caducada
  // dejaba al usuario en el inicio, teniendo que buscarlo otra vez.
  if (!sesion) {
    return (
      <div style={{ fontSize: `${fontSize}px` }}>
        <Login
          apiBase={API_BASE}
          onEntrar={(datos) => {
            setSesion(datos);
            if (lugar.pathname !== "/") navegar(lugar.pathname + lugar.search);
          }}
        />
      </div>
    );
  }

  const content = (
    <Routes>
      <Route path="/" element={<WelcomeScreen onStart={goCreate} onList={goList} />} />
      <Route
        path="/proyectos"
        element={<Lista goCreate={goCreate} goProyecto={goProyecto} />}
      />
      <Route path="/proyectos/nuevo" element={<CrearProyecto goBack={goList} />} />
      <Route path="/proyectos/:id/articulos" element={<RutaArticulos />} />
      <Route path="/proyectos/:id/brechas" element={<RutaBrechas />} />
      {/* Cualquier otra dirección vuelve al inicio en lugar de dejar la
          pantalla en blanco, que es lo que más desconcierta. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );

  return (
    <ProveedorAvisos>
    <div style={{ fontSize: `${fontSize}px` }}>
      {/* Controles de lectura, fijos arriba a la derecha. */}
      <div
        className="fixed top-3 right-4 z-50 flex items-center gap-1 bg-lienzo/90 backdrop-blur px-2 py-1.5 rounded-full border border-borde"
        style={{ boxShadow: "var(--sombra-1)" }}
      >
        <span className="text-[11px] text-tinta-suave px-1.5 select-none">
          Texto
        </span>
        <button
          onClick={decreaseFont}
          title="Reducir el tamaño del texto"
          aria-label="Reducir el tamaño del texto"
          className="text-xs w-7 h-7 grid place-items-center border border-borde rounded-full text-tinta-media hover:bg-hundido hover:text-tinta transition-colors"
        >
          A−
        </button>
        <button
          onClick={increaseFont}
          title="Aumentar el tamaño del texto"
          aria-label="Aumentar el tamaño del texto"
          className="text-xs w-7 h-7 grid place-items-center border border-borde rounded-full text-tinta-media hover:bg-hundido hover:text-tinta transition-colors"
        >
          A+
        </button>

        <span className="w-px h-5 bg-borde mx-1" />

        <button
          onClick={() => setTema((t) => (t === "oscuro" ? "claro" : "oscuro"))}
          title={tema === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
          aria-label={
            tema === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"
          }
          className="w-7 h-7 grid place-items-center border border-borde rounded-full text-tinta-media hover:bg-hundido hover:text-tinta transition-colors"
        >
          {tema === "oscuro" ? (
            /* Sol */
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </svg>
          ) : (
            /* Luna */
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                 strokeLinejoin="round">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            </svg>
          )}
        </button>

        <span className="w-px h-5 bg-borde mx-1" />

        <button
          onClick={salir}
          title={`Salir de la sesión de ${sesion.usuario?.correo || ""}`}
          aria-label="Cerrar sesión"
          className="text-[11px] px-2.5 h-7 grid place-items-center border border-borde rounded-full text-tinta-media hover:bg-hundido hover:text-tinta transition-colors"
        >
          Salir
        </button>
      </div>

      {content}
    </div>
    </ProveedorAvisos>
  );
}
