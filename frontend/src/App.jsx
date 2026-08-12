import { useEffect, useState } from "react";
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
  useAviso,
} from "./components/UI";

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
function Modal({ open, onClose, title, children, footer }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-tinta/35 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl rounded-2xl bg-lienzo border border-borde overflow-hidden"
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
async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let detail;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text();
    }
    const err = new Error(`GET ${url} → ${r.status}`);
    err.detail = detail;
    throw err;
  }
  return r.json();
}
async function jpost(url, body) {
  const r = await fetch(url, {
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
  const r = await fetch(url);
  if (!r.ok) {
    let detail;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text();
    }
    const err = new Error(`DOWNLOAD ${url} → ${r.status}`);
    err.detail = detail;
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
      const proyectos = await jget(`${API_BASE}/proyectos`);
      const enr = await Promise.all(
        proyectos.map(async (p) => {
          let articulos = [];
          let estadoArte = null;
          try {
            articulos = await jget(`${API_BASE}/proyectos/${p.id}/articulos`);
          } catch {}
          try {
            estadoArte = await jget(
              `${API_BASE}/proyectos/${p.id}/estado_arte/latest`
            );
          } catch {}
          return {
            ...p,
            articulos_count: Array.isArray(articulos) ? articulos.length : 0,
            tiene_sota: !!estadoArte,
          };
        })
      );
      setRows(enr);
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
    <Page title="Proyectos" subtitle="Cada proyecto reúne un tema, sus artículos y el estado del arte generado a partir de ellos.">
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
          <Tabla>
            <thead>
              <tr>
                <Th>Tema</Th>
                <Th ancho="7rem">Artículos</Th>
                <Th ancho="11rem">Estado del arte</Th>
                <Th ancho="9rem" className="text-right">
                  <span className="sr-only">Acciones</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <Fila key={p.id}>
                  <Td>
                    <div className="text-tinta font-medium leading-snug">
                      <Recorte>{p.tema_principal || "(Sin tema)"}</Recorte>
                    </div>
                  </Td>
                  <Td className="text-tinta-media tabular-nums">
                    {p.articulos_count ?? 0}
                    <span className="text-tinta-suave">
                      {" "}
                      / {p.n_articulos_objetivo ?? "—"}
                    </span>
                  </Td>
                  <Td>
                    {p.tiene_sota ? (
                      <button
                        onClick={() => verSOTA(p.id)}
                        className="text-left"
                      >
                        <Estado tono="bien">Generado · ver</Estado>
                      </button>
                    ) : (
                      <Estado tono="neutro">Sin generar</Estado>
                    )}
                  </Td>
                  <Td className="text-right">
                    <Btn kind="blue" onClick={() => goProyecto(p)}>
                      Abrir
                    </Btn>
                  </Td>
                </Fila>
              ))}
            </tbody>
          </Tabla>
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
        className="grid grid-cols-1 md:grid-cols-2 gap-6"
      >
        <label className="block">
          <span className="text-sm">Tema principal</span>
          <input
            name="tema_principal"
            className="mt-1 w-full rounded border px-3 py-2"
            required
            placeholder="Ej: IA generativa en educación"
          />
        </label>
        <label className="block">
          <span className="text-sm">Metodología</span>
          <input
            name="metodologia_txt"
            className="mt-1 w-full rounded border px-3 py-2"
            placeholder="PRISMA / DSRM / Mixta"
          />
        </label>
        <label className="block md:col-span-2">
          <span className="text-sm">Objetivo de investigación</span>
          <textarea
            name="objetivo"
            rows={4}
            className="mt-1 w-full rounded border px-3 py-2"
            placeholder="Describa el objetivo principal…"
          />
        </label>
        <label className="block">
          <span className="text-sm">Sector de investigación</span>
          <input
            name="sector_txt"
            className="mt-1 w-full rounded border px-3 py-2"
            placeholder="Educación / Salud / Industria"
          />
        </label>
        <label className="block">
          <span className="text-sm">Número de artículos (5–10)</span>
          <input
            name="n_articulos"
            type="number"
            min={5}
            max={10}
            defaultValue={5}
            className="mt-1 w-full rounded border px-3 py-2"
          />
        </label>
        <div className="md:col-span-2 flex justify-between">
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
  const [fase, setFase] = useState(null); // { etapa, hecho, total, detalle }
  const [err, setErr] = useState(null);
  const avisar = useAviso();

  async function load() {
    try {
      const data = await jget(`${API_BASE}/proyectos/${proyecto.id}/articulos`);
      setArts(Array.isArray(data) ? data : []);
    } catch (e) {
      setArts([]);
      setErr(e);
    }
  }
  useEffect(() => {
    load();
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
    try {
      for (let i = 0; i < archivos.length; i++) {
        const f = archivos[i];
        setSubiendo({ hecho: i, total: archivos.length, nombre: f.name });
        const fd = new FormData();
        fd.append("pdf", f);
        const r = await fetch(`${API_BASE}/proyectos/${proyecto.id}/archivos`, {
          method: "POST",
          body: fd,
        });
        if (!r.ok) {
          let detail;
          try {
            detail = await r.json();
          } catch {
            detail = await r.text();
          }
          avisar(`No se pudo subir «${f.name}»`, "mal");
          console.error(detail);
          continue;
        }
        const cuerpo = await r.json();
        // El backend deduplica por hash: el mismo PDF dos veces no crea dos
        // artículos, y conviene decirlo en lugar de fingir que se subió.
        if (cuerpo?.archivo_id && arts.some((a) => a.id === cuerpo.articulo_id)) {
          repetidos++;
        } else {
          ok++;
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
   * Análisis por pasos, conducido desde el navegador.
   *
   * Antes se llamaba a `analizar_todo`, que indexa y analiza todo dentro de
   * una sola petición: varios minutos sin respuesta, sin saber por dónde iba
   * y perdiendo el lote entero si la conexión se cortaba.
   *
   * Aquí se encadenan las peticiones cortas que el backend ya ofrecía, de
   * modo que cada paso responde enseguida y el progreso es real. No sustituye
   * al procesamiento en segundo plano que hará falta más adelante, pero
   * elimina el problema de fondo sin esperar a esa reforma.
   */
  async function analizar() {
    setErr(null);
    setBusy(true);
    try {
      // 1) Indexar. Es idempotente: lo ya indexado no se vuelve a pagar.
      for (let i = 0; i < arts.length; i++) {
        setFase({
          etapa: "Indexando artículos",
          hecho: i,
          total: arts.length,
          detalle: arts[i].titulo || "(sin título)",
        });
        try {
          await jpost(`${API_BASE}/embeddings/index/${arts[i].id}`);
        } catch (e) {
          avisar(`No se pudo indexar «${arts[i].titulo || "artículo"}»`, "aviso");
          console.error(e);
        }
      }

      // 2) Crear la ejecución.
      setFase({ etapa: "Preparando el análisis", hecho: 0, total: arts.length });
      const run = await jpost(`${API_BASE}/proyectos/${proyecto.id}/runs`, {});

      // 3) Procesar artículo a artículo, con progreso real.
      let estado = run;
      let vueltas = 0;
      while (estado.estado !== "completado" && vueltas <= arts.length + 2) {
        setFase({
          etapa: "Analizando artículos",
          hecho: estado.n_items_ok ?? 0,
          total: estado.n_items_total ?? arts.length,
        });
        estado = await jpost(`${API_BASE}/runs/${run.id}/process_next`, {});
        vueltas++;
      }

      // 4) Sintetizar el estado del arte.
      setFase({
        etapa: "Redactando el estado del arte",
        hecho: estado.n_items_ok ?? arts.length,
        total: estado.n_items_total ?? arts.length,
      });
      await jpost(`${API_BASE}/proyectos/${proyecto.id}/estado_arte`, {});

      avisar("Análisis completado", "bien");
      goBack();
    } catch (e) {
      setErr(e);
    } finally {
      setFase(null);
      setBusy(false);
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
      <Seccion titulo="Indicadores del proyecto">
        <div className="grid lg:grid-cols-[1fr_15rem] gap-5 items-start">
          <PanelMetricas proyectoId={proyecto.id} />
          <div className="flex flex-col gap-3">
            <IndicadorConsumo proyectoId={proyecto.id} />
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

/* ============== APP ROUTER ============== */
export default function App() {
  const [view, setView] = useState("welcome"); // welcome | list | create | subir | brechas
  const [proyectoSel, setProyectoSel] = useState(null);
  const [fontSize, setFontSize] = useState(16); // tamaño base

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

  function goCreate() {
    setView("create");
  }
  function goList() {
    setProyectoSel(null);
    setView("list");
  }
  async function goProyecto(p) {
    let tieneSota = false;
    try {
      await jget(`${API_BASE}/proyectos/${p.id}/estado_arte/latest`);
      tieneSota = true;
    } catch {}
    setProyectoSel(p);
    setView(tieneSota ? "brechas" : "subir");
  }

  let content = null;
  if (view === "welcome")
    content = <WelcomeScreen onStart={goCreate} onList={goList} />;
  else if (view === "create") content = <CrearProyecto goBack={goList} />;
  else if (view === "subir" && proyectoSel)
    content = <SubirArticulos proyecto={proyectoSel} goBack={goList} />;
  else if (view === "brechas" && proyectoSel)
    content = <BrechasProyecto proyecto={proyectoSel} goBack={goList} />;
  else content = <Lista goCreate={goCreate} goProyecto={goProyecto} />;

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
      </div>

      {content}
    </div>
    </ProveedorAvisos>
  );
}
