# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

MYSQL_URI = os.getenv("MYSQL_URI")
engine = create_engine(MYSQL_URI, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()  # ← necesaria para los modelos

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
