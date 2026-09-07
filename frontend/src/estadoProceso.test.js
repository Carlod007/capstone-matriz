import { describe, expect, it } from "vitest";

import {
  destinoProyecto,
  presentarAvance,
  presentarBorradoProyecto,
  presentarProyecto,
} from "./estadoProceso";


describe("estado visible del proyecto", () => {
  it("abre resultados cuando las brechas existen aunque la síntesis siga", () => {
    const p = { estado_proceso: "generando_estado_arte", n_brechas: 5 };

    expect(destinoProyecto(p)).toBe("brechas");
    expect(presentarProyecto(p)).toMatchObject({
      valor: "Sintetizando",
      apoyo: "Las brechas ya están disponibles",
      puedeVerSintesis: false,
    });
  });

  it("abre el avance mientras se analizan artículos", () => {
    expect(destinoProyecto({ estado_proceso: "analizando", n_brechas: 5 }))
      .toBe("articulos");
  });

  it("no presenta una síntesis histórica como si fuera la actual", () => {
    const vista = presentarProyecto({
      estado_proceso: "estado_arte_fallido",
      tiene_estado_arte: true,
    });

    expect(vista.puedeVerSintesis).toBe(false);
    expect(vista.mensaje).toContain("las brechas se conservan");
  });
});

describe("gravedad del borrado", () => {
  it("distingue un proyecto vacío", () => {
    expect(presentarBorradoProyecto({ n_articulos: 0, n_brechas: 0 }))
      .toMatchObject({ nivel: "bajo", titulo: "Este proyecto está vacío" });
  });

  it("avisa por los PDF aunque todavía no haya resultados", () => {
    expect(presentarBorradoProyecto({ n_articulos: 2, n_brechas: 0 }))
      .toMatchObject({ nivel: "medio", titulo: "Este proyecto contiene documentos" });
  });

  it("usa la advertencia máxima cuando existen resultados", () => {
    const vista = presentarBorradoProyecto({
      n_articulos: 5,
      n_brechas: 5,
      tiene_estado_arte: true,
    });

    expect(vista.nivel).toBe("alto");
    expect(vista.detalle).toContain("brechas");
    expect(vista.aviso).toContain("cuota de API");
  });
});

describe("seguimiento del análisis", () => {
  it("explica una espera larga sin pedir comandos técnicos", () => {
    const vista = presentarAvance(
      { fase: "analizando", n_items_ok: 2, n_items_total: 5 },
      5,
      true,
    );

    expect(vista.detalle).toContain("continúa en segundo plano");
    expect(vista.detalle).not.toContain("python");
  });

  it("mantiene el seguimiento durante la síntesis", () => {
    const vista = presentarAvance(
      { estado: "completado", fase: "generando_estado_arte", n_items_ok: 5 },
      5,
    );

    expect(vista).toMatchObject({
      etapa: "Generando estado del arte",
      hecho: 5,
      total: 5,
      termino: false,
    });
  });

  it("distingue el fallo de síntesis del fallo del análisis", () => {
    expect(presentarAvance({ fase: "estado_arte_fallido" }, 5))
      .toMatchObject({ termino: true, exito: false, soloSintesis: true });
    expect(presentarAvance({ fase: "fallido" }, 5))
      .toMatchObject({ termino: true, exito: false, soloSintesis: false });
  });
});
