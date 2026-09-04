import { useCallback, useEffect, useState } from "react";

import { api } from "../sesion";
import { abrirPdfArticulo } from "../utils/abrirPdf";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

function Boton({ children, principal = false, ...props }) {
  return (
    <button
      type="button"
      className={`rounded-lg border px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
        principal
          ? "border-acento bg-acento text-papel hover:bg-acento-fuerte"
          : "border-borde bg-superficie text-tinta hover:bg-hundido"
      }`}
      {...props}
    >
      {children}
    </button>
  );
}

function Item({ item, proyectoId, onGuardado, onError }) {
  const [respuesta, setRespuesta] = useState(item.etiqueta_humana);
  const [justificacion, setJustificacion] = useState(item.justificacion || "");
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState(null);
  const [pdf, setPdf] = useState(null);

  async function guardar() {
    setGuardando(true);
    setAviso(null);
    try {
      const r = await api(
        `${API_BASE}/proyectos/${proyectoId}/validacion-n26/${item.brecha_id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ya_resuelta: respuesta,
            justificacion: justificacion.trim(),
          }),
        },
      );
      const cuerpo = await r.json().catch(() => null);
      if (!r.ok) {
        setAviso(cuerpo?.detail || `No se pudo guardar (error ${r.status})`);
        return;
      }
      setAviso("Guardado");
      onGuardado(cuerpo);
    } catch (e) {
      onError?.(e);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <article className="rounded-xl border border-borde bg-superficie p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-tinta">{item.articulo}</h3>
        <span className="text-[11px] uppercase tracking-wide text-tinta-suave">
          {item.tipo_brecha}
        </span>
      </div>
      <button
        type="button"
        onClick={() => abrirPdfArticulo(item.articulo_id, setPdf)}
        className="mt-2 rounded-lg border border-acento-borde bg-acento-claro px-2.5 py-1 text-xs font-medium text-acento-fuerte hover:border-acento"
      >
        {pdf === "abriendo" ? "Abriendo…" : "Leer el artículo (PDF)"}
      </button>
      {pdf && pdf !== "abriendo" && (
        <span className="ml-2 text-[11px] text-mal">{pdf}</span>
      )}

      <p className="mt-3 text-sm leading-relaxed text-tinta-media">{item.brecha}</p>
      {item.oportunidad && (
        <p className="mt-1.5 text-xs leading-relaxed text-tinta-suave">
          <span className="font-medium">Oportunidad:</span> {item.oportunidad}
        </p>
      )}

      <fieldset className="mt-4">
        <legend className="text-sm font-medium text-tinta">
          ¿La brecha presenta como pendiente algo que el artículo ya realizó?
        </legend>
        <p className="mt-1 text-xs leading-relaxed text-tinta-suave">
          Responde según el artículo, no según si la brecha parece útil o está bien redactada.
        </p>
        <div className="mt-2 flex gap-2">
          {[[true, "Sí, ya lo realizó"], [false, "No, sigue pendiente"]].map(
            ([valor, texto]) => (
              <button
                key={texto}
                type="button"
                aria-pressed={respuesta === valor}
                onClick={() => setRespuesta(valor)}
                className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                  respuesta === valor
                    ? "border-acento bg-acento-claro text-acento-fuerte"
                    : "border-borde bg-hundido text-tinta-media hover:text-tinta"
                }`}
              >
                {texto}
              </button>
            ),
          )}
        </div>
      </fieldset>

      {respuesta !== null && respuesta !== undefined && (
        <div className="mt-3">
          <label className="block text-xs text-tinta-suave">
            ¿En qué parte del artículo basas tu respuesta? (obligatorio)
          </label>
          <textarea
            rows={2}
            value={justificacion}
            onChange={(e) => setJustificacion(e.target.value)}
            placeholder="Por ejemplo: metodología, página 6; el artículo sí describe…"
            className="mt-1 w-full rounded-lg border border-borde bg-superficie px-3 py-2 text-sm text-tinta outline-none placeholder:text-tinta-suave focus:border-acento"
          />
          <div className="mt-2 flex items-center gap-3">
            <Boton
              principal
              disabled={guardando || !justificacion.trim()}
              onClick={guardar}
            >
              {guardando ? "Guardando…" : "Guardar respuesta"}
            </Boton>
            {aviso && (
              <span className={`text-xs ${aviso === "Guardado" ? "text-bien" : "text-mal"}`}>
                {aviso}
              </span>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function Porcentaje({ titulo, dato, ayuda }) {
  return (
    <div className="rounded-lg border border-borde bg-hundido p-3">
      <div className="text-xs text-tinta-suave">{titulo}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums text-tinta">
        {dato ? `${Math.round(dato.valor * 100)} %` : "No calculable"}
      </div>
      <div className="mt-1 text-[11px] leading-relaxed text-tinta-suave">
        {dato
          ? `Intervalo 95 %: ${Math.round(dato.inferior * 100)}–${Math.round(dato.superior * 100)} % (n=${dato.n}).`
          : "No hubo casos suficientes en esta categoría."}
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-tinta-media">{ayuda}</p>
    </div>
  );
}

function Resultado({ datos }) {
  const matriz = datos.resultado.matriz;
  const indicadores = datos.resultado.indicadores;
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-bien-borde bg-bien-claro p-4">
        <h2 className="text-sm font-semibold text-bien">Validación cerrada</h2>
        <p className="mt-1 text-xs leading-relaxed text-tinta-media">
          Las predicciones se revelan ahora porque todas las respuestas humanas quedaron guardadas y bloqueadas.
        </p>
      </div>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-tinta">
          Matriz de confusión
        </h2>
        <p className="mt-1 text-xs text-tinta-suave">
          “Positivo” significa que el artículo ya había realizado lo que la brecha presenta como pendiente.
        </p>
        <div className="mt-3 overflow-x-auto rounded-xl border border-borde bg-superficie p-4">
          <table className="w-full min-w-[32rem] text-center text-sm">
            <thead className="text-xs text-tinta-suave">
              <tr><th className="p-2 text-left">N2.6 frente al juicio humano</th><th className="p-2">Humano: sí</th><th className="p-2">Humano: no</th></tr>
            </thead>
            <tbody>
              <tr className="border-t border-borde"><th className="p-3 text-left font-medium">N2.6: sí</th><td className="p-3"><strong>{matriz.verdadero_positivo}</strong><span className="block text-[11px] text-tinta-suave">acierto positivo</span></td><td className="p-3"><strong>{matriz.falso_positivo}</strong><span className="block text-[11px] text-tinta-suave">alarma incorrecta</span></td></tr>
              <tr className="border-t border-borde"><th className="p-3 text-left font-medium">N2.6: no</th><td className="p-3"><strong>{matriz.falso_negativo}</strong><span className="block text-[11px] text-tinta-suave">caso que no detectó</span></td><td className="p-3"><strong>{matriz.verdadero_negativo}</strong><span className="block text-[11px] text-tinta-suave">descarte correcto</span></td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Porcentaje titulo="Exactitud" dato={indicadores.exactitud} ayuda="Cuántas decisiones totales coincidieron." />
        <Porcentaje titulo="Sensibilidad" dato={indicadores.sensibilidad} ayuda="Cuántos casos ya resueltos logró detectar." />
        <Porcentaje titulo="Especificidad" dato={indicadores.especificidad} ayuda="Cuántos casos realmente pendientes descartó bien." />
        <Porcentaje titulo="Precisión" dato={indicadores.precision} ayuda="Cuántas alertas de N2.6 fueron correctas." />
      </div>

      {datos.resultado.advertencia_muestra && (
        <p className="rounded-lg border border-aviso-borde bg-aviso-claro px-3 py-2 text-xs leading-relaxed text-aviso">
          {datos.resultado.advertencia_muestra}
        </p>
      )}

      <div className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-tinta">Casos revisados</h2>
        {datos.items.map((item) => (
          <div key={item.id} className="rounded-lg border border-borde bg-superficie p-3 text-sm">
            <div className="font-medium text-tinta">{item.articulo}</div>
            <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-tinta-media">
              <span>Tu respuesta: <strong>{item.etiqueta_humana ? "sí" : "no"}</strong></span>
              <span>N2.6: <strong>{item.prediccion_ya_resuelta ? "sí" : "no"}</strong></span>
            </div>
            <p className="mt-1 text-xs text-tinta-suave">{item.justificacion}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ValidacionN26({ proyectoId, onError }) {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [accion, setAccion] = useState(false);
  const [mensaje, setMensaje] = useState(null);
  const [confirmando, setConfirmando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const r = await api(`${API_BASE}/proyectos/${proyectoId}/validacion-n26`);
      const cuerpo = await r.json().catch(() => null);
      setDatos(r.ok ? cuerpo : null);
      if (!r.ok) setMensaje(cuerpo?.detail || "No se pudo cargar la validación.");
    } catch (e) {
      onError?.(e);
    } finally {
      setCargando(false);
    }
  }, [proyectoId, onError]);

  useEffect(() => { cargar(); }, [cargar]);

  async function enviar(ruta) {
    setAccion(true);
    setMensaje(null);
    try {
      const r = await api(`${API_BASE}/proyectos/${proyectoId}/validacion-n26/${ruta}`, { method: "POST" });
      const cuerpo = await r.json().catch(() => null);
      if (!r.ok) {
        setMensaje(cuerpo?.detail || `No se pudo continuar (error ${r.status})`);
        return;
      }
      setDatos(cuerpo);
      setConfirmando(false);
    } catch (e) {
      onError?.(e);
    } finally {
      setAccion(false);
    }
  }

  if (cargando) return <p className="text-sm text-tinta-suave">Cargando validación…</p>;

  if (!datos?.lote) {
    return (
      <div className="max-w-3xl space-y-4">
        <div className="rounded-xl border border-borde bg-superficie p-5">
          <h2 className="text-base font-semibold text-tinta">Antes de comenzar</h2>
          <p className="mt-2 text-sm leading-relaxed text-tinta-media">
            Usa un proyecto nuevo, cuyos artículos no se hayan utilizado para diseñar ni ajustar N2.6. Al comenzar se congelan las predicciones actuales y no podrás verlas hasta terminar.
          </p>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-relaxed text-tinta-suave">
            <li>Lee cada artículo y responde una sola pregunta concreta.</li>
            <li>Justifica dónde encontraste la evidencia.</li>
            <li>Cierra el lote para revelar la comparación y sus intervalos de incertidumbre.</li>
          </ol>
          <p className="mt-3 text-xs text-tinta-suave">
            Esta ejecución contiene {datos?.total ?? 0} brechas. La primera prueba prevista usa 5; para evidencia más sólida se necesitan 20–30 de varios dominios.
          </p>
          <div className="mt-4">
            <Boton principal disabled={!datos?.puede_iniciar || accion} onClick={() => enviar("iniciar")}>
              {accion ? "Preparando…" : "Comenzar revisión ciega"}
            </Boton>
          </div>
        </div>
        {(mensaje || datos?.motivo) && <p className="text-sm text-mal">{mensaje || datos.motivo}</p>}
      </div>
    );
  }

  if (datos.lote.estado === "cerrado") return <Resultado datos={datos} />;

  const completo = datos.progreso.pendientes === 0 && datos.progreso.total > 0;
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-borde bg-superficie p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="text-2xl font-semibold tabular-nums text-tinta">
              {datos.progreso.anotados}<span className="text-base font-normal text-tinta-suave"> / {datos.progreso.total}</span>
            </div>
            <div className="text-xs text-tinta-suave">respuestas guardadas</div>
          </div>
          {completo && !confirmando && <Boton principal onClick={() => setConfirmando(true)}>Cerrar y ver resultados</Boton>}
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-hundido">
          <div className="h-full bg-acento transition-[width]" style={{ width: `${datos.progreso.total ? (datos.progreso.anotados / datos.progreso.total) * 100 : 0}%` }} />
        </div>
        <p className="mt-3 text-xs leading-relaxed text-tinta-suave">
          Las predicciones de N2.6 permanecen ocultas. Formula v{datos.lote.formula_version}; protocolo v{datos.lote.protocolo_version}.
        </p>
      </div>

      {confirmando && (
        <div className="rounded-xl border border-aviso-borde bg-aviso-claro p-4">
          <p className="text-sm font-medium text-aviso">¿Cerrar la validación?</p>
          <p className="mt-1 text-xs leading-relaxed text-tinta-media">
            Se revelarán las predicciones y las respuestas quedarán bloqueadas. Esto evita corregirlas después de conocer el resultado.
          </p>
          <div className="mt-3 flex gap-2">
            <Boton principal disabled={accion} onClick={() => enviar("cerrar")}>{accion ? "Cerrando…" : "Sí, cerrar y comparar"}</Boton>
            <Boton disabled={accion} onClick={() => setConfirmando(false)}>Seguir revisando</Boton>
          </div>
        </div>
      )}

      {mensaje && <p className="text-sm text-mal">{mensaje}</p>}
      <div className="space-y-3">
        {datos.items.map((item) => <Item key={item.id} item={item} proyectoId={proyectoId} onGuardado={setDatos} onError={onError} />)}
      </div>
    </div>
  );
}
