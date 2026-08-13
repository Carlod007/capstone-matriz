# tests/conftest.py
"""Fixtures compartidas.

Las pruebas se ejecutan siempre en modo simulado: no consumen cuota de API y
los embeddings son deterministas, de modo que un fallo señala una regresión
real y no la variabilidad del modelo.
"""

import os
import sys
import uuid

# Deben fijarse antes de importar la aplicación: varios módulos leen estas
# variables al configurarse, y `app.config` exige el secreto para arrancar.
# Con `setdefault`, un .env presente manda; donde no lo hay —integración
# continua, una máquina recién clonada— las pruebas siguen corriendo.
os.environ.setdefault("GEMINI_MODE", "mock")
os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import fitz  # noqa: E402
import pytest  # noqa: E402


# --------------------------------------------------------------- artículos
SECCIONES_ARTICULO = [
    (None, "Revista Internacional de Tecnologia Educativa. Volumen 12, numero 3. "
           "doi 10.1000/rite.2024.0033. Recibido 3 de marzo de 2024. "
           "Ana Torres, Universidad Nacional. Luis Gomez, Instituto Tecnologico. ", 2),
    ("Abstract", "Este trabajo evalua un sistema de analisis automatico de literatura "
                 "cientifica basado en modelos de lenguaje de gran escala aplicados a "
                 "articulos indexados en bases de datos academicas reconocidas. ", 3),
    ("1. Introduccion", "La revision de literatura es un proceso costoso en tiempo y "
                        "esfuerzo para el investigador. Diversos autores han propuesto "
                        "herramientas de apoyo automatizado. Sin embargo la mayoria de "
                        "las references citadas por estos trabajos se limitan a dominios "
                        "anglofonos, restringiendo su aplicabilidad regional. ", 12),
    ("2. Trabajos relacionados", "Estudios previos abordaron la clasificacion automatica "
                                 "de resumenes y la extraccion de metadatos bibliograficos "
                                 "con resultados dispares segun el dominio analizado. ", 8),
    ("3. Metodologia", "Se empleo un diseno cuasi experimental con una muestra de sesenta "
                       "articulos seleccionados mediante muestreo intencional. El protocolo "
                       "de anotacion fue aplicado por dos evaluadores independientes. No se "
                       "realizo validacion cruzada ni se reporto el acuerdo entre anotadores, "
                       "lo que limita la reproducibilidad del procedimiento experimental. ", 10),
    ("4. Resultados", "El sistema alcanzo una precision de 0.71 y una exhaustividad de 0.58 "
                      "sobre el conjunto evaluado. Los resumenes generados obtuvieron valores "
                      "de solapamiento lexico inferiores a los reportados previamente. ", 9),
    ("5. Discusion", "Los hallazgos indican que el rendimiento depende fuertemente del dominio "
                     "disciplinar analizado. La ausencia de un corpus anotado en espanol impide "
                     "contrastar el desempeno con poblaciones hispanohablantes. ", 7),
    ("6. Limitaciones", "El tamano muestral es reducido y se concentra en un unico campo. No se "
                        "evaluo la estabilidad del sistema entre ejecuciones repetidas. ", 4),
    ("7. Conclusiones", "El enfoque resulta prometedor como herramienta de apoyo, no como "
                        "sustituto del criterio experto en la revision de literatura. ", 3),
    ("Referencias", "[1] Smith J. Automated screening methods. Journal of Reviews, 2023. "
                    "[2] Lopez M. Text mining aplicado. Revista de Informatica, 2022. ", 6),
]

SECCIONES_AJENO = [
    (None, "Boletin de Biologia Marina. Volumen 44. doi 10.2000/bbm.2024.0012. ", 2),
    ("Abstract", "Estudio sobre la migracion estacional de cetaceos en aguas frias del "
                 "hemisferio sur y su relacion con la temperatura superficial. ", 3),
    ("1. Introduccion", "Las poblaciones de ballena jorobada recorren miles de kilometros "
                        "entre zonas de alimentacion y de reproduccion cada temporada. ", 12),
    ("3. Metodologia", "Se instalaron transmisores satelitales en veinte ejemplares adultos "
                       "durante tres campanas oceanograficas consecutivas en alta mar. ", 10),
    ("4. Resultados", "Las rutas registradas muestran una desviacion respecto a los patrones "
                      "historicos documentados en la region durante las decadas previas. ", 9),
    ("5. Discusion", "El calentamiento del agua superficial podria explicar el desplazamiento "
                     "observado en las zonas de alimentacion de la especie estudiada. ", 7),
    ("Referencias", "[1] Ocean Research Group. Cetacean tracking. Marine Journal, 2023. ", 5),
]


def _construir_pdf(ruta: str, secciones) -> str:
    doc = fitz.open()
    pag = doc.new_page()
    y = 55
    for enc, cuerpo, repes in secciones:
        texto = cuerpo * repes
        if enc:
            if y > 700:
                pag = doc.new_page()
                y = 55
            pag.insert_text((55, y), enc, fontsize=12, fontname="hebo")
            y += 20
        restante = texto
        while restante:
            if y > 690:
                pag = doc.new_page()
                y = 55
            caja = fitz.Rect(55, y, 545, 740)
            sobra = pag.insert_textbox(caja, restante, fontsize=9, fontname="helv")
            if sobra < 0:
                # No cupo entero: se corta y continua en la pagina siguiente.
                corte = max(1, int(len(restante) * 0.55))
                pag.insert_textbox(caja, restante[:corte], fontsize=9, fontname="helv")
                restante = restante[corte:]
                pag = doc.new_page()
                y = 55
                continue
            y = 740 - sobra + 12
            restante = ""
    doc.save(ruta)
    doc.close()
    return ruta


@pytest.fixture(scope="session")
def pdf_articulo(tmp_path_factory) -> str:
    ruta = str(tmp_path_factory.mktemp("pdfs") / "articulo.pdf")
    return _construir_pdf(ruta, SECCIONES_ARTICULO)


@pytest.fixture(scope="session")
def pdf_ajeno(tmp_path_factory) -> str:
    ruta = str(tmp_path_factory.mktemp("pdfs") / "ajeno.pdf")
    return _construir_pdf(ruta, SECCIONES_AJENO)


@pytest.fixture(scope="session")
def texto_articulo(pdf_articulo) -> str:
    from app.utils.text_extractor import extract_full_text
    return extract_full_text(pdf_articulo)


# --------------------------------------------------------------- contextos
CONTEXTO_PROPIO = {
    "tema_principal": "Deteccion automatica de brechas de investigacion con IA generativa",
    "objetivo": "Identificar vacios metodologicos y limitaciones en estudios sobre "
                "analisis automatizado de literatura cientifica en educacion",
    "sector_txt": "Educacion superior",
    "metodologia_txt": "DSRM",
}

CONTEXTO_AJENO = {
    "tema_principal": "Migracion de cetaceos y temperatura oceanica",
    "objetivo": "Determinar la relacion entre el calentamiento del agua superficial "
                "y las rutas migratorias de ballenas en el hemisferio sur",
    "sector_txt": "Biologia marina",
    "metodologia_txt": "Seguimiento satelital",
}


@pytest.fixture(scope="session")
def contexto_propio() -> dict:
    return dict(CONTEXTO_PROPIO)


@pytest.fixture(scope="session")
def contexto_ajeno() -> dict:
    return dict(CONTEXTO_AJENO)


# --------------------------------------------------------------- base de datos
@pytest.fixture(scope="session")
def db():
    """Sesión contra MySQL. Las pruebas que la usan van marcadas con `bd`."""
    try:
        from app.database import SessionLocal
        s = SessionLocal()
        s.execute.__self__  # fuerza que la conexión exista
    except Exception as e:  # pragma: no cover
        pytest.skip("Sin conexión a MySQL: %s" % e)
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def usuario_prueba(db):
    """Cuenta a la que pertenecen los datos de las pruebas.

    Desde que los proyectos tienen dueño, uno sin él no lo ve nadie, así que
    las pruebas de endpoint necesitan una cuenta real y su sesión.
    """
    from app.models.usuario import Usuario
    from app.services import seguridad

    correo = "pruebas-%s@ejemplo.com" % uuid.uuid4().hex[:8]
    clave = "contrasena-de-las-pruebas"
    u = Usuario(id=str(uuid.uuid4()), correo=correo,
                contrasena_hash=seguridad.cifrar(clave),
                nombre="Cuenta de pruebas", activo=True)
    db.add(u)
    db.commit()
    try:
        yield {"id": u.id, "correo": correo, "contrasena": clave}
    finally:
        db.rollback()
        db.query(Usuario).filter(Usuario.id == u.id).delete()
        db.commit()


@pytest.fixture(scope="session")
def cliente(usuario_prueba):
    """Cliente HTTP con la sesión ya iniciada.

    Lleva la cabecera puesta por defecto, para que las pruebas no tengan que
    repetirla en cada llamada.
    """
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    r = c.post("/auth/login", json={"correo": usuario_prueba["correo"],
                                    "contrasena": usuario_prueba["contrasena"]})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": "Bearer %s" % r.json()["token"]})
    return c


@pytest.fixture(scope="session")
def proyecto_indexado(db, usuario_prueba, pdf_articulo, pdf_ajeno):
    """Crea un proyecto con tres artículos y los indexa.

    - `pertinente`: el artículo del tema del proyecto.
    - `duplicado` : el mismo PDF cargado como otro artículo (control C4).
    - `ajeno`     : un artículo de otro dominio (control C3).

    Todo se elimina al terminar la sesión de pruebas.
    """
    from app.models.proyecto import Proyecto
    from app.models.articulo import Articulo
    from app.models.archivo import Archivo, EstadoArchivo
    from app.services.embedding_service import index_articulo

    pid = str(uuid.uuid4())
    ids = {"pertinente": str(uuid.uuid4()),
           "duplicado": str(uuid.uuid4()),
           "ajeno": str(uuid.uuid4())}

    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal=CONTEXTO_PROPIO["tema_principal"],
                    objetivo=CONTEXTO_PROPIO["objetivo"], metodologia_txt="DSRM",
                    sector_txt="Educacion superior", n_articulos_objetivo=3,
                    estado_arte_generado=False))
    db.flush()

    for clave, ruta in (("pertinente", pdf_articulo),
                        ("duplicado", pdf_articulo),
                        ("ajeno", pdf_ajeno)):
        db.add(Articulo(id=ids[clave], proyecto_id=pid, doi=None,
                        titulo="prueba-%s" % clave))
        db.flush()
        db.add(Archivo(id=str(uuid.uuid4()), proyecto_id=pid, articulo_id=ids[clave],
                       nombre="%s.pdf" % clave, ruta=ruta,
                       hash_sha256=uuid.uuid4().hex * 2, bytes=0,
                       estado=EstadoArchivo.extraido))
        db.flush()
    db.commit()

    for clave in ids:
        index_articulo(db, ids[clave])

    try:
        yield {"proyecto_id": pid, **ids}
    finally:
        db.rollback()
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()
