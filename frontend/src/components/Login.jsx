import { useState } from "react";

import { guardarSesion } from "../sesion";

/**
 * Pantalla de entrada.
 *
 * Sin registro: el alta está cerrada en el servidor y la primera cuenta se
 * crea desde la terminal con `python crear_cuenta.py`. Poner aquí un enlace a
 * un registro que responde 403 sería prometer algo que no existe.
 */
export default function Login({ apiBase, onEntrar }) {
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);

  async function entrar(e) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const r = await fetch(`${apiBase}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ correo: correo.trim().toLowerCase(), contrasena }),
      });

      if (r.status === 401) {
        setError("Correo o contraseña incorrectos.");
        return;
      }
      if (r.status === 422) {
        setError("Ese correo no tiene un formato válido.");
        return;
      }
      if (!r.ok) {
        setError("El servidor respondió con un error. ¿Está encendido?");
        return;
      }

      const datos = await r.json();
      guardarSesion(datos);
      onEntrar(datos);
    } catch {
      // Un fallo de red aquí casi siempre es el backend apagado, y decirlo
      // ahorra buscar la causa en el sitio equivocado.
      setError("No se pudo contactar con el servidor. Comprueba que el backend esté en marcha.");
    } finally {
      setEnviando(false);
    }
  }

  const listo = correo.trim() && contrasena && !enviando;

  return (
    <main className="min-h-screen bg-papel px-4 py-8 sm:px-6 sm:py-12">
      <div
        className="mx-auto grid w-full max-w-5xl overflow-hidden rounded-3xl border border-borde bg-lienzo lg:grid-cols-[1.1fr_0.9fr]"
        style={{ boxShadow: "var(--sombra-2)" }}
      >
        <section className="order-2 border-t border-borde p-6 sm:p-9 lg:order-1 lg:border-r lg:border-t-0 lg:p-12">
          <div className="inline-flex items-center gap-2 rounded-full border border-acento-borde bg-acento-claro px-3 py-1 text-xs font-medium text-acento-fuerte">
            <span className="h-1.5 w-1.5 rounded-full bg-acento" aria-hidden="true" />
            Matriz de brechas de investigación
          </div>

          <h1 className="mt-6 text-2xl font-bold leading-tight tracking-tight text-tinta sm:text-3xl">
            Convierte artículos científicos en hallazgos verificables
          </h1>
          <p className="mt-4 max-w-xl leading-relaxed text-tinta-media">
            Organiza tus artículos, identifica brechas y oportunidades de
            investigación, y comprueba en qué fragmentos se apoya cada resultado.
          </p>

          <ol className="mt-7 space-y-4 text-sm text-tinta-media">
            {[
              ["1", "Define el proyecto", "Indica el tema, el objetivo y la metodología."],
              ["2", "Analiza los artículos", "Sube los PDF y deja que el sistema localice evidencia relevante."],
              ["3", "Revisa los resultados", "Consulta brechas, oportunidades, citas y el estado del arte."],
            ].map(([numero, titulo, descripcion]) => (
              <li key={numero} className="flex items-start gap-3">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-acento-borde bg-acento-claro text-xs font-semibold text-acento-fuerte">
                  {numero}
                </span>
                <div>
                  <div className="font-medium text-tinta">{titulo}</div>
                  <div className="mt-0.5 leading-relaxed">{descripcion}</div>
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-8 border-l-2 border-acento pl-3 text-xs leading-relaxed text-tinta-suave">
            Herramienta de apoyo: los resultados deben revisarse con criterio
            académico y contrastarse con los artículos originales.
          </p>
        </section>

        <section className="order-1 flex items-center bg-superficie p-6 sm:p-9 lg:order-2 lg:p-12" aria-labelledby="titulo-acceso">
          <div className="w-full">
            <div>
              <div className="text-xs font-medium uppercase tracking-wider text-tinta-suave">
                Acceso
              </div>
              <h2 id="titulo-acceso" className="mt-2 text-xl font-semibold text-tinta">
                Entra a tus proyectos
              </h2>
              <p className="mt-1.5 text-sm leading-relaxed text-tinta-media">
                Usa la cuenta habilitada para esta instalación.
              </p>
            </div>

            <form onSubmit={entrar} className="mt-7 flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-tinta-media">Correo</span>
                <input
                type="email"
                autoComplete="username"
                  autoFocus
                  value={correo}
                  onChange={(e) => setCorreo(e.target.value)}
                  placeholder="correo@universidad.edu"
                  className="rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta outline-none transition-colors placeholder:text-tinta-suave focus:border-acento focus:ring-2 focus:ring-acento/20"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-tinta-media">Contraseña</span>
                <input
                  type="password"
                  autoComplete="current-password"
                  value={contrasena}
                  onChange={(e) => setContrasena(e.target.value)}
                  placeholder="Tu contraseña"
                  className="rounded-lg border border-borde bg-lienzo px-3 py-2.5 text-sm text-tinta outline-none transition-colors placeholder:text-tinta-suave focus:border-acento focus:ring-2 focus:ring-acento/20"
                />
              </label>

              {error && (
                <p role="alert" className="rounded-lg border border-mal-borde bg-mal-claro px-3 py-2 text-sm text-mal">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={!listo}
                className="mt-1 rounded-lg bg-oro px-4 py-2.5 text-sm font-medium text-oro-tinta shadow-[var(--sombra-1)] transition-[background-color,transform] hover:bg-oro-hover active:scale-[0.985] disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-oro"
              >
                {enviando ? "Entrando…" : "Entrar a mis proyectos"}
              </button>
            </form>

            <p className="mt-5 text-xs leading-relaxed text-tinta-suave">
              El acceso está restringido. Si necesitas una cuenta, solicítala al
              responsable de la aplicación.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
