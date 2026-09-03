import { expect, test } from '@playwright/test'


async function iniciarSesion(page) {
  await page.addInitScript(() => {
    localStorage.setItem('matriz.sesion', JSON.stringify({
      token: 'token-e2e',
      nombre: 'Investigadora',
    }))
  })
}

test('crea un proyecto conservando los datos introducidos', async ({ page }) => {
  await iniciarSesion(page)
  let recibido = null

  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request()
    const camino = new URL(peticion.url()).pathname.replace(/^\/api/, '')
    if (camino === '/proyectos' && peticion.method() === 'POST') {
      recibido = peticion.postDataJSON()
      await ruta.fulfill({ json: { id: 'proyecto-nuevo', ...recibido } })
      return
    }
    if (camino === '/proyectos' && peticion.method() === 'GET') {
      await ruta.fulfill({ json: [] })
      return
    }
    if (camino === '/consumo') {
      await ruta.fulfill({ json: {} })
      return
    }
    await ruta.fulfill({ status: 404, json: { detail: 'Ruta simulada no definida' } })
  })

  await page.goto('/proyectos/nuevo')
  await page.getByLabel('Tema principal').fill('IA generativa en educación')
  await page.getByLabel('Metodología').fill('DSRM')
  await page.getByRole('textbox', { name: 'Objetivo de investigación' }).fill('Evaluar apoyo a la revisión académica')
  await page.getByLabel('Sector de investigación').fill('Educación superior')
  await page.getByLabel('Número de artículos (5–10)').fill('7')
  await page.getByRole('button', { name: 'Crear', exact: true }).click()

  await expect(page).toHaveURL(/\/proyectos$/)
  expect(recibido).toEqual({
    tema_principal: 'IA generativa en educación',
    metodologia_txt: 'DSRM',
    sector_txt: 'Educación superior',
    objetivo: 'Evaluar apoyo a la revisión académica',
    n_articulos_objetivo: 7,
  })
})

test('confirma dentro de la aplicación antes de quitar un artículo', async ({ page }) => {
  await iniciarSesion(page)
  let eliminado = false

  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request()
    const camino = new URL(peticion.url()).pathname.replace(/^\/api/, '')
    if (camino === '/proyectos/p-1') {
      await ruta.fulfill({ json: {
        id: 'p-1',
        tema_principal: 'Proyecto de prueba',
        n_articulos_objetivo: 5,
      } })
      return
    }
    if (camino === '/proyectos/p-1/articulos' && peticion.method() === 'GET') {
      await ruta.fulfill({ json: eliminado ? [] : [{
        id: 'a-1',
        titulo: 'Artículo ya analizado',
        doi: '10.1000/prueba',
        tiene_analisis: true,
      }] })
      return
    }
    if (camino === '/proyectos/p-1/run_activo') {
      await ruta.fulfill({ json: null })
      return
    }
    if (camino === '/proyectos/p-1/articulos/a-1' && peticion.method() === 'DELETE') {
      eliminado = true
      await ruta.fulfill({ status: 204 })
      return
    }
    await ruta.fulfill({ status: 404, json: { detail: 'Ruta simulada no definida' } })
  })

  await page.goto('/proyectos/p-1/articulos')
  await page.getByRole('button', { name: 'Quitar', exact: true }).click()

  const dialogo = page.getByRole('dialog', { name: 'Quitar artículo del proyecto' })
  await expect(dialogo).toBeVisible()
  await expect(dialogo).toContainText('No se puede deshacer')
  await dialogo.getByRole('button', { name: 'Quitar artículo' }).click()

  await expect(dialogo).toBeHidden()
  await expect(page.getByRole('status')).toContainText('Artículo quitado')
  await expect(page.getByText('Todavía no hay artículos')).toBeVisible()
})

test('mantiene ciega la revisión y abre el PDF con autenticación', async ({ page }) => {
  await iniciarSesion(page)
  let autorizacionPdf = null

  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request()
    const camino = new URL(peticion.url()).pathname.replace(/^\/api/, '')
    if (camino === '/proyectos/p-1') {
      await ruta.fulfill({ json: { id: 'p-1', tema_principal: 'Proyecto ciego' } })
      return
    }
    if (camino === '/proyectos/p-1/validacion') {
      await ruta.fulfill({ json: {
        brechas: [{
          id: 'b-1',
          articulo_id: 'a-1',
          articulo: 'Artículo para revisar',
          tipo_brecha: 'metodológica',
          brecha: 'No se informó validación externa.',
          oportunidad: 'Validar en otro conjunto de datos.',
          veredicto: null,
          otros_anotadores: 0,
        }],
        resumen: {
          total: 1,
          anotadas: 0,
          pendientes: 1,
          revision_completa: false,
          acierto: null,
          por_veredicto: null,
          anotadores: 0,
        },
      } })
      return
    }
    if (camino === '/articulos/a-1/pdf') {
      autorizacionPdf = peticion.headers().authorization
      await ruta.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: '%PDF-1.4\n% prueba',
      })
      return
    }
    await ruta.fulfill({ status: 404, json: { detail: 'Ruta simulada no definida' } })
  })

  await page.goto('/proyectos/p-1/revisar')

  await expect(page.getByText(/Faltan 1\./)).toBeVisible()
  await expect(page.getByText('N2.1')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /juicio frente a las métricas/i })).toHaveCount(0)

  await page.getByRole('button', { name: 'Leer el artículo (PDF)' }).click()
  await expect.poll(() => autorizacionPdf).toBe('Bearer token-e2e')
})
