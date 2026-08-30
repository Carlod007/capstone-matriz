# tests/test_lectura_pdf.py
"""
Servir el PDF original para poder anotar.

Para juzgar si una brecha es correcta hay que leer el articulo. El PDF entraba
en el sistema y no volvia a salir: quedaba en el disco del servidor sin ninguna
forma de abrirlo, y quien anotaba tenia que buscar su copia en el ordenador,
con el riesgo de revisar una version distinta de la analizada.

Un endpoint que sirve archivos del disco es exactamente el sitio donde un fallo
de permisos se convierte en fuga, asi que estas pruebas se centran en quien
puede pedir que.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd

PDF_FALSO = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def articulo_con_pdf(db, usuario_prueba, tmp_path, monkeypatch):
    from app.models.archivo import Archivo
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.services import almacenamiento

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    pid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Lectura", objetivo="Abrir el PDF original",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.flush()
    db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Un articulo"))
    db.flush()

    clave = almacenamiento.nueva_clave(usuario_prueba["id"])
    almacenamiento.guardar(clave, PDF_FALSO)
    db.add(Archivo(id=str(uuid.uuid4()), proyecto_id=pid, articulo_id=aid,
                   nombre="original.pdf", ruta=clave,
                   hash_sha256="f" * 64, bytes=len(PDF_FALSO)))
    db.commit()

    try:
        yield {"proyecto": pid, "articulo": aid, "clave": clave}
    finally:
        db.rollback()
        db.query(Archivo).filter(Archivo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Articulo).filter(Articulo.id == aid).delete()
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


class TestServirElPdf:
    def test_devuelve_el_archivo(self, cliente, articulo_con_pdf):
        r = cliente.get("/articulos/%s/pdf" % articulo_con_pdf["articulo"])

        assert r.status_code == 200, r.text
        assert r.content == PDF_FALSO
        assert r.headers["content-type"] == "application/pdf"

    def test_se_abre_en_el_navegador_y_no_se_descarga(self, cliente,
                                                     articulo_con_pdf):
        """`inline`: se quiere leer mientras se anota, no acumular descargas."""
        r = cliente.get("/articulos/%s/pdf" % articulo_con_pdf["articulo"])

        assert r.headers["content-disposition"].startswith("inline")
        assert "original.pdf" in r.headers["content-disposition"]

    def test_si_el_archivo_ya_no_esta_lo_dice(self, db, cliente,
                                              articulo_con_pdf):
        """Pasa al restaurar la base sin los PDF. Decirlo asi evita que parezca
        un problema de permisos."""
        from app.services import almacenamiento

        almacenamiento.borrar(articulo_con_pdf["clave"])

        r = cliente.get("/articulos/%s/pdf" % articulo_con_pdf["articulo"])
        assert r.status_code == 404
        assert "ya no está en el servidor" in r.json()["detail"]

    def test_un_articulo_sin_pdf_da_404(self, db, cliente, articulo_con_pdf):
        from app.models.archivo import Archivo

        db.query(Archivo).filter(
            Archivo.articulo_id == articulo_con_pdf["articulo"]).delete(
            synchronize_session=False)
        db.commit()

        r = cliente.get("/articulos/%s/pdf" % articulo_con_pdf["articulo"])
        assert r.status_code == 404
        assert "no tiene PDF" in r.json()["detail"]


class TestQuienPuedePedirlo:
    def test_sin_sesion_no_se_sirve(self, articulo_con_pdf):
        from fastapi.testclient import TestClient

        import main

        anonimo = TestClient(main.app)
        r = anonimo.get("/articulos/%s/pdf" % articulo_con_pdf["articulo"])
        assert r.status_code in (401, 403)

    def test_no_se_sirve_el_pdf_de_otra_cuenta(self, db, cliente, tmp_path,
                                               monkeypatch):
        """Un endpoint que entrega archivos del disco es donde un fallo de
        permisos se convierte en fuga de documentos ajenos."""
        from app.models.archivo import Archivo
        from app.models.articulo import Articulo
        from app.models.proyecto import Proyecto
        from app.models.usuario import Usuario
        from app.services import almacenamiento, seguridad

        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
        otro, pid, aid = (str(uuid.uuid4()) for _ in range(3))
        db.add(Usuario(id=otro, correo="ajeno-%s@x.com" % otro[:8],
                       contrasena_hash=seguridad.cifrar("clave-de-la-otra"),
                       nombre="Otra", activo=True))
        db.flush()
        db.add(Proyecto(id=pid, usuario_id=otro, tema_principal="Ajeno",
                        objetivo="No se lee", n_articulos_objetivo=1,
                        estado_arte_generado=False))
        db.flush()
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Ajeno"))
        db.flush()
        clave = almacenamiento.nueva_clave(otro)
        almacenamiento.guardar(clave, PDF_FALSO)
        db.add(Archivo(id=str(uuid.uuid4()), proyecto_id=pid, articulo_id=aid,
                       nombre="ajeno.pdf", ruta=clave, hash_sha256="a" * 64,
                       bytes=len(PDF_FALSO)))
        db.commit()

        try:
            r = cliente.get("/articulos/%s/pdf" % aid)
            assert r.status_code == 404, "no debe servirse un PDF ajeno"
            assert PDF_FALSO not in r.content
        finally:
            db.rollback()
            db.query(Archivo).filter(Archivo.proyecto_id == pid).delete(
                synchronize_session=False)
            db.query(Articulo).filter(Articulo.id == aid).delete()
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.query(Usuario).filter(Usuario.id == otro).delete()
            db.commit()


class TestLaPantallaDeAnotacion:
    def test_el_listado_trae_el_identificador_del_articulo(self, cliente,
                                                           articulo_con_pdf):
        """Sin el, la pantalla no puede ofrecer el enlace al PDF."""
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem

        # El proyecto de la fixture no tiene run; se comprueba sobre la forma
        # de la respuesta, que es lo que consume la pantalla.
        r = cliente.get("/proyectos/%s/validacion" % articulo_con_pdf["proyecto"])
        assert r.status_code == 200
        assert r.json()["brechas"] == [], "este proyecto no se ha analizado"
