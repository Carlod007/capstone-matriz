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
      name: 'Respaldo de afirmaciones evidenciales',
    })
    expect(within(titulo.closest('article')).getAllByText('0.000').length).toBeGreaterThan(0)

    await usuario.click(screen.getByRole('button', { name: /Ver las 2 métricas técnicas/i }))
    await usuario.click(screen.getByRole('button', { name: /N4 Resumen/ }))
    await usuario.click(screen.getByRole('button', { name: /ROUGE-1 precisión/i }))

    expect(await screen.findByText('Sin mediciones aplicables')).toBeInTheDocument()
    expect(screen.getByText('El resumen y el abstract están en idiomas distintos.')).toBeInTheDocument()
    expect(screen.getByText(/La ausencia de datos no equivale a un cero/i)).toBeInTheDocument()
  })

  it('presenta el IQR como descripción y no como veredicto', async () => {
    render(<PanelMetricas proyectoId="proyecto-1" />)

    await screen.findByText('IQR descriptivo, sin calificación', { exact: false })
    expect(screen.getByText('Sin umbral común:')).toBeInTheDocument()
    expect(screen.queryByText('Separa los casos')).not.toBeInTheDocument()
    expect(screen.queryByText('Valores parecidos entre sí')).not.toBeInTheDocument()

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  })
})
