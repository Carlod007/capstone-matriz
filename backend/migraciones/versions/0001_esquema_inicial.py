"""Esquema inicial

Reproduce el esquema tal y como existe en la base en produccion, no como lo
describian los modelos ni schema.sql: los tres diverguian entre si. Los
identificadores son CHAR(36) y las claves foraneas son las que hay realmente,
incluidas las que solo estaban declaradas en schema.sql.

A partir de aqui Alembic es la unica fuente de verdad del esquema. schema.sql
se conserva como referencia de lectura.

Sobre una base que ya tiene estas tablas no hay que ejecutar esta migracion,
sino marcarla como aplicada:

    alembic stamp 0001

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# Orden de creacion: cada tabla despues de aquellas a las que referencia.
TABLAS = [
    ("proyecto", """
        CREATE TABLE proyecto (
          id CHAR(36) NOT NULL,
          tema_principal VARCHAR(200) NOT NULL,
          objetivo TEXT NOT NULL,
          metodologia_txt VARCHAR(150) DEFAULT NULL,
          sector_txt VARCHAR(150) DEFAULT NULL,
          n_articulos_objetivo INT NOT NULL,
          estado_arte_generado TINYINT(1) DEFAULT 0,
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_proyecto_estado (estado_arte_generado),
          KEY idx_proyecto_tema (tema_principal)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("articulo", """
        CREATE TABLE articulo (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) NOT NULL,
          doi VARCHAR(255) DEFAULT NULL,
          titulo VARCHAR(500) DEFAULT NULL,
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_articulo_proy_doi (proyecto_id, doi),
          KEY idx_articulo_proyecto (proyecto_id),
          CONSTRAINT fk_articulo_proyecto FOREIGN KEY (proyecto_id)
            REFERENCES proyecto (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("archivo", """
        CREATE TABLE archivo (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) NOT NULL,
          articulo_id CHAR(36) DEFAULT NULL,
          nombre VARCHAR(300) NOT NULL,
          ruta VARCHAR(500) NOT NULL,
          hash_sha256 CHAR(64) NOT NULL,
          bytes BIGINT DEFAULT NULL,
          ocr_aplicado TINYINT(1) DEFAULT 0,
          estado ENUM('pendiente','subido','extraido','ocr','fallido') DEFAULT 'subido',
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_archivo_hash (hash_sha256),
          KEY idx_archivo_proyecto (proyecto_id),
          KEY idx_archivo_estado (estado),
          KEY fk_archivo_articulo (articulo_id),
          CONSTRAINT fk_archivo_proyecto FOREIGN KEY (proyecto_id)
            REFERENCES proyecto (id) ON DELETE CASCADE,
          CONSTRAINT fk_archivo_articulo FOREIGN KEY (articulo_id)
            REFERENCES articulo (id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("run", """
        CREATE TABLE run (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) NOT NULL,
          estado ENUM('creado','en_progreso','completado','fallido') DEFAULT 'creado',
          iniciado_en DATETIME DEFAULT NULL,
          finalizado_en DATETIME DEFAULT NULL,
          n_items_total INT DEFAULT 0,
          n_items_ok INT DEFAULT 0,
          tokens_in BIGINT DEFAULT 0,
          tokens_out BIGINT DEFAULT 0,
          costo_estimado DECIMAL(10,2) DEFAULT 0.00,
          PRIMARY KEY (id),
          KEY idx_run_proy_estado (proyecto_id, estado),
          CONSTRAINT fk_run_proyecto FOREIGN KEY (proyecto_id)
            REFERENCES proyecto (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("run_item", """
        CREATE TABLE run_item (
          id CHAR(36) NOT NULL,
          run_id CHAR(36) NOT NULL,
          articulo_id CHAR(36) NOT NULL,
          estado ENUM('pendiente','extraido','ocr','enriquecido','analizado',
                      'guardado','fallido') DEFAULT 'pendiente',
          duracion_ms BIGINT DEFAULT NULL,
          error_msg TEXT,
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_run_item_run_estado (run_id, estado),
          KEY idx_run_item_articulo (articulo_id),
          CONSTRAINT fk_run_item_run FOREIGN KEY (run_id)
            REFERENCES run (id) ON DELETE CASCADE,
          CONSTRAINT fk_run_item_articulo FOREIGN KEY (articulo_id)
            REFERENCES articulo (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("resultado_brecha", """
        CREATE TABLE resultado_brecha (
          id CHAR(36) NOT NULL,
          run_item_id CHAR(36) NOT NULL,
          tipo_brecha ENUM('metodológica','temática','teórica','tecnológica','otra')
            NOT NULL,
          brecha LONGTEXT NOT NULL,
          oportunidad LONGTEXT NOT NULL,
          evidencia LONGTEXT,
          estado_validacion ENUM('pendiente','aceptada','rechazada') DEFAULT 'pendiente',
          rag_hits JSON DEFAULT NULL,
          sim_promedio DECIMAL(5,4) DEFAULT 0.0000,
          entropia DECIMAL(6,3) DEFAULT 0.000,
          val_score DECIMAL(5,4) DEFAULT 0.0000,
          val_reason VARCHAR(300) DEFAULT NULL,
          es_duplicada TINYINT(1) DEFAULT 0,
          dup_de CHAR(36) DEFAULT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_brecha_run_item (run_item_id),
          KEY idx_brecha_tipo (tipo_brecha),
          KEY idx_brecha_estado (estado_validacion),
          KEY idx_brecha_val (estado_validacion, val_score),
          CONSTRAINT fk_brecha_run_item FOREIGN KEY (run_item_id)
            REFERENCES run_item (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("resultado_resumen", """
        CREATE TABLE resultado_resumen (
          id CHAR(36) NOT NULL,
          articulo_id CHAR(36) NOT NULL,
          resumen_generado LONGTEXT NOT NULL,
          resumen_referencia LONGTEXT NOT NULL,
          rouge1_prec VARCHAR(32) DEFAULT NULL,
          rouge1_rec VARCHAR(32) DEFAULT NULL,
          rouge1_f1 VARCHAR(32) DEFAULT NULL,
          lexical_density FLOAT DEFAULT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_resumen_articulo (articulo_id),
          CONSTRAINT fk_resumen_articulo FOREIGN KEY (articulo_id)
            REFERENCES articulo (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("estado_arte", """
        CREATE TABLE estado_arte (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) NOT NULL,
          run_id CHAR(36) NOT NULL,
          version INT NOT NULL,
          texto LONGTEXT NOT NULL,
          estado ENUM('generado','validado') DEFAULT 'generado',
          tokens_in BIGINT DEFAULT 0,
          tokens_out BIGINT DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_estado_arte_version (proyecto_id, version),
          KEY idx_estado_arte_proy (proyecto_id),
          KEY fk_estado_arte_run (run_id),
          CONSTRAINT fk_estado_arte_proyecto FOREIGN KEY (proyecto_id)
            REFERENCES proyecto (id) ON DELETE CASCADE,
          CONSTRAINT fk_estado_arte_run FOREIGN KEY (run_id)
            REFERENCES run (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("articulo_meta", """
        CREATE TABLE articulo_meta (
          id CHAR(36) NOT NULL,
          articulo_id CHAR(36) NOT NULL,
          source ENUM('crossref','scopus') NOT NULL,
          payload_json JSON DEFAULT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_meta_articulo_source (articulo_id, source),
          CONSTRAINT fk_meta_articulo FOREIGN KEY (articulo_id)
            REFERENCES articulo (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("embedding_doc", """
        CREATE TABLE embedding_doc (
          id CHAR(36) NOT NULL,
          articulo_id CHAR(36) NOT NULL,
          chunk_orden INT NOT NULL,
          texto LONGTEXT NOT NULL,
          embedding JSON NOT NULL,
          seccion VARCHAR(24) DEFAULT NULL,
          char_inicio INT DEFAULT NULL,
          char_fin INT DEFAULT NULL,
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_embedding_articulo (articulo_id),
          KEY idx_embedding_seccion (articulo_id, seccion),
          CONSTRAINT fk_embedding_articulo FOREIGN KEY (articulo_id)
            REFERENCES articulo (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("rag_log", """
        CREATE TABLE rag_log (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) NOT NULL,
          run_id CHAR(36) DEFAULT NULL,
          articulo_id CHAR(36) DEFAULT NULL,
          consulta TEXT,
          top_k INT DEFAULT 5,
          scores JSON DEFAULT NULL,
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_rag_articulo (articulo_id),
          KEY idx_rag_run (run_id),
          KEY fk_rag_log_proyecto (proyecto_id),
          CONSTRAINT fk_rag_log_proyecto FOREIGN KEY (proyecto_id)
            REFERENCES proyecto (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("metrica", """
        CREATE TABLE metrica (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) NOT NULL,
          ambito VARCHAR(16) NOT NULL,
          referencia_id CHAR(36) NOT NULL,
          codigo VARCHAR(32) NOT NULL,
          valor FLOAT DEFAULT NULL,
          detalle JSON DEFAULT NULL,
          creado_en DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
          PRIMARY KEY (id),
          KEY idx_metrica_ref (ambito, referencia_id),
          KEY idx_metrica_codigo (codigo),
          KEY idx_metrica_proyecto (proyecto_id, codigo),
          CONSTRAINT fk_metrica_proyecto FOREIGN KEY (proyecto_id)
            REFERENCES proyecto (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
    ("llamada_api", """
        CREATE TABLE llamada_api (
          id CHAR(36) NOT NULL,
          proyecto_id CHAR(36) DEFAULT NULL,
          operacion VARCHAR(16) NOT NULL,
          modelo VARCHAR(64) DEFAULT NULL,
          unidades INT DEFAULT 1,
          exito TINYINT(1) DEFAULT 1,
          motivo TEXT,
          tokens_in INT DEFAULT 0,
          tokens_out INT DEFAULT 0,
          creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY ix_llamada_api_proyecto_id (proyecto_id),
          KEY ix_llamada_api_creado_en (creado_en)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """),
]


def upgrade() -> None:
    for _nombre, ddl in TABLAS:
        op.execute(ddl)


def downgrade() -> None:
    # En orden inverso: no se puede borrar una tabla a la que otra apunta.
    for nombre, _ddl in reversed(TABLAS):
        op.execute("DROP TABLE IF EXISTS %s" % nombre)
