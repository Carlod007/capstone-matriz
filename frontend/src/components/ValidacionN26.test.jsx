import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ValidacionN26 from "./ValidacionN26";
import { respuestaJson } from "../test/respuestas";

const item = {
  id: "item-1", brecha_id: "brecha-1", articulo_id: "articulo-1",
  articulo: "Artículo reservado", tipo_brecha: "metodológica",
  brecha: "No se evaluó la estabilidad.", oportunidad: "Repetir la evaluación.",
  etiqueta_humana: null, justificacion: null,
};

describe("ValidacionN26", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("no recibe ni muestra la predicción durante la revisión", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaJson({
      lote: { id: "lote-1", estado: "abierto", formula_version: 1, protocolo_version: 1 },
      progreso: { anotados: 0, total: 1, pendientes: 1 },
      items: [item], resultado: null,
    })));

    render(<ValidacionN26 proyectoId="proyecto-1" />);

    expect(await screen.findByText(/0/)).toBeInTheDocument();
    expect(screen.getByText(/predicciones de N2.6 permanecen ocultas/i)).toBeInTheDocument();
    expect(screen.queryByText(/N2.6: sí/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/exactitud/i)).not.toBeInTheDocument();
  });

  it("explica la matriz y los intervalos después de cerrar", async () => {
    const usuario = userEvent.setup();
    const abierto = {
      lote: { id: "lote-1", estado: "abierto", formula_version: 1, protocolo_version: 1 },
      progreso: { anotados: 1, total: 1, pendientes: 0 },
      items: [{ ...item, etiqueta_humana: true, justificacion: "Método, página 4." }],
      resultado: null,
    };
    const cerrado = {
      ...abierto,
      lote: { ...abierto.lote, estado: "cerrado" },
      items: [{ ...abierto.items[0], prediccion_ya_resuelta: true }],
      resultado: {
        matriz: { verdadero_positivo: 1, falso_positivo: 0, falso_negativo: 0, verdadero_negativo: 0 },
        indicadores: {
          exactitud: { valor: 1, inferior: 0.2065, superior: 1, n: 1 },
          sensibilidad: { valor: 1, inferior: 0.2065, superior: 1, n: 1 },
          especificidad: null, precision: { valor: 1, inferior: 0.2065, superior: 1, n: 1 },
        },
        advertencia_muestra: "Muestra exploratoria.",
      },
    };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(respuestaJson(abierto))
      .mockResolvedValueOnce(respuestaJson(cerrado)));

    render(<ValidacionN26 proyectoId="proyecto-1" />);
    await usuario.click(await screen.findByRole("button", { name: /cerrar y ver resultados/i }));
    expect(screen.getByText(/respuestas quedarán bloqueadas/i)).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: /sí, cerrar y comparar/i }));

    expect(await screen.findByText("Matriz de confusión")).toBeInTheDocument();
    expect(screen.getByText("alarma incorrecta")).toBeInTheDocument();
    expect(screen.getByText("caso que no detectó")).toBeInTheDocument();
    expect(screen.getAllByText(/Intervalo 95 %/).length).toBeGreaterThan(0);
    expect(screen.getByText("No calculable")).toBeInTheDocument();
  });
});
