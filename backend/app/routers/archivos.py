import os, uuid, hashlib, re
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.database import get_db
from app.models.archivo import Archivo, EstadoArchivo
from app.models.articulo import Articulo
import fitz  # PyMuPDF
from pdfminer.high_level import extract_text as pdfminer_extract

load_dotenv()
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage/pdfs")

router = APIRouter(prefix="/proyectos", tags=["archivos"])

DOI_RE = re.compile(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', re.I)

def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def clean(v):
    if not v:
        return None
    t = v.strip().lower()
    return None if t in {"", "string", "null", "undefined"} else v.strip()

def extract_title_and_doi(path: str) -> tuple[str | None, str | None]:
    title = None
    doi = None

    # 1) PyMuPDF: metadata + primeras 10 páginas
    try:
        with fitz.open(path) as doc:
            meta = doc.metadata or {}
            if meta.get("title"):
                t = meta["title"].strip()
                if len(t) >= 5:
                    title = t[:500]

            texts = []
            pages_to_read = min(10, len(doc))
            for i in range(pages_to_read):
                texts.append(doc[i].get_text("text"))
            joined = "\n".join(texts)

            if not doi:
                m = DOI_RE.search(joined)
                if m:
                    doi = m.group(0)

            if not title:
                lines = [l.strip() for l in joined.splitlines() if l.strip()]
                for l in lines[:50]:
                    if 15 <= len(l) <= 200:
                        title = l[:500]
                        break
    except Exception:
        pass

    # 2) Fallback pdfminer: documento completo
    if not title or not doi:
        try:
            txt2 = pdfminer_extract(path)
            if not doi:
                m2 = DOI_RE.search(txt2)
                if m2:
                    doi = m2.group(0)
            if not title:
                lines = [l.strip() for l in txt2.splitlines() if l.strip()]
                for l in lines[:80]:
                    if 15 <= len(l) <= 200:
                        title = l[:500]
                        break
        except Exception:
            pass

    return title, doi

@router.post("/{proyecto_id}/archivos")
async def subir_pdf(
    proyecto_id: str,
    pdf: UploadFile = File(...),
    titulo: str | None = Form(None),
    doi: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo PDF")
    os.makedirs(STORAGE_DIR, exist_ok=True)

    data = await pdf.read()
    file_hash = _sha256_bytes(data)

    # Deduplicación por hash
    duplicado = db.query(Archivo).filter(Archivo.hash_sha256 == file_hash).first()
    if duplicado:
        return {
            "articulo_id": duplicado.articulo_id,
            "archivo_id": duplicado.id,
            "titulo": titulo,
            "doi": doi,
            "estado": duplicado.estado,
        }

    file_id = str(uuid.uuid4())
    fname = f"{file_id}.pdf"
    path = os.path.join(STORAGE_DIR, fname)
    with open(path, "wb") as f:
        f.write(data)

    # Limpieza y extracción
    titulo = clean(titulo)
    doi = clean(doi)
    auto_title, auto_doi = extract_title_and_doi(path)
    titulo = titulo or auto_title
    doi = doi or auto_doi

    # Reusar artículo si el DOI ya existe en el proyecto
    art_exist = None
    if doi:
        art_exist = db.query(Articulo).filter(
            Articulo.proyecto_id == proyecto_id,
            Articulo.doi == doi
        ).first()

    if art_exist:
        art_id = art_exist.id
    else:
        art_id = str(uuid.uuid4())
        art = Articulo(
            id=art_id,
            proyecto_id=proyecto_id,
            doi=doi,
            titulo=titulo
        )
        db.add(art)
        db.flush()

    estado = EstadoArchivo.extraido if (titulo or doi) else EstadoArchivo.subido
    arc = Archivo(
        id=file_id,
        proyecto_id=proyecto_id,
        articulo_id=art_id,
        nombre=pdf.filename,
        ruta=path,
        hash_sha256=file_hash,
        bytes=len(data),
        estado=estado,
    )
    db.add(arc)
    db.commit()

    return {
        "articulo_id": art_id,
        "archivo_id": file_id,
        "titulo": titulo,
        "doi": doi,
        "estado": estado,
    }
