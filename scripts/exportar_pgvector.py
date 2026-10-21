"""Exporta el catálogo con sus vectores a un archivo SQL listo para cargar en pgvector.

No necesita Postgres: solo escribe el archivo. Para cargarlo:

    psql "$DATABASE_URL" -f output/pgvector_catalogo.sql

Modos:
    --embeddings hashing   vectores locales de dimensión fija, sin red ni claves (por defecto)
    --embeddings openai    text-embedding-3-small vía API (requiere OPENAI_API_KEY)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from catalog_matching.matcher import cargar_catalogo  # noqa: E402
from catalog_matching.normalizacion import normalizar  # noqa: E402


def _sql(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalogo", default="data/catalogo.csv")
    p.add_argument("--embeddings", choices=["hashing", "openai"], default="hashing")
    p.add_argument("--dim", type=int, default=256, help="dimensión del modo hashing")
    p.add_argument("--limite", type=int, default=None, help="exportar solo los primeros N SKU")
    p.add_argument("--lote", type=int, default=500)
    p.add_argument("--salida", default="output/pgvector_catalogo.sql")
    args = p.parse_args()

    productos = cargar_catalogo(args.catalogo)[: args.limite]
    if args.embeddings == "openai":
        from catalog_matching.embeddings import EmbeddingsOpenAI
        emb = EmbeddingsOpenAI(ruta_cache=Path(args.salida).parent / "cache_embeddings.json")
        modelo, dim = emb.modelo, None
    else:
        from catalog_matching.embeddings import EmbeddingsHashing
        emb = EmbeddingsHashing(args.dim)
        modelo, dim = f"hashing-{args.dim}", args.dim

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    esquema = (Path(__file__).resolve().parents[1] / "sql" / "pgvector_esquema.sql").read_text(encoding="utf-8")
    with salida.open("w", encoding="utf-8") as f:
        for i in range(0, len(productos), args.lote):
            lote = productos[i:i + args.lote]
            normalizados = [normalizar(prod.descripcion) for prod in lote]
            vectores = emb.embed(normalizados)
            if i == 0:
                dim = dim or len(vectores[0])
                f.write(esquema.replace("vector(1536)", f"vector({dim})") + "\n")
            f.write("INSERT INTO catalogo_productos (sku, descripcion, descripcion_normalizada, familia, marca, "
                    "modelo_embedding, embedding) VALUES\n")
            filas = []
            for prod, norm, vec in zip(lote, normalizados, vectores):
                literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
                filas.append(f"({_sql(prod.sku)}, {_sql(prod.descripcion)}, {_sql(norm)}, {_sql(prod.familia)}, "
                             f"{_sql(prod.marca)}, {_sql(modelo)}, '{literal}')")
            f.write(",\n".join(filas))
            f.write("\nON CONFLICT (sku) DO UPDATE SET descripcion = EXCLUDED.descripcion, "
                    "descripcion_normalizada = EXCLUDED.descripcion_normalizada, embedding = EXCLUDED.embedding, "
                    "modelo_embedding = EXCLUDED.modelo_embedding, actualizado = now();\n\n")
    print(f"{len(productos)} SKU con vectores de dimensión {dim} ({modelo}) → {salida}")


if __name__ == "__main__":
    main()
