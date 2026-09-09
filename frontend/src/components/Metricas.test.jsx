import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DetalleBrecha, PanelMetricas } from './Metricas'
import { respuestaJson } from '../test/respuestas'


const baseMetrica = {
  nivel: 'N2 Fidelidad',
  ambito: 'brecha',
  minimo: 0,
  p25: 0,
  mediana: 0,
  p75: 0.5,
  maximo: 0.5,
  media: 0.25,
  iqr: 0.5,
  n: 2,
  n_intentos: 2,
  mejor: 'alto',
  rango: '0 a 1',
  descripcion: 'Proporción de afirmaciones respaldadas por el artículo.',
  interpretacion: 'Permite comprobar el respaldo documental de cada afirmación.',
  version_formula: 2,
}

const datos = {
  run: {
    id: 'run-1',
    estado: 'completado',
    tokens_in: 120,
    tokens_out: 30,
  },
  conteos: { articulos: 2, brechas: 2, por_estado_validacion: {} },
  estado_arte: null,
  validacion_calibrada: false,
  metricas: [
    {
      ...baseMetrica,
      codigo: 'N2.1',
      nombre: 'Respaldo de afirmaciones evidenciales',
    },
    {
      ...baseMetrica,
      codigo: 'N4.1a',
      nombre: 'ROUGE-1 precisión',
      nivel: 'N4 Resumen',
      n: 0,
      n_intentos: 2,
      minimo: 0,
      p25: 0,
      mediana: 0,
      p75: 0,
      maximo: 0,
      media: 0,
      iqr: 0,
      motivo_sin_datos: 'El resumen y el abstract están en idiomas distintos.',
    },
  ],
}

describe('PanelMetricas', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaJson(datos)))
  })

  it('distingue un cero medido de una métrica no aplicable', async () => {
    const usuario = userEvent.setup()
    render(<PanelMetricas proyectoId="proyecto-1" />)

    const titulo = await screen.findByRole('heading', {
      name: 'Respaldo de las afirmaciones',
    })
    expect(within(titulo.closest('article')).getByText('0.000 de 1')).toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: /Ver las 2 métricas técnicas/i }))
    await usuario.click(screen.getByRole('button', { name: /N4 Resumen/ }))
    await usuario.click(screen.getByRole('button', { name: /ROUGE-1 precisión/i }))

    expect(await screen.findByText('Sin mediciones aplicables')).toBeInTheDocument()
    expect(screen.getByText('El resumen y el abstract están en idiomas distintos.')).toBeInTheDocument()
    expect(screen.getByText(/La ausencia de datos no equivale a un cero/i)).toBeInTheDocument()
  })

  it('presenta el IQR como descripción y no como veredicto', async () => {
    const usuario = userEvent.setup()
    render(<PanelMetricas proyectoId="proyecto-1" />)

    await screen.findByText('IQR descriptivo, sin calificación', { exact: false })
    expect(screen.queryByText('Sin umbral común:')).not.toBeInTheDocument()
    expect(screen.getByText(/No muestran aprobado o desaprobado/i)).toBeInTheDocument()
    expect(screen.queryByText('Separa los casos')).not.toBeInTheDocument()
    expect(screen.queryByText('Valores parecidos entre sí')).not.toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: /Ver las 2 métricas técnicas/i }))
    expect(screen.getByText('Sin umbral común:')).toBeInTheDocument()

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  })

  it('coloca el contenido principal antes de las mediciones', async () => {
    render(
      <PanelMetricas
        proyectoId="proyecto-1"
        contenidoPrincipal={<h2>Artículos y brechas</h2>}
      />,
    )

    const articulos = await screen.findByRole('heading', { name: 'Artículos y brechas' })
    const mediciones = screen.getByRole('heading', {
      name: 'Qué dicen las mediciones principales',
    })

    expect(
      articulos.compareDocumentPosition(mediciones) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('no explica una cobertura histórica como si usara la fórmula actual', async () => {
    fetch.mockResolvedValueOnce(respuestaJson({
      ...datos,
      metricas: [
        ...datos.metricas,
        {
          ...baseMetrica,
          codigo: 'N1.2',
          nombre: 'Cobertura seccional',
          nivel: 'N1 Recuperación',
          mediana: 0.5,
          media: 0.5,
          version_formula: 1,
        },
      ],
    }))

    render(<PanelMetricas proyectoId="proyecto-historico" />)

    expect(await screen.findByText(/usa la fórmula histórica/i)).toBeInTheDocument()
    expect(screen.queryByText(/llegó al modelo el 50 %/i)).not.toBeInTheDocument()
  })
})

describe('DetalleBrecha', () => {
  const brecha = {
    id: 'brecha-1',
    tipo_brecha: 'metodológica',
    brecha: 'El estudio usa cargas estáticas y no representa efectos dinámicos.',
    oportunidad: 'Validar el modelo con simulaciones dinámicas explícitas.',
    validacion_calibrada: false,
    secciones_consultadas: ['método', 'resultados'],
    respaldo: [
      { seccion: 'método', score: 0.65 },
      { seccion: 'resultados', score: 0.61 },
    ],
    verificacion: {
      disponible: true,
      n_evidenciales_autonomas: 2,
      n_sin_respaldo: 0,
      n_contradicciones: 0,
      ya_resuelta: false,
      fidelidad: 1,
      trazabilidad: 1,
      equilibrio_evidencial: 0.67,
      detalle_trazabilidad: {
        formula: 2,
        n_elegibles: 2,
        n_con_fragmento_y_cita: 2,
      },
      afirmaciones: [
        {
          tipo: 'evidencial',
          autonoma: true,
          respaldada: true,
          texto: 'El estudio usa cargas estáticas.',
          fragmento: 1,
          cita: 'The study uses equivalent static forces.',
        },
        {
          tipo: 'evidencial',
          autonoma: true,
          respaldada: true,
          texto: 'No se modelan efectos dinámicos.',
          fragmento: 2,
          cita: 'Dynamic effects are not represented.',
        },
      ],
    },
    metricas: [
      {
        codigo: 'N1.2',
        nombre: 'Cobertura seccional',
        nivel: 'N1 Recuperación',
        valor: 1,
        mejor: 'alto',
        rango: '0 a 1',
        descripcion: 'Secciones útiles consultadas.',
        interpretacion: 'Más cobertura incorpora más secciones disponibles.',
      },
      {
        codigo: 'N2.1',
        nombre: 'Respaldo de afirmaciones evidenciales',
        nivel: 'N2 Fidelidad',
        valor: 1,
        mejor: 'alto',
        rango: '0 a 1',
        descripcion: 'Afirmaciones respaldadas.',
        interpretacion: 'No evalúa la novedad de la brecha.',
      },
      {
        codigo: 'N4.1a',
        nombre: 'ROUGE-1 precisión',
        nivel: 'N4 Resumen',
        valor: null,
        mejor: 'alto',
        rango: '0 a 1',
        descripcion: 'Solape de palabras.',
        detalle: {
          aplicable: false,
          motivo: 'El resumen y el abstract están en idiomas distintos.',
        },
      },
    ],
  }

  it('prioriza una lectura sencilla y deja la auditoría plegada', () => {
    render(<DetalleBrecha brecha={brecha} />)

    expect(screen.getByText('Brecha identificada')).toBeInTheDocument()
    expect(screen.getByText('2 de 2 afirmaciones respaldadas')).toBeInTheDocument()
    expect(screen.getByText('Sin contradicciones detectadas')).toBeInTheDocument()
    expect(screen.getByText('No parece una brecha ya resuelta')).toBeInTheDocument()
    expect(screen.getByText('Requiere revisión humana')).toBeInTheDocument()

    expect(screen.getByText('Comprobar qué frases se apoyan en el artículo').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Qué partes del artículo leyó el sistema').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Cómo se evaluó esta brecha').closest('details')).not.toHaveAttribute('open')
  })

  it('conserva las métricas técnicas y explica las no aplicables', async () => {
    const usuario = userEvent.setup()
    render(<DetalleBrecha brecha={brecha} />)

    await usuario.click(screen.getByText('Cómo se evaluó esta brecha'))

    expect(screen.getByText('Contexto consultado · 1')).toBeInTheDocument()
    expect(screen.getByText('Fidelidad · 1')).toBeInTheDocument()
    expect(screen.getByText('Resumen · 1')).toBeInTheDocument()
    expect(screen.getByText('ROUGE-1 precisión')).toBeInTheDocument()
    expect(screen.getByText('no aplicable')).toBeInTheDocument()
    expect(screen.getByText('El resumen y el abstract están en idiomas distintos.')).toBeInTheDocument()
  })

  it('resume las secciones consultadas antes de mostrar relevancias técnicas', async () => {
    const usuario = userEvent.setup()
    render(<DetalleBrecha brecha={brecha} />)

    await usuario.click(screen.getByText('Qué partes del artículo leyó el sistema'))

    expect(screen.getByText('método · 1')).toBeInTheDocument()
    expect(screen.getByText('resultados · 1')).toBeInTheDocument()
    expect(screen.getByText('Ver selección técnica de los 2 fragmentos').closest('details'))
      .not.toHaveAttribute('open')
  })

  it('traduce una saturación temporal sin mostrar el error técnico del proveedor', () => {
    render(
      <DetalleBrecha
        brecha={{
          ...brecha,
          verificacion: {
            disponible: false,
            motivo: "No se pudo verificar: 503 UNAVAILABLE. {'error': {'message': 'This model is currently experiencing high demand.'}}",
          },
        }}
      />,
    )

    expect(screen.getByText(/servicio de análisis estaba temporalmente saturado/i))
      .toBeInTheDocument()
    expect(screen.getByText(/La brecha sigue guardada/i)).toBeInTheDocument()
    expect(screen.queryByText('Comprobar qué frases se apoyan en el artículo')).not.toBeInTheDocument()
    expect(screen.queryByText(/503 UNAVAILABLE/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/high demand/i)).not.toBeInTheDocument()
  })
})
