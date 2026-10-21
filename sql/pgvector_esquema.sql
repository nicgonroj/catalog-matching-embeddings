-- Esquema de referencia para guardar el catálogo con embeddings en PostgreSQL + pgvector.
-- El demo no lo necesita: corre en memoria y sin red. Esto muestra cómo se lleva a producción.
--
-- Dimensión: 1536 para text-embedding-3-small de OpenAI. Si cargas los vectores locales de
-- scripts/exportar_pgvector.py --embeddings hashing, usa la dimensión que indiques (256 por defecto).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS catalogo_productos (
    sku                     text PRIMARY KEY,
    descripcion             text        NOT NULL,
    descripcion_normalizada text        NOT NULL,      -- salida de normalizar(): unidades y abreviaturas
    familia                 text,
    marca                   text,
    modelo_embedding        text        NOT NULL,      -- p. ej. 'text-embedding-3-small'
    embedding               vector(1536) NOT NULL,
    actualizado             timestamptz NOT NULL DEFAULT now()
);

-- Índice aproximado (HNSW) por distancia coseno: top-k en milisegundos sobre decenas de miles de SKU.
CREATE INDEX IF NOT EXISTS catalogo_productos_embedding_hnsw
    ON catalogo_productos USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Filtro previo frecuente: restringir por familia antes de ordenar por similitud.
CREATE INDEX IF NOT EXISTS catalogo_productos_familia ON catalogo_productos (familia);

-- Decisiones del motor y resultado de la revisión humana (sirve para medir y re-entrenar umbrales).
CREATE TABLE IF NOT EXISTS decisiones_matching (
    id               bigserial PRIMARY KEY,
    glosa            text        NOT NULL,
    ruta             text        NOT NULL CHECK (ruta IN ('automatico', 'revision')),
    sku_propuesto    text        REFERENCES catalogo_productos (sku),
    score            real        NOT NULL,
    margen           real        NOT NULL,
    motivo           text,
    candidatos       jsonb       NOT NULL,            -- top-3 que vio la persona
    sku_confirmado   text        REFERENCES catalogo_productos (sku),
    revisado_por     text,
    creado           timestamptz NOT NULL DEFAULT now(),
    revisado         timestamptz
);

-- Búsqueda top-k para una glosa: $1 es el embedding de la glosa normalizada.
-- SET hnsw.ef_search = 100;
-- SELECT sku, descripcion, 1 - (embedding <=> $1) AS similitud
-- FROM catalogo_productos
-- ORDER BY embedding <=> $1
-- LIMIT 50;
--
-- Después, en la aplicación: regla de medidas, umbral y margen contra el mejor rival distinguible.
