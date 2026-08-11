# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

load_dotenv()

MYSQL_URI = os.getenv("MYSQL_URI")
engine = create_engine(MYSQL_URI, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base declarativa única de todo el proyecto.

    Antes coexistían dos: esta, creada con `declarative_base()`, y otra
    definida en `app/models/proyecto.py`. Los modelos se repartían entre
    ambas, de modo que el `create_all()` de `main.py` —que opera sobre esta—
    solo conocía la tabla `embedding_doc`. Pese al comentario que decía
    "crea todas las tablas conocidas por los modelos", nunca creó ninguna
    otra: el resto existía únicamente porque se ejecutaba `schema.sql` a
    mano (C-14).
    """
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
