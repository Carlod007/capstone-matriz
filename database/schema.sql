-- ===========================================
-- Creación de base de datos
-- ===========================================
CREATE DATABASE IF NOT EXISTS capstone
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE capstone;

-- ===========================================
-- TABLA PROYECTO
-- ===========================================
DROP TABLE IF EXISTS proyecto;
CREATE TABLE proyecto (
  id CHAR(36) PRIMARY KEY,
  tema_principal      VARCHAR(200) NOT NULL,
  objetivo            TEXT NOT NULL,
  metodologia_txt     VARCHAR(150) NULL,
  sector_txt          VARCHAR(150) NULL,
  n_articulos_objetivo INT NOT NULL,
  estado_arte_generado TINYINT(1) DEFAULT 0,
  creado_en           DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_proyecto_estado (estado_arte_generado),
  INDEX idx_proyecto_tema (tema_principal)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA ARTICULO
-- ===========================================
DROP TABLE IF EXISTS articulo;
CREATE TABLE articulo (
  id          CHAR(36) PRIMARY KEY,
  proyecto_id CHAR(36) NOT NULL,
  doi         VARCHAR(255) NULL,
  titulo      VARCHAR(500) NULL,
  creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_articulo_proyecto
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  UNIQUE KEY uq_articulo_proy_doi (proyecto_id, doi),
  INDEX idx_articulo_proyecto (proyecto_id)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA ARCHIVO (PDF subido)
-- ===========================================
DROP TABLE IF EXISTS archivo;
CREATE TABLE archivo (
  id          CHAR(36) PRIMARY KEY,
  proyecto_id CHAR(36) NOT NULL,
  articulo_id CHAR(36) NULL,
  nombre      VARCHAR(300) NOT NULL,
  ruta        VARCHAR(500) NOT NULL,
  hash_sha256 CHAR(64) NOT NULL,
  bytes       BIGINT NULL,
  ocr_aplicado TINYINT(1) DEFAULT 0,
  estado      ENUM('pendiente','subido','extraido','ocr','fallido') DEFAULT 'subido',
  creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_archivo_proyecto
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT fk_archivo_articulo
    FOREIGN KEY (articulo_id) REFERENCES articulo(id)
    ON DELETE SET NULL ON UPDATE RESTRICT,
  UNIQUE KEY uq_archivo_hash (hash_sha256),
  INDEX idx_archivo_proyecto (proyecto_id),
  INDEX idx_archivo_estado (estado)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA RUN (ejecución/lote de análisis)
-- ===========================================
DROP TABLE IF EXISTS run;
CREATE TABLE run (
  id            CHAR(36) PRIMARY KEY,
  proyecto_id   CHAR(36) NOT NULL,
  estado        ENUM('creado','en_progreso','completado','fallido') DEFAULT 'creado',
  iniciado_en   DATETIME NULL,
  finalizado_en DATETIME NULL,
  n_items_total INT DEFAULT 0,
  n_items_ok    INT DEFAULT 0,
  tokens_in     BIGINT DEFAULT 0,
  tokens_out    BIGINT DEFAULT 0,
  costo_estimado DECIMAL(10,2) DEFAULT 0.00,
  CONSTRAINT fk_run_proyecto
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_run_proy_estado (proyecto_id, estado)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA RUN_ITEM (progreso por artículo)
-- ===========================================
DROP TABLE IF EXISTS run_item;
CREATE TABLE run_item (
  id          CHAR(36) PRIMARY KEY,
  run_id      CHAR(36) NOT NULL,
  articulo_id CHAR(36) NOT NULL,
  estado      ENUM('pendiente','extraido','ocr','enriquecido','analizado','guardado','fallido') DEFAULT 'pendiente',
  duracion_ms BIGINT NULL,
  error_msg   TEXT NULL,
  creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_run_item_run
    FOREIGN KEY (run_id) REFERENCES run(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT fk_run_item_articulo
    FOREIGN KEY (articulo_id) REFERENCES articulo(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_run_item_run_estado (run_id, estado),
  INDEX idx_run_item_articulo (articulo_id)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA RESULTADO_RESUMEN (resúmenes + métricas)
-- ===========================================
DROP TABLE IF EXISTS resultado_resumen;
CREATE TABLE resultado_resumen (
  id                 CHAR(36)  NOT NULL,
  articulo_id        CHAR(36)  NOT NULL,
  resumen_generado   LONGTEXT  NOT NULL,
  resumen_referencia LONGTEXT  NOT NULL,
  rouge1_prec        VARCHAR(32) DEFAULT NULL,
  rouge1_rec         VARCHAR(32) DEFAULT NULL,
  rouge1_f1          VARCHAR(32) DEFAULT NULL,
  lexical_density    FLOAT NULL,
  created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_resumen_articulo
    FOREIGN KEY (articulo_id) REFERENCES articulo(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_resumen_articulo (articulo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===========================================
-- TABLA RESULTADO_BRECHA
-- ===========================================
DROP TABLE IF EXISTS resultado_brecha;
CREATE TABLE resultado_brecha (
  id               CHAR(36) PRIMARY KEY,
  run_item_id      CHAR(36) NOT NULL,
  tipo_brecha      ENUM('metodológica','temática','teórica','tecnológica','otra') NOT NULL,
  brecha           LONGTEXT NOT NULL,
  oportunidad      LONGTEXT NOT NULL,
  evidencia        LONGTEXT NULL,
  estado_validacion ENUM('pendiente','aceptada','rechazada') DEFAULT 'pendiente',
  rag_hits         JSON NULL,
  sim_promedio     DECIMAL(5,4) DEFAULT 0.0000,
  entropia         DECIMAL(6,3) DEFAULT 0.000,
  val_score        DECIMAL(5,4) DEFAULT 0.0000,
  val_reason       VARCHAR(300) NULL,
  es_duplicada     TINYINT(1) DEFAULT 0,
  dup_de           CHAR(36) NULL,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_brecha_run_item
    FOREIGN KEY (run_item_id) REFERENCES run_item(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_brecha_run_item (run_item_id),
  INDEX idx_brecha_tipo (tipo_brecha),
  INDEX idx_brecha_estado (estado_validacion),
  INDEX idx_brecha_val (estado_validacion, val_score)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA ESTADO_DEL_ARTE (versionado)
-- ===========================================
DROP TABLE IF EXISTS estado_arte;
CREATE TABLE estado_arte (
  id          CHAR(36) PRIMARY KEY,
  proyecto_id CHAR(36) NOT NULL,
  run_id      CHAR(36) NOT NULL,
  version     INT NOT NULL,
  texto       LONGTEXT NOT NULL,
  estado      ENUM('generado','validado') DEFAULT 'generado',
  tokens_in   BIGINT DEFAULT 0,
  tokens_out  BIGINT DEFAULT 0,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_estado_arte_proyecto
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT fk_estado_arte_run
    FOREIGN KEY (run_id) REFERENCES run(id)
    ON DELETE RESTRICT ON UPDATE RESTRICT,
  UNIQUE KEY uq_estado_arte_version (proyecto_id, version),
  INDEX idx_estado_arte_proy (proyecto_id)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA ARTICULO_META (cache Crossref/Scopus)
-- ===========================================
DROP TABLE IF EXISTS articulo_meta;
CREATE TABLE articulo_meta (
  id          CHAR(36) PRIMARY KEY,
  articulo_id CHAR(36) NOT NULL,
  source      ENUM('crossref','scopus') NOT NULL,
  payload_json JSON,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_meta_articulo
    FOREIGN KEY (articulo_id) REFERENCES articulo(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_meta_articulo_source (articulo_id, source)
) ENGINE=InnoDB;

-- ===========================================
-- TABLAS PARA RAG (embeddings)
-- ===========================================
DROP TABLE IF EXISTS embedding_doc;
CREATE TABLE embedding_doc (
  id          CHAR(36) PRIMARY KEY,
  articulo_id CHAR(36) NOT NULL,
  chunk_orden INT NOT NULL,
  texto       LONGTEXT NOT NULL,
  embedding   JSON NOT NULL,
  -- Seccion del articulo a la que pertenece el fragmento: permite exigir
  -- cobertura de metodo, resultados y discusion al recuperar contexto.
  seccion     VARCHAR(24) NULL,
  char_inicio INT NULL,
  char_fin    INT NULL,
  creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_embedding_articulo
    FOREIGN KEY (articulo_id) REFERENCES articulo(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_embedding_articulo (articulo_id),
  INDEX idx_embedding_seccion (articulo_id, seccion)
) ENGINE=InnoDB;

-- ===========================================
-- TABLA METRICA (capa de medicion v2)
-- ===========================================
-- Formato largo: una fila por medicion. La capa de metricas esta en
-- evolucion, y con una columna por indicador cada metrica nueva exigiria
-- una migracion y cada metrica retirada dejaria una columna muerta.
DROP TABLE IF EXISTS metrica;
CREATE TABLE metrica (
  id            CHAR(36) PRIMARY KEY,
  -- referencia_id es polimorfico y no admite clave foranea; se guarda ademas
  -- el proyecto para que al borrarlo desaparezcan sus metricas y la tabla no
  -- acumule filas huerfanas.
  proyecto_id   CHAR(36) NOT NULL,
  ambito        VARCHAR(16) NOT NULL,   -- brecha | articulo | run | proyecto
  referencia_id CHAR(36) NOT NULL,
  codigo        VARCHAR(32) NOT NULL,   -- N1.2, N3.1, N4.1c...
  valor         FLOAT NULL,
  detalle       JSON NULL,
  creado_en     DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_metrica_proyecto
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_metrica_ref (ambito, referencia_id),
  INDEX idx_metrica_codigo (codigo),
  INDEX idx_metrica_proyecto (proyecto_id, codigo)
) ENGINE=InnoDB;

DROP TABLE IF EXISTS rag_log;
CREATE TABLE rag_log (
  id          CHAR(36) PRIMARY KEY,
  -- run_id y articulo_id son opcionales por diseno y no llevan clave
  -- foranea; el proyecto si la lleva, para que el registro se borre con el.
  proyecto_id CHAR(36) NOT NULL,
  run_id      CHAR(36) NULL,
  articulo_id CHAR(36) NULL,
  consulta    TEXT NULL,
  top_k       INT DEFAULT 5,
  scores      JSON NULL,
  creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_rag_log_proyecto
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id)
    ON DELETE CASCADE ON UPDATE RESTRICT,
  INDEX idx_rag_articulo (articulo_id),
  INDEX idx_rag_run (run_id)
) ENGINE=InnoDB;

-- ===========================================
-- NOTA
-- ===========================================
-- Este archivo contiene UNICAMENTE el DDL del esquema.
-- No incluir aqui sentencias de consulta ni de borrado: el archivo
-- esta pensado para ejecutarse completo al preparar una base nueva.
-- Para limpiar datos durante el desarrollo usar un script aparte.