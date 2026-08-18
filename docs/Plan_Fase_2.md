# Plan de Fase 2 — De herramienta local a servicio accesible

**Estado:** ejecutada y cerrada el 17 de agosto de 2026. El servicio está en
producción en Oracle Always Free con HTTPS. Este documento se conserva como el
plan que se acordó, no como una descripción del estado actual.
**Fecha:** 13 de agosto de 2026
**Punto de partida:** Fase 1 cerrada — esquema gobernado por Alembic, README que
instala desde cero, CI en verde sobre 201 pruebas. *(Esa cifra es la de aquel
día; hoy son 317. Se deja sin actualizar a propósito: es el punto de partida.)*

---

## 1. Objetivo

Que el sistema deje de existir solo en una máquina. Al terminar la fase debe
poder abrirse desde un enlace, en el navegador del PC y en el del celular, sin
arrancar nada a mano.

**Criterio de cierre, en una frase:** entras a una URL desde el celular, inicias
sesión, subes un PDF, lanzas el análisis, cierras el navegador, vuelves diez
minutos después y el resultado está ahí.

Esa última parte —cerrar y volver— es la que obliga a casi todo lo demás.

---

## 2. Decisiones ya tomadas

| Decisión | Elegido | Motivo |
|---|---|---|
| Alcance de la autenticación | Multiusuario, **con el registro cerrado** | Construir la tabla de usuarios y la propiedad de los datos cuesta lo mismo para uno que para cien. Se construye completo y se deja cerrado; abrirlo es cambiar una variable. |
| Infraestructura | **Gratuita** | Requisito del autor. Ver §4. |
| Cuotas, facturación y legalidad | **Fuera de esta fase** | Decisión previa del autor: proyecto personal, sin publicación abierta. |

**Unidad de trabajo.** Un usuario no sube un artículo: sube un *proyecto*, de 5 a
10 artículos. Es lo que fija el tamaño de un trabajo en cola y lo que hace
inviable procesarlo dentro de una petición HTTP.

---

## 3. Deficiencias que impiden el despliegue

Cinco, en orden de gravedad. No son opiniones de estilo: cada una rompe algo
concreto en cuanto el sistema salga de `localhost`.

### D1. El análisis ocurre dentro de la petición HTTP

`POST /proyectos/{id}/analizar_todo` indexa los artículos, ejecuta una
generación por cada uno y sintetiza el estado del arte **sin devolver la
respuesta hasta terminar**. Con el limitador en 4 generaciones por minuto, cinco
artículos son varios minutos de petición abierta.

Cualquier hosting corta las peticiones que pasan de 30–60 segundos. El análisis
no fallaría a medias: fallaría **siempre**, y además consumiendo cuota de API en
un trabajo cuyo resultado nadie recibe.

Es la deficiencia que sostiene el criterio de cierre: sin resolverla, "cerrar el
navegador y volver" es imposible.

### D2. No hay usuarios

Cualquiera que alcance el backend ve y modifica todos los proyectos. No hay
tabla de usuarios, ni dueño en ninguna fila, ni sesión. Publicar el enlace tal
cual es publicar tus artículos y tu cuota de API.

**Hallazgo asociado:** la deduplicación de PDF por hash SHA-256 en
`app/routers/archivos.py` es **global**, sin filtrar por proyecto. Hoy es una
molestia menor —subir el mismo PDF a dos proyectos tuyos devuelve el artículo
del primero—; con varias cuentas se convierte en fuga de datos: subir un PDF que
otra persona ya subió te devolvería *su* artículo. Hay que acotarla al usuario.

### D3. Los PDF viven en el disco local

`STORAGE_DIR=storage/pdfs` guarda los archivos junto al proceso. En un hosting,
ese disco es efímero: se borra en cada despliegue y no se comparte entre el
servidor web y el trabajador. Un artículo subido antes del despliegue de hoy
dejaría de existir.

### D4. El origen del frontend está fijado en el código

`main.py` permite CORS solo desde `localhost:5173` y `127.0.0.1:5173`. Desde un
dominio real, el navegador bloquea todas las llamadas antes de enviarlas. La
lista tiene que salir de una variable de entorno.

### D5. El frontend es una sola pantalla sin rutas

`App.jsx` conmuta vistas con una variable de estado. Consecuencias en un
navegador de verdad: no se puede compartir el enlace de un proyecto, el botón
"atrás" del celular sale de la aplicación en vez de retroceder, y recargar
devuelve al inicio. En móvil, donde el gesto de retroceso es el principal, esto
se nota en el primer minuto de uso.

---

## 4. Infraestructura

**Una sola máquina virtual en Oracle Cloud, nivel Always Free.** Todo vive ahí:
MySQL, el backend, el trabajador y el frontend servido como estático, orquestados
con Docker Compose y con nginx delante resolviendo HTTPS.

| Pieza | Dónde | Coste |
|---|---|---|
| Máquina (4 núcleos ARM, 24 GB RAM, 200 GB disco) | Oracle Always Free | Gratis, permanente |
| MySQL | Contenedor en esa máquina | — |
| Backend y trabajador | Contenedores en esa máquina | — |
| Frontend | Estático servido por nginx | — |
| PDF | Disco de la máquina | — |
| Certificado HTTPS | Let's Encrypt | Gratis |

**Por qué esta y no un PaaS gratuito.** Es la forma de un despliegue de
producción real —máquina, contenedores, proxy inverso, certificado—, no la de un
proveedor concreto: lo que quede escrito en el repositorio sirve en cualquier
sitio. Además no se duerme, no tiene arranques en frío y el disco persiste. Un
PaaS gratuito obliga a repartir la aplicación entre tres proveedores, se duerme a
los quince minutos y no ofrece MySQL, lo que forzaría migrar a PostgreSQL:
reescribir la revisión `0001`, que es DDL de MySQL escrito a mano con `LONGTEXT`
y `CHAR(36)`, y revalidar el esquema entero.

**Consecuencia sobre el plan:** con disco persistente, el almacenamiento de
objetos deja de hacer falta. El paso que estaba previsto para S3/R2 se retira
—1,5 días y una cuenta menos—, aunque la interfaz de almacenamiento se deja
preparada por si algún día hay más de una máquina.

**Dos fricciones conocidas, dichas por delante:**

1. Oracle pide **tarjeta para verificar identidad**. No cobra ni pasa a pago por
   sí solo, pero el trámite existe.
2. A veces **no hay capacidad ARM libre** en la región elegida y la creación
   falla con "out of host capacity". Se resuelve reintentando o cambiando de
   región; puede costar un rato el día de crear la instancia.

**Alternativa sin tarjeta**, si esas fricciones pesan: Cloudflare Tunnel desde tu
PC. Da URL real y HTTPS, pero solo funciona con la computadora encendida, así que
no cumple "entrar desde el celular cuando sea". El trabajo del plan es el mismo:
todo va en Docker, y mover de un sitio a otro es volver a levantar los
contenedores.

---

## 5. Pasos

Ocho, en orden de dependencia. Cada uno se cierra con sus pruebas en verde y su
commit, como en Fase 1.

### Paso 1 — Usuarios y sesión *(~2 días)*

Tabla `usuario` (id, correo, contraseña cifrada con bcrypt, nombre, fecha de
alta). Registro, inicio de sesión y JWT firmado. `contraseña_hash` nunca sale en
ninguna respuesta.

El registro se construye entero pero queda **cerrado** tras la variable
`REGISTRO_ABIERTO=false`: por ahora solo hay una cuenta, la tuya. Abrirlo el día
que quieras es cambiar ese valor, sin tocar código.

Migración de Alembic, no `create_all()`.

**Prueba de cierre:** registrarse, iniciar sesión, y que un token inválido o
caducado devuelva 401. Con el registro cerrado, que el alta responda 403.

### Paso 2 — Propiedad de los datos *(~1,5 días)*

`proyecto.usuario_id`, con dependencia `usuario_actual` en los 29 endpoints. La
comprobación va **en la consulta**, no en un `if` posterior: filtrar por dueño
al construir el `SELECT` hace imposible olvidarse en un caso.

Los proyectos que ya existen se asignan a tu cuenta en la migración; no se
pierde nada de lo hecho hasta ahora.

Se acota aquí la deduplicación por hash al usuario (D2).

**Prueba de cierre:** con dos usuarios de prueba, que A pida el proyecto de B
por su identificador y reciba 404 —no 403: un 403 confirma que ese proyecto
existe—. Una prueba por endpoint, sin excepciones.

### Paso 3 — Trabajos en segundo plano *(~2,5 días)*

El paso que sostiene el criterio de cierre.

`analizar_todo` deja de ejecutar y pasa a **encolar**: responde de inmediato con
un identificador de trabajo. Un proceso trabajador aparte toma los pendientes y
los procesa.

**Sin Redis ni Celery.** Las tablas `run` y `run_item` ya son una cola: tienen
estado por artículo (`pendiente`, `extraido`, `analizado`, `fallido`) y el
frontend ya consulta su avance. El trabajador toma items pendientes con
`SELECT ... FOR UPDATE SKIP LOCKED`, que es exactamente para esto. Añadir una
pieza de infraestructura para reimplementar lo que el esquema ya modela sería
trabajo de más y un servicio más que pagar y vigilar.

Incluye reintentos y marcar como fallido lo que no avanza, para que un trabajo
atascado no quede "en progreso" para siempre.

**Prueba de cierre:** encolar un análisis, cortar el trabajador a mitad,
reiniciarlo, y que termine sin repetir lo ya hecho ni gastar cuota de más.

### Paso 4 — Almacenamiento tras una interfaz *(~0,5 días)*

Reducido: con disco persistente en la máquina no hace falta almacenamiento de
objetos. Solo se aísla el acceso a archivos tras una interfaz, de modo que
`STORAGE_DIR` no aparezca repartido por los routers y añadir S3 el día que haya
más de una máquina sea escribir una implementación, no buscar rutas por todo el
código.

Los archivos se guardan bajo una carpeta por usuario, para que el aislamiento
del paso 2 valga también en el disco.

### Paso 5 — Configuración por entorno *(~0,5 días)*

CORS desde variable de entorno; secreto del JWT obligatorio y sin valor por
defecto —un secreto por defecto es peor que ninguno, porque parece configurado—.
Un módulo de configuración que falle al arrancar si falta algo, en vez de fallar
raro en la primera petición.

### Paso 6 — Rutas en el frontend *(~1,5 días)*

`react-router` con URL por proyecto y por vista. Enlaces compartibles, botón
atrás funcional, recarga que no pierde el sitio. Pantallas de registro e inicio
de sesión, y el token guardado con renovación silenciosa.

**Comprobación en móvil real**, no solo estrechando la ventana del navegador.

### Paso 7 — Docker *(~1,5 días)*

`Dockerfile` para el backend y otro para el trabajador; `docker-compose.yml` con
MySQL, nginx y volúmenes para los PDF y los datos de la base. `alembic upgrade
head` al arrancar. Las imágenes se construyen para ARM, que es la arquitectura de
la máquina.

Efecto secundario que importa: el README pasa de nueve pasos a uno, y el mismo
`compose` que usas en tu PC es el que corre en el servidor.

### Paso 8 — Despliegue *(~1,5 días)*

Crear la máquina, abrir los puertos, instalar Docker, subir el `compose`,
certificado de Let's Encrypt con renovación automática, y arranque al reiniciar
la máquina. Copia de seguridad de la base programada, porque a partir de aquí los
datos ya no están en tu PC.

Verificación final: el recorrido completo desde el celular.

---

## 6. Calendario

**Total: 10 días de trabajo efectivo.** A ritmo de estudiante con clases, entre
tres y cuatro semanas.

Los pasos 1 a 3 son el 60 % del valor: con ellos el sistema ya es multiusuario y
no bloquea. Del 4 en adelante es lo que hace falta para que viva fuera de tu
máquina.

---

## 7. Lo que tienes que hacer tú

Nada de esto lo puedo hacer yo, porque implica cuentas y credenciales.

| Cuándo | Qué |
|---|---|
| Antes del paso 7 | Instalar Docker Desktop |
| Antes del paso 8 | Crear cuenta en Oracle Cloud y verificar identidad con tarjeta (no cobra) |
| Antes del paso 8 | Crear la máquina Always Free y darme su dirección; guardar tú la llave SSH |
| En el paso 8 | Pegar los secretos en el servidor: clave de Gemini, contraseña de la base, secreto del JWT |
| En el paso 6 | Probar en tu celular y decirme qué se ve mal |
| Opcional | Un dominio propio (~10 USD/año). Sin él, se entra por la dirección IP o un subdominio gratuito |

**No tocaré credenciales ni llaves.** Te diré exactamente qué variable configurar
y con qué valor; escribirlas en el servidor lo haces tú.

---

## 8. Riesgos

| Riesgo | Cómo se mitiga |
|---|---|
| La cuota gratuita de Gemini es de 20 generaciones al día, compartida por *todos* los usuarios de la instancia | Con dos o tres cuentas conocidas no molesta. Abrir el registro a desconocidos sí exige cuotas por usuario, que es Fase 4 y está aplazada. |
| El paso 2 toca los 29 endpoints y es donde más fácil se cuela un fallo de seguridad | Una prueba de aislamiento por endpoint, y `/security-review` sobre el diff antes de dar el paso por cerrado. |
| Migrar los datos actuales al añadir usuarios | Se hace con migración de Alembic, reversible, y se prueba primero sobre una copia de la base. |
| Los PDF y la base que ya tienes están solo en tu disco | Se copian al servidor en el paso 8, y desde ahí la copia de seguridad programada se encarga. |
| Oracle puede no tener capacidad ARM libre al crear la instancia | Reintentar o cambiar de región. Si se atasca, el túnel desde tu PC sirve de puente mientras tanto: el trabajo del plan no cambia. |

---

## 9. Fuera de alcance

Aplazado por decisión previa, no por olvido:

- Cuotas por usuario, facturación y textos legales *(Fase 4)*
- Anclaje humano de las métricas con conjunto anotado por expertos *(N6, paso 8
  de la fase anterior)*
- Rediseño visual más allá de lo necesario para que funcione en móvil

---

## 10. Qué hace falta para empezar

Nada por tu parte todavía. Las cuentas y la máquina no hacen falta hasta el paso
7; los seis primeros pasos se desarrollan y se prueban en tu PC como hasta ahora.

Arranco por el paso 1.
