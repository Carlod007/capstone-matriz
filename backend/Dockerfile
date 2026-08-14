# Imagen del backend y del trabajador.
#
# Es una sola para los dos: comparten dependencias y codigo, y lo unico que
# cambia es el comando. Dos imagenes obligarian a instalar todo dos veces y a
# recordar reconstruir ambas cuando se anada un paquete.
#
# La construccion va en dos partes para que las dependencias no se reinstalen
# cada vez que se toca una linea de codigo: primero requirements.txt, que
# cambia poco, y despues el codigo, que cambia constantemente.

FROM python:3.13-slim

# Tesseract con espanol e ingles: es el OCR de respaldo para PDF escaneados,
# y lo pide el codigo como "spa+eng". Sin los paquetes de idioma, Tesseract
# se instala pero falla al reconocer.
#
# libgl1 y libglib2.0-0 los necesita PyMuPDF para renderizar paginas a imagen,
# que es el paso previo al OCR.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Sin cache de pip: en una imagen no sirve de nada y ocupa espacio en la capa.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuario sin privilegios. Si alguien consigue ejecutar codigo a traves de la
# aplicacion, que no sea como root.
RUN useradd --create-home --uid 1000 matriz \
    && mkdir -p /app/storage/pdfs \
    && chown -R matriz:matriz /app
USER matriz

# PYTHONUNBUFFERED para que los registros salgan al momento y no por bloques:
# en un contenedor, `docker logs` es la unica ventana a lo que ocurre.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Sin --reload: recarga al detectar cambios en los archivos, algo que en un
# servidor no ocurre y que solo anade un vigilante de ficheros de mas.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
