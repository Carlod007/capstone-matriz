import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Validacion from './Validacion'
import { respuestaJson } from '../test/respuestas'


const brecha = {
  id: 'brecha-1',
  articulo_id: 'articulo-1',
  articulo: 'Artículo de prueba',
  tipo_brecha: 'metodológica',
  brecha: 'No se evaluó la estabilidad entre ejecuciones.',
  oportunidad: 'Repetir el experimento con distintas semillas.',
  veredicto: null,
  justificacion: null,
  origen: null,
  otros_anotadores: 0,
}

describe('Validacion', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('mantiene ocultos el resultado y las métricas mientras falta una revisión', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaJson({
      brechas: [brecha],
      resumen: {
        total: 2,
        anotadas: 1,
        pendientes: 1,
        revision_completa: false,
        acierto: null,
        por_veredicto: null,
        anotadores: 1,
      },
    })))

    render(<Validacion proyectoId="proyecto-1" />)

    expect(await screen.findByText(/Faltan 1\./)).toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /juicio frente a las métricas/i })).not.toBeInTheDocument()
    expect(screen.queryByText('N2.1')).not.toBeInTheDocument()
  })

  it('revela la comparación solo cuando la revisión está completa', async () => {
    const usuario = userEvent.setup()
    const pedir = vi.fn(async (url) => {
      if (url.endsWith('/validacion/comparacion')) {
        return respuestaJson({
          brechas: [{
            id: 'brecha-1',
            articulo: 'Artículo de prueba',
            veredicto: 'parcial',
            metricas: { 'N2.1': 0.75, 'N2.5': 0, 'N2.6': 0 },
          }],
        })
      }
      return respuestaJson({
        brechas: [{ ...brecha, veredicto: 'parcial', justificacion: 'Falta un matiz.' }],
        resumen: {
          total: 1,
          anotadas: 1,
          pendientes: 0,
          revision_completa: true,
          acierto: 0.5,
          por_veredicto: { parcial: 1 },
          anotadores: 1,
        },
      })
    })
    vi.stubGlobal('fetch', pedir)

    render(<Validacion proyectoId="proyecto-1" />)

    expect(await screen.findByText('50 %')).toBeInTheDocument()
    expect(screen.queryByText('N2.1')).not.toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: /Ver tu juicio frente a las métricas/i }))

    expect(await screen.findByText('N2.1')).toBeInTheDocument()
    expect(screen.getByText('0.750')).toBeInTheDocument()
    expect(pedir).toHaveBeenCalledTimes(2)
  })
})
