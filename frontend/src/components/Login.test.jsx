import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import Login from './Login'
import { respuestaJson } from '../test/respuestas'


it('reúne la explicación y el acceso en una sola pantalla', () => {
  render(<Login apiBase="/api" onEntrar={() => {}} />)

  expect(screen.getByRole('heading', {
    name: 'Convierte artículos científicos en hallazgos verificables',
  })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Entra a tus proyectos' })).toBeInTheDocument()
  expect(screen.getByLabelText('Correo')).toBeInTheDocument()
  expect(screen.getByLabelText('Contraseña')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Comenzar' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Ir a proyectos' })).not.toBeInTheDocument()
})

it('mantiene el mismo inicio de sesión', async () => {
  const usuario = userEvent.setup()
  const onEntrar = vi.fn()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaJson({
    token: 'token-prueba',
    nombre: 'Investigadora',
  })))

  render(<Login apiBase="/api" onEntrar={onEntrar} />)

  await usuario.type(screen.getByLabelText('Correo'), 'PERSONA@UNIVERSIDAD.EDU ')
  await usuario.type(screen.getByLabelText('Contraseña'), 'secreto')
  await usuario.click(screen.getByRole('button', { name: 'Entrar a mis proyectos' }))

  expect(fetch).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({
      correo: 'persona@universidad.edu',
      contrasena: 'secreto',
    }),
  }))
  expect(onEntrar).toHaveBeenCalledWith({
    token: 'token-prueba',
    nombre: 'Investigadora',
  })
})
