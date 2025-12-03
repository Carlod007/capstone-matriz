import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/* ---------------- UI core ---------------- */
function Page({ title, subtitle, children }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 via-white to-white">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-semibold mb-1">{title}</h1>
        {subtitle && <p className="text-sm text-gray-600 mb-6">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}
function Btn({ children, kind = "ghost", ...props }) {
  const k = {
    ghost:
      "border rounded-lg px-4 py-2 bg-white hover:bg-gray-50 transition-colors",
    blue: "rounded-lg px-4 py-2 border border-blue-600 text-blue-700 bg-white hover:bg-blue-50 transition-colors",
    green:
      "rounded-lg px-4 py-2 border border-green-600 text-green-700 bg-white hover:bg-green-50 transition-colors",
    yellow:
      "rounded-lg px-4 py-2 bg-yellow-400 hover:bg-yellow-500 text-black font-medium transition-transform active:scale-[0.98]",
    gray: "rounded-lg px-4 py-2 bg-gray-200 hover:bg-gray-300 transition-colors",
    danger:
      "rounded-lg px-4 py-2 bg-red-50 border border-red-500 text-red-700 hover:bg-red-100 transition-colors",
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="w-full max-w-5xl rounded-2xl bg-white shadow-2xl overflow-hidden">
        <div className="p-4 border-b">
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        <div className="p-6 max-h-[80vh] overflow-y-auto">{children}</div>
        <div className="p-4 border-t flex flex-wrap gap-2 justify-end bg-gray-50">
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
      <div className="absolute inset-0 bg-black/40" />
      <div className="absolute inset-0 flex items-center justify-center p-6">
        <div className="w-full max-w-md rounded-2xl bg-white shadow-xl p-6 text-center">
          <div className="mx-auto mb-4 h-10 w-10 rounded-full border-4 border-gray-200 border-t-gray-700 animate-spin" />
          <p className="text-gray-800 font-medium">{text}</p>
          <p className="text-xs text-gray-500 mt-1">
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
      <div className="text-sm text-red-700">
        {typeof error === "string"
          ? error
          : error?.message || "Ocurrió un error"}
      </div>
      {error?.detail && (
        <pre className="mt-3 text-xs p-3 bg-red-50 border border-red-200 rounded whitespace-pre-wrap">
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
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="max-w-5xl mx-auto px-4 py-16">
        <div className="rounded-3xl bg-white shadow-xl border border-gray-100 overflow-hidden">
          <div className="p-8 md:p-12 grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 text-xs font-medium mb-4">
                <span className="h-2 w-2 rounded-full bg-indigo-500"></span>
                Matriz de brechas con IAG
              </div>
              <h1 className="text-3xl md:text-4xl font-bold text-gray-900 leading-tight">
                Bienvenido 👋
              </h1>
              <p className="mt-3 text-gray-600">
                Este asistente te ayuda a cargar artículos científicos,
                analizarlos y generar automáticamente brechas y estado del arte.
                Puedes iniciar creando un tema o revisar tus proyectos
                existentes.
              </p>

              <ul className="mt-6 space-y-2 text-sm text-gray-700">
                <li className="flex items-start gap-2">
                  <span className="mt-[6px] h-2 w-2 rounded-full bg-gray-300"></span>
                  Crea un tema y define tu objetivo (PRISMA/DSRM, etc.)
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-[6px] h-2 w-2 rounded-full bg-gray-300"></span>
                  Sube PDFs con DOI y ejecuta el análisis
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-[6px] h-2 w-2 rounded-full bg-gray-300"></span>
                  Consulta brechas, oportunidades y estado del arte generado
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-[6px] h-2 w-2 rounded-full bg-gray-300"></span>
                  Descarga la matriz (PDF) y el dashboard de métricas
                </li>
              </ul>

              <div className="mt-8 flex flex-wrap gap-3">
                <Btn kind="yellow" onClick={onStart}>
                  Comenzar
                </Btn>
                <Btn kind="blue" onClick={onList}>
                  Ir a proyectos
                </Btn>
              </div>
            </div>

            <div className="relative">
              <div className="absolute -inset-6 rounded-3xl bg-gradient-to-tr from-yellow-100 via-purple-100 to-indigo-100 blur-2xl opacity-60" />
              <div className="relative rounded-2xl border bg-white p-6 shadow-md">
                <div className="text-sm text-gray-800 font-medium">
                  Vista previa
                </div>
                <div className="mt-3 space-y-2 text-xs text-gray-600">
                  <div className="rounded-lg border p-3">
                    <div className="text-gray-500">Proyecto</div>
                    <div className="font-medium">
                      IA generativa en educación
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-gray-500">Artículos</div>
                    <div className="font-medium">5 / 5</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-gray-500">Acciones</div>
                    <div className="font-medium">
                      Analizar • Matriz PDF • Dashboard
                    </div>
                  </div>
                </div>
                <div className="mt-4 text-[10px] text-gray-400">
                  * Ilustrativo
                </div>
              </div>
            </div>
          </div>

          <div className="px-8 py-4 bg-gray-50/60 border-t text-xs text-gray-500">
            Requiere backend activo para procesar artículos.
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
    <Page
      title="Lista"
      subtitle="Para generar el estado del arte, sube como mínimo 5 artículos en PDF con DOI."
    >
      <div className="overflow-x-auto bg-white border rounded-xl shadow-sm">
        <table className="min-w-full">
          <thead className="bg-gray-100 text-left">
            <tr>
              <th className="px-4 py-3">Tema</th>
              <th className="px-4 py-3 w-28">Artículos</th>
              <th className="px-4 py-3 w-44">Estado del arte</th>
              <th className="px-4 py-3 w-40">Detalles</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td className="px-4 py-5 text-gray-500" colSpan={4}>
                  Cargando…
                </td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-gray-500" colSpan={4}>
                  Sin proyectos. Crea uno nuevo.
                </td>
              </tr>
            )}
            {rows.map((p) => (
              <tr key={p.id} className="border-t hover:bg-gray-50/60">
                <td className="px-4 py-4">
                  {p.tema_principal || "(Sin tema)"}
                </td>
                <td className="px-4 py-4">{p.articulos_count ?? 0}</td>
                <td className="px-4 py-4">
                  {p.tiene_sota ? (
                    <Btn kind="green" onClick={() => verSOTA(p.id)}>
                      Ver
                    </Btn>
                  ) : (
                    <span className="text-gray-600">No generado</span>
                  )}
                </td>
                <td className="px-4 py-4">
                  <Btn kind="blue" onClick={() => goProyecto(p)}>
                    Ingresar
                  </Btn>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex justify-end">
        <Btn kind="yellow" onClick={goCreate}>
          Crear tema
        </Btn>
      </div>

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
            <div className="text-gray-600">
              Versión:{" "}
              <span className="font-medium">{sotaModal.data.version}</span> ·{" "}
              Fecha:{" "}
              <span className="font-medium">
                {new Date(sotaModal.data.created_at).toLocaleString()}
              </span>
            </div>
            <article className="whitespace-pre-wrap leading-relaxed border rounded-lg p-4 bg-gray-50 text-gray-800 text-justify">
              {sotaModal.data.texto}
            </article>
          </div>
        ) : (
          <div className="text-gray-500">Cargando…</div>
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

  return (
    <Page
      title="Configuración de tema"
      subtitle="Ingresa los datos del tema de investigación"
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
            alert("Proyecto creado");
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
  const [overlay, setOverlay] = useState({ show: false, text: "Procesando…" });
  const [err, setErr] = useState(null);

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
  const faltantes = Math.max(0, objetivo - arts.length);
  const filas = [...arts, ...Array.from({ length: faltantes }).map(() => null)];
  const puedeAnalizar = arts.length >= objetivo && arts.length > 0;

  async function subirPDF(file) {
    setErr(null);
    const fd = new FormData();
    fd.append("pdf", file);
    try {
      setBusy(true);
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
        const err = new Error(`POST /archivos → ${r.status}`);
        err.detail = detail;
        throw err;
      }
      await load(); // refresca título y DOI
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }
  function seleccionarArchivo() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf";
    input.onchange = (e) => {
      const file = e.target.files?.[0];
      if (file) subirPDF(file);
    };
    input.click();
  }

  async function analizarTodo() {
    setErr(null);
    try {
      setOverlay({ show: true, text: "Ejecutando análisis de artículos…" });
      setBusy(true);
      await jpost(`${API_BASE}/proyectos/${proyecto.id}/analizar_todo`, {});
      setOverlay({ show: true, text: "Listo. Generando estado del arte…" });
      alert("Análisis completado");
      goBack(); // vuelve a Lista
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
      setOverlay({ show: false, text: "Procesando…" });
    }
  }

  return (
    <Page
      title="Subir artículos"
      subtitle={`Suba ${objetivo} artículos en PDF`}
    >
      <div className="overflow-x-auto bg-white border rounded-xl shadow-sm">
        <table className="min-w-full">
          <thead className="bg-gray-800 text-white">
            <tr>
              <th className="px-4 py-3 text-left">Nombre del artículo</th>
              <th className="px-4 py-3 w-60 text-left">DOI</th>
              <th className="px-4 py-3 w-40 text-left">Acción</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((row, idx) => (
              <tr key={idx} className="border-t">
                <td className="px-4 py-3">
                  {row ? (
                    row.titulo || "(sin título detectado)"
                  ) : (
                    <em className="text-gray-500">Pendiente</em>
                  )}
                </td>
                <td className="px-4 py-3">{row ? row.doi || "—" : "—"}</td>
                <td className="px-4 py-3">
                  {row ? (
                    <span className="text-green-700 font-medium">Cargado</span>
                  ) : (
                    <Btn
                      kind="yellow"
                      disabled={busy}
                      onClick={seleccionarArchivo}
                    >
                      Subir PDF
                    </Btn>
                  )}
                </td>
              </tr>
            ))}
            {filas.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-5 text-gray-500 text-center">
                  Sin filas
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-sm text-gray-600">
        Cargados: <span className="font-semibold">{arts.length}</span> /{" "}
        {objetivo}
      </div>

      <div className="mt-6 flex justify-between items-center">
        <Btn kind="gray" onClick={goBack} disabled={busy}>
          Volver
        </Btn>
        <Btn
          kind="yellow"
          onClick={analizarTodo}
          disabled={busy || !puedeAnalizar}
          title={
            !puedeAnalizar
              ? "Sube todos los artículos indicados para habilitar el análisis"
              : ""
          }
        >
          {busy ? "Procesando…" : "Analizar todo"}
        </Btn>
      </div>

      <LoadingOverlay show={overlay.show} text={overlay.text} />
      <ErrorModal error={err} onClose={() => setErr(null)} />
    </Page>
  );
}

/* ============ 4) BRECHAS DETECTADAS ============ */
function BrechasProyecto({ proyecto, goBack }) {
  const [arts, setArts] = useState([]);
  const [metrics, setMetrics] = useState(null);
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
      try {
        const m = await jget(
          `${API_BASE}/proyectos/${proyecto.id}/metrics/resumen`
        );
        setMetrics(m);
      } catch {
        setMetrics(null);
      }
    })();
  }, [proyecto.id]);

  async function verBrechas(art) {
    try {
      const rows = await jget(`${API_BASE}/articulos/${art.id}/brechas`);
      const r = rows?.[0];
      if (!r) {
        alert("Sin brechas");
        return;
      }
      setModal({ open: true, title: art.titulo || "Brecha", payload: r });
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
    <Page title="Brechas detectadas">
      {/* Panel de métricas de proyecto */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
          <div className="border rounded-lg p-3 bg-white shadow-sm">
            <div className="text-gray-500 text-sm">Entropía promedio</div>
            <div className="text-2xl font-semibold">
              {metrics ? Number(metrics.avg_entropia).toFixed(3) : "—"}
            </div>
          </div>
          <div className="border rounded-lg p-3 bg-white shadow-sm">
            <div className="text-gray-500 text-sm">Similitud promedio</div>
            <div className="text-2xl font-semibold">
              {metrics ? Number(metrics.avg_sim_promedio).toFixed(3) : "—"}
            </div>
          </div>
          <div className="border rounded-lg p-3 bg-white shadow-sm">
            <div className="text-gray-500 text-sm">Score validación</div>
            <div className="text-2xl font-semibold">
              {metrics ? Number(metrics.avg_val_score).toFixed(3) : "—"}
            </div>
          </div>
        </div>

        {/* Acciones */}
        <div className="shrink-0 flex flex-col gap-2">
          <Btn
            kind="blue"
            onClick={() =>
              downloadFile(
                `${API_BASE}/proyectos/${proyecto.id}/metrics/plots`,
                `metricas_${proyecto.id}.zip`
              ).catch(() => alert("No se pudo descargar métricas"))
            }
          >
            Descargar métricas (ZIP)
          </Btn>
          <Btn
            kind="yellow"
            onClick={async () => {
              try {
                await downloadFile(
                  `${API_BASE}/export/proyectos/${proyecto.id}/dashboard.pdf`,
                  `dashboard_${proyecto.id}.pdf`
                );
              } catch (e) {
                console.error(e);
                setErr(e);
              }
            }}
          >
            Dashboard (PDF)
          </Btn>
          <Btn kind="gray" onClick={abrirMatriz}>
            Ver matriz
          </Btn>
        </div>
      </div>

      {/* Tabla de artículos */}
      <div className="overflow-x-auto bg-white border rounded-xl shadow-sm">
        <table className="min-w-full">
          <thead className="bg-gray-800 text-white">
            <tr>
              <th className="px-4 py-3 text-left">Nombre del artículo</th>
              <th className="px-4 py-3 w-60 text-left">DOI</th>
              <th className="px-4 py-3 w-40 text-left">Brechas</th>
            </tr>
          </thead>
          <tbody>
            {arts.map((a) => (
              <tr key={a.id} className="border-t">
                <td className="px-4 py-3">{a.titulo || "(sin título)"}</td>
                <td className="px-4 py-3">{a.doi || "—"}</td>
                <td className="px-4 py-3">
                  <Btn kind="gray" onClick={() => verBrechas(a)}>
                    Ver
                  </Btn>
                </td>
              </tr>
            ))}
            {arts.length === 0 && (
              <tr>
                <td className="px-4 py-5 text-gray-500" colSpan={3}>
                  Sin artículos
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-6">
        <Btn kind="gray" onClick={goBack}>
          Volver
        </Btn>
      </div>

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
        {modal.payload && (
          <div className="space-y-3 text-sm">
            <div>
              <div className="text-gray-500">Tipo de brecha</div>
              <div className="font-medium">{modal.payload.tipo_brecha}</div>
            </div>
            <div>
              <div className="text-gray-500">Brecha</div>
              <p className="whitespace-pre-wrap">{modal.payload.brecha}</p>
            </div>
            <div>
              <div className="text-gray-500">Oportunidad de innovación</div>
              <p className="whitespace-pre-wrap">{modal.payload.oportunidad}</p>
            </div>

            <details className="mt-3">
              <summary className="cursor-pointer select-none">
                Mostrar resultados
              </summary>
              <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="border rounded-lg p-3">
                  <div className="text-gray-500">Similitud promedio</div>
                  <div className="font-medium">
                    {modal.payload.sim_promedio ?? 0}
                  </div>
                </div>
                <div className="border rounded-lg p-3">
                  <div className="text-gray-500">Entropía (bits)</div>
                  <div className="font-medium">
                    {modal.payload.entropia ?? 0}
                  </div>
                </div>
                <div className="border rounded-lg p-3">
                  <div className="text-gray-500">Score de validación</div>
                  <div className="font-medium">
                    {modal.payload.val_score ?? 0}
                  </div>
                </div>
                <div className="border rounded-lg p-3">
                  <div className="text-gray-500">Estado de validación</div>
                  <div className="font-medium">
                    {modal.payload.estado_validacion}
                  </div>
                </div>
                {modal.payload.val_reason && (
                  <div className="md:col-span-2 border rounded-lg p-3">
                    <div className="text-gray-500">Razón</div>
                    <div className="font-medium">
                      {modal.payload.val_reason}
                    </div>
                  </div>
                )}
              </div>
            </details>
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
          <div className="text-gray-600">Cargando matriz…</div>
        ) : mx.rows.length === 0 ? (
          <div className="text-gray-600">No hay datos para la matriz.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-100 text-left">
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
                    className="border-t align-top hover:bg-gray-50/60"
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
    <div style={{ fontSize: `${fontSize}px` }}>
      {/* Control de tamaño de letra fijo arriba a la derecha */}
      <div className="fixed top-3 right-4 z-50 flex items-center gap-2 bg-white/80 backdrop-blur px-3 py-1 rounded-full border shadow-sm">
        <span className="text-xs text-gray-600">Tamaño texto</span>
        <button
          onClick={decreaseFont}
          className="text-sm px-2 py-1 border rounded-full hover:bg-gray-100"
        >
          A-
        </button>
        <button
          onClick={increaseFont}
          className="text-sm px-2 py-1 border rounded-full hover:bg-gray-100"
        >
          A+
        </button>
      </div>

      {content}
    </div>
  );
}
