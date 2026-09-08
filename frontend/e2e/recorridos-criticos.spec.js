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

test('abre las brechas mientras se genera el estado del arte', async ({ page }) => {
  await iniciarSesion(page)
  const proyecto = {
    id: 'p-1',
    tema_principal: 'Estructuras civiles',
    n_articulos_objetivo: 5,
    n_articulos: 5,
    n_brechas: 5,
    estado_proceso: 'generando_estado_arte',
    tiene_estado_arte: false,
    tiene_estado_arte_actual: false,
  }

  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request()
    const camino = new URL(peticion.url()).pathname.replace(/^\/api/, '')
    if (camino === '/proyectos') {
      await ruta.fulfill({ json: [proyecto] })
      return
    }
    if (camino === '/proyectos/p-1') {
      await ruta.fulfill({ json: proyecto })
      return
    }
    if (camino === '/proyectos/p-1/articulos') {
      await ruta.fulfill({ json: [] })
      return
    }
    if (camino === '/proyectos/p-1/metricas') {
      await ruta.fulfill({ json: { run: null, aviso: 'Síntesis en curso' } })
      return
    }
    if (camino.endsWith('/consumo') || camino === '/consumo') {
      await ruta.fulfill({ json: {} })
      return
    }
    await ruta.fulfill({ status: 404, json: { detail: 'Ruta simulada no definida' } })
  })

  await page.goto('/proyectos')
  await expect(page.getByText('Sintetizando')).toBeVisible()
  await expect(page.getByText('Las brechas ya están disponibles')).toBeVisible()
  await page.getByRole('button', { name: /Ver resultados/ }).click()

  await expect(page).toHaveURL(/\/proyectos\/p-1\/brechas$/)
  await expect(page.getByText('Ya puedes revisar las brechas mientras se redacta la síntesis final.'))
    .toBeVisible()
})

test('prioriza artículos y lectura sencilla antes del detalle técnico', async ({ page }) => {
  await iniciarSesion(page)
  const proyecto = {
    id: 'p-resultados',
    tema_principal: 'Estructuras civiles',
    n_articulos_objetivo: 5,
    n_articulos: 2,
    n_brechas: 2,
    estado_proceso: 'resultados_listos',
    tiene_estado_arte: true,
    tiene_estado_arte_actual: true,
  }
  const metrica = (codigo, nombre, nivel, mediana, ambito = 'brecha') => ({
    codigo,
    nombre,
    nivel,
    ambito,
    minimo: mediana,
    p25: mediana,
    mediana,
    p75: mediana,
    maximo: mediana,
    media: mediana,
    iqr: 0,
    n: ambito === 'run' ? 1 : 2,
    n_intentos: ambito === 'run' ? 1 : 2,
    mejor: 'alto',
    rango: '0 a 1',
    descripcion: 'Descripción de prueba.',
    interpretacion: 'Interpretación de prueba.',
    version_formula: 2,
  })
  const metricas = [
    metrica('N2.1', 'Respaldo de afirmaciones evidenciales', 'N2 Fidelidad', 0.9),
    metrica('N2.2', 'Trazabilidad', 'N2 Fidelidad', 0.85),
    metrica('N2.4', 'Composición evidencial', 'N2 Fidelidad', 0.7),
    metrica('N2.5', 'Contradicciones', 'N2 Fidelidad', 0),
    metrica('N2.6', 'Brecha ya resuelta', 'N2 Fidelidad', 0),
    metrica('N1.2', 'Cobertura seccional', 'N1 Recuperación', 1),
    metrica('N3.1', 'Discriminabilidad', 'N3 Especificidad', 0.35, 'run'),
    { ...metrica('N3.2', 'Densidad de anclajes', 'N3 Especificidad', 3), rango: 'por 100 palabras' },
    metrica('N4.2', 'Similitud semántica', 'N4 Resumen', 0.89),
    { ...metrica('N2.verificada', 'Verificación realizada', 'N2 Fidelidad', 1), rango: '0 o 1' },
  ]

  await page.route('**/api/**', async (ruta) => {
    const camino = new URL(ruta.request().url()).pathname.replace(/^\/api/, '')
    if (camino === '/proyectos/p-resultados') {
      await ruta.fulfill({ json: proyecto })
      return
    }
    if (camino === '/proyectos/p-resultados/articulos') {
      await ruta.fulfill({ json: [
        { id: 'a-1', titulo: 'Artículo estructural A', doi: '10.1000/a' },
        { id: 'a-2', titulo: 'Artículo estructural B', doi: '10.1000/b' },
      ] })
      return
    }
    if (camino === '/proyectos/p-resultados/metricas') {
      await ruta.fulfill({ json: {
        run: { id: 'run-1', estado: 'completado', tokens_in: 120, tokens_out: 30 },
        conteos: { articulos: 2, brechas: 2, por_estado_validacion: {} },
        estado_arte: { version: 1 },
        validacion_calibrada: false,
        metricas,
      } })
      return
    }
    if (camino === '/proyectos/p-resultados/consumo') {
      await ruta.fulfill({ json: {
        generaciones_estimadas: 19,
        limite_diario_nivel_gratuito: 20,
        restantes_estimadas: 1,
        alcanza_para_otra_ejecucion: false,
        coste_de_una_ejecucion: 5,
        generaciones_que_faltan: 4,
        generaciones_fallidas: 0,
        renovaciones: [],
      } })
      return
    }
    await ruta.fulfill({ status: 404, json: { detail: 'Ruta simulada no definida' } })
  })

  await page.goto('/proyectos/p-resultados/brechas')

  await expect(page.getByRole('button', { name: 'Volver a proyectos' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Artículos y brechas' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Qué dicen las mediciones principales' })).toBeVisible()
  await expect(page.getByText('Fidelidad verificada')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Verificar fidelidad' })).toHaveCount(0)

  const articulosAntes = await page.locator('body').evaluate(() => {
    const titulos = [...document.querySelectorAll('h2')]
    const articulos = titulos.find((nodo) => nodo.textContent === 'Artículos y brechas')
    const mediciones = titulos.find(
      (nodo) => nodo.textContent === 'Qué dicen las mediciones principales',
    )
    return Boolean(
      articulos
      && mediciones
      && (articulos.compareDocumentPosition(mediciones) & Node.DOCUMENT_POSITION_FOLLOWING),
    )
  })
  expect(articulosAntes).toBeTruthy()

  await page.getByText('Repetir el proceso').click()
  await expect(page.getByRole('button', { name: 'Volver a verificar' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Volver a analizar' })).toBeVisible()

  await expect(page.getByRole('heading', { name: /Explorar las 10 métricas/i })).toHaveCount(0)
  await page.getByRole('button', { name: 'Ver las 10 métricas técnicas' }).click()
  await expect(page.getByRole('heading', { name: /Explorar las 10 métricas/i })).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: 'Volver a proyectos' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Revisar brecha' }).first()).toBeVisible()
  const desborda = await page.locator('html').evaluate(
    (nodo) => nodo.scrollWidth > nodo.clientWidth + 1,
  )
  expect(desborda).toBe(false)
})

test('confirma con gravedad antes de eliminar un proyecto con resultados', async ({ page }) => {
  await iniciarSesion(page)
  let eliminado = false
  const proyecto = {
    id: 'p-borrar',
    tema_principal: 'Proyecto con resultados',
    n_articulos_objetivo: 5,
    n_articulos: 5,
    n_brechas: 5,
    estado_proceso: 'resultados_listos',
    tiene_estado_arte: true,
    tiene_estado_arte_actual: true,
  }

  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request()
    const camino = new URL(peticion.url()).pathname.replace(/^\/api/, '')
    if (camino === '/proyectos' && peticion.method() === 'GET') {
      await ruta.fulfill({ json: eliminado ? [] : [proyecto] })
      return
    }
    if (camino === '/proyectos/p-borrar' && peticion.method() === 'DELETE') {
      eliminado = true
      await ruta.fulfill({ json: {
        proyecto_id: 'p-borrar',
        borrado: true,
        pdf_no_borrados: 0,
      } })
      return
    }
    if (camino === '/consumo') {
      await ruta.fulfill({ json: {} })
      return
    }
    await ruta.fulfill({ status: 404, json: { detail: 'Ruta simulada no definida' } })
  })

  await page.goto('/proyectos')
  await page.getByRole('button', { name: 'Eliminar', exact: true }).click()

  const dialogo = page.getByRole('dialog', { name: 'Eliminar proyecto' })
  await expect(dialogo).toContainText('Este proyecto ya tiene resultados')
  await expect(dialogo).toContainText('La cuota de API que ya se consumió tampoco se recupera')
  await dialogo.getByRole('button', { name: 'Eliminar proyecto' }).click()

  await expect(dialogo).toBeHidden()
  await expect(page.getByRole('status')).toContainText('Proyecto eliminado')
  await expect(page.getByText('Todavía no hay proyectos')).toBeVisible()
})
