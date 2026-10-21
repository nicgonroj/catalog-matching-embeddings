"""Vectores densos: embeddings de OpenAI (opcional) y hashing local.

- ``EmbeddingsOpenAI``: llama a ``/v1/embeddings`` con ``urllib`` (sin SDK). Solo se usa si existe
  ``OPENAI_API_KEY``. Guarda un caché en disco para no pagar dos veces por el mismo texto.
- ``RerankerEmbeddings``: reordena los candidatos que entrega el TF-IDF según el coseno de sus
  embeddings. Es la versión de demo de lo que en producción hace pgvector sobre todo el catálogo.
- ``EmbeddingsHashing``: vectores densos de dimensión fija calculados localmente (feature hashing
  de los mismos rasgos del TF-IDF). Sirven para probar la carga en pgvector sin claves.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Callable

from .normalizacion import normalizar
from .vectorizador import rasgos

URL_OPENAI = "https://api.openai.com/v1/embeddings"
Transporte = Callable[[str, dict, dict], dict]


def _post_json(url: str, cuerpo: dict, cabeceras: dict) -> dict:
    datos = json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url, data=datos, headers=cabeceras, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def coseno_denso(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


class EmbeddingsOpenAI:
    def __init__(self, modelo: str | None = None, api_key: str | None = None,
                 transporte: Transporte | None = None, ruta_cache: str | Path | None = None,
                 tamano_lote: int = 256):
        self.modelo = modelo or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta OPENAI_API_KEY. El modo offline no la necesita.")
        self.transporte = transporte or _post_json
        self.tamano_lote = tamano_lote
        self.ruta_cache = Path(ruta_cache) if ruta_cache else None
        self.cache: dict[str, list[float]] = {}
        if self.ruta_cache and self.ruta_cache.exists():
            self.cache = json.loads(self.ruta_cache.read_text(encoding="utf-8"))

    def _clave(self, texto: str) -> str:
        return hashlib.sha1(f"{self.modelo}|{texto}".encode("utf-8")).hexdigest()

    def embed(self, textos: list[str]) -> list[list[float]]:
        faltantes = list(dict.fromkeys(t for t in textos if self._clave(t) not in self.cache))
        for i in range(0, len(faltantes), self.tamano_lote):
            lote = faltantes[i:i + self.tamano_lote]
            resp = self.transporte(URL_OPENAI, {"model": self.modelo, "input": lote},
                                   {"Authorization": f"Bearer {self.api_key}",
                                    "Content-Type": "application/json"})
            for item in sorted(resp["data"], key=lambda d: d["index"]):
                self.cache[self._clave(lote[item["index"]])] = item["embedding"]
            if self.ruta_cache:
                self.ruta_cache.parent.mkdir(parents=True, exist_ok=True)
                self.ruta_cache.write_text(json.dumps(self.cache), encoding="utf-8")
        return [self.cache[self._clave(t)] for t in textos]


class EmbeddingsHashing:
    """Proyección local de los rasgos TF-IDF a ``dim`` dimensiones (feature hashing con signo)."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, textos: list[str]) -> list[list[float]]:
        salida = []
        for texto in textos:
            vec = [0.0] * self.dim
            for rasgo in rasgos(normalizar(texto)):
                h = int.from_bytes(hashlib.md5(rasgo.encode("utf-8")).digest()[:8], "big")
                vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            norma = math.sqrt(sum(v * v for v in vec)) or 1.0
            salida.append([round(v / norma, 6) for v in vec])
        return salida


class RerankerEmbeddings:
    """Similitud por embeddings entre la glosa y cada candidato (cumple ``matcher.Reranker``)."""

    def __init__(self, embedder):
        self.embedder = embedder

    def similitudes(self, consulta: str, descripciones: list[str]) -> list[float]:
        vectores = self.embedder.embed([consulta, *descripciones])
        q = vectores[0]
        return [coseno_denso(q, v) for v in vectores[1:]]
