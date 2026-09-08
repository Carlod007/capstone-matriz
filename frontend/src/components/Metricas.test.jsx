import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PanelMetricas } from './Metricas'
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
