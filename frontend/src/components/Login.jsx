import { useState } from "react";

import { Panel } from "./UI";
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
    <div className="min-h-screen flex items-center justify-center px-5 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-7 text-center">
          <h1 className="text-xl font-semibold text-tinta">
            Matriz de brechas de investigación
          </h1>
          <p className="mt-1.5 text-sm text-tinta-media">
            Entra para ver tus proyectos.
          </p>
        </div>

        <Panel>
          <form onSubmit={entrar} className="flex flex-col gap-4 p-5">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-tinta-media">Correo</span>
              <input
                type="email"
                autoComplete="username"
                autoFocus
                value={correo}
                onChange={(e) => setCorreo(e.target.value)}
                className="rounded-lg border border-borde bg-superficie px-3 py-2 text-sm text-tinta outline-none focus:border-acento"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-tinta-media">Contraseña</span>
              <input
                type="password"
                autoComplete="current-password"
                value={contrasena}
                onChange={(e) => setContrasena(e.target.value)}
                className="rounded-lg border border-borde bg-superficie px-3 py-2 text-sm text-tinta outline-none focus:border-acento"
              />
            </label>

            {error && (
              <p role="alert" className="rounded-lg border border-mal-borde bg-mal-claro px-3 py-2 text-sm text-mal">
                {error}
              </p>
            )}

            {/* Dorado: es la acción principal de esta pantalla, la misma
                convención que sigue el resto de la aplicación. */}
            <button
              type="submit"
              disabled={!listo}
              className="rounded-lg bg-oro px-4 py-2.5 text-sm font-medium text-oro-tinta shadow-[var(--sombra-1)] transition-[background-color,transform] hover:bg-oro-hover active:scale-[0.985] disabled:opacity-45 disabled:cursor-not-allowed disabled:hover:bg-oro"
            >
              {enviando ? "Entrando…" : "Entrar"}
            </button>
          </form>
        </Panel>

        <p className="mt-4 text-center text-xs leading-relaxed text-tinta-suave">
          ¿Aún no tienes cuenta? Se crea desde la terminal, en <code>backend/</code>,
          con <code>python crear_cuenta.py</code>.
        </p>
      </div>
    </div>
  );
}
