import { beforeEach, describe, expect, it, vi } from 'vitest'

import { alExpirar, api, guardarSesion, leerSesion } from './sesion'


describe('api de sesión', () => {
  beforeEach(() => {
    alExpirar(null)
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('envía el token al pedir un recurso protegido', async () => {
    guardarSesion({ token: 'token-de-prueba', nombre: 'Investigadora' })
    const pedir = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
    vi.stubGlobal('fetch', pedir)

    await api('/api/articulos/a-1/pdf')

    expect(pedir).toHaveBeenCalledWith('/api/articulos/a-1/pdf', {
      headers: { Authorization: 'Bearer token-de-prueba' },
    })
  })

  it('cierra la sesión y avisa cuando el servidor responde 401', async () => {
    guardarSesion({ token: 'token-caducado' })
    const expiro = vi.fn()
    alExpirar(expiro)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))

    await expect(api('/api/proyectos')).rejects.toMatchObject({ sesionCaducada: true })
    expect(leerSesion()).toBeNull()
    expect(expiro).toHaveBeenCalledOnce()
  })
})
