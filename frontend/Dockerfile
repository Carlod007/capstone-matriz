# Imagen del frontend: se compila con Node y se sirve con Caddy.
#
# Lo que llega al servidor son archivos estaticos, no Node: el navegador
# recibe HTML, CSS y JavaScript ya compilados. Dejar Node en la imagen final
# significaria arrastrar cientos de megas de dependencias que nadie ejecuta.

# ---------------------------------------------------------------- compilar
FROM node:22-slim AS compilacion

WORKDIR /app

# npm ci y no npm install: instala exactamente lo que fija package-lock, de
# modo que la imagen se construye igual hoy que dentro de seis meses.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite incrusta las variables VITE_* en el codigo al compilar, no las lee al
# arrancar. La direccion de la API tiene que decidirse aqui: cambiarla despues
# obliga a reconstruir la imagen.
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ------------------------------------------------------------------ servir
#
# Caddy y no nginx: consigue y renueva los certificados de Let's Encrypt por su
# cuenta. Ver el comentario de cabecera del Caddyfile.
FROM caddy:2-alpine

COPY --from=compilacion /app/dist /usr/share/caddy
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
