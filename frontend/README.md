# Frontend

Interfaz de la matriz de brechas de investigación. React 19 con Vite y
Tailwind 4, sin router: es una sola pantalla con vistas conmutadas.

La instalación completa del sistema —base de datos, backend y frontend— está
en el [README de la raíz](../README.md). Aquí solo lo propio de esta parte.

## Arrancar

```bash
npm install
npm run dev
```

Queda en <http://localhost:5173>. Necesita el backend en marcha; la dirección
sale de `VITE_API_BASE` en `.env` (copia `.env.example`), y si falta se usa
`http://127.0.0.1:8000`.

## Otros comandos

```bash
npm run build
```

```bash
npm run lint
```

## Organización

```
src/
  App.jsx              vistas, estado y llamadas a la API
  components/UI.jsx    piezas reutilizables: avisos, tablas, zona de archivos
  components/Metricas.jsx  panel de métricas, consumo de cuota y fidelidad
  index.css            tokens de color, tipografía y tema oscuro
```

Los colores no se escriben directos en los componentes: salen de las
variables CSS de `index.css`, que definen a la vez el tema claro y el oscuro.
Un color a mano rompe el tema oscuro sin que se note hasta que alguien lo
activa.
