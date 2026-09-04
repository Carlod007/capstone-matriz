import { api } from "../sesion";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/** Abre el PDF protegido usando la sesion actual y libera despues la copia. */
export async function abrirPdfArticulo(articuloId, setEstado) {
  setEstado("abriendo");
  try {
    const r = await api(`${API_BASE}/articulos/${articuloId}/pdf`);
    if (!r.ok) {
      const cuerpo = await r.json().catch(() => null);
      setEstado(cuerpo?.detail || `No se pudo abrir (error ${r.status})`);
      return;
    }
    const url = URL.createObjectURL(await r.blob());
    const ventana = window.open(url, "_blank", "noopener");
    if (!ventana) {
      setEstado("El navegador bloqueó la ventana. Permite las emergentes.");
    } else {
      setEstado(null);
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch {
    setEstado("No se pudo abrir el artículo.");
  }
}
