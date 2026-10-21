"""Representación local de textos: TF-IDF de palabras + n-gramas de caracteres.

Es el reemplazo offline de los embeddings: no necesita red ni claves y es determinista.

- Las **palabras** capturan el vocabulario exacto (``nitrilo``, ``10ml``, ``talla_m``).
- Los **n-gramas de caracteres** (3 a 5, dentro de cada palabra) toleran errores de tipeo y
  abreviaturas que las reglas no cubren: «nitirlo» comparte casi todos sus trigramas con «nitrilo».

La búsqueda usa un índice invertido: para cada rasgo de la consulta recorre solo los productos
que lo contienen. Los rasgos muy frecuentes se omiten al generar candidatos (aportan poco y son
caros), pero el puntaje final de cada candidato es el coseno exacto con todos los rasgos.
"""
from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict

Vector = dict[str, float]


def _gramas(tok: str, n_min: int, n_max: int) -> list[str]:
    """N-gramas de caracteres de una palabra, con marcas de inicio y fin: «#gu», «gua», …"""
    marcado = f"#{tok}#"
    return ["c:" + marcado[i:i + n] for n in range(n_min, n_max + 1) for i in range(len(marcado) - n + 1)]


def rasgos(texto: str, n_min: int = 3, n_max: int = 5) -> set[str]:
    """Conjunto de palabras (``w:``) y n-gramas de caracteres (``c:``) de un texto normalizado."""
    salida: set[str] = set()
    for tok in texto.split():
        salida.add("w:" + tok)
        salida.update(_gramas(tok, n_min, n_max))
    return salida


def coseno(a: Vector, b: Vector) -> float:
    """Producto punto de dos vectores dispersos ya normalizados (L2 = 1)."""
    if len(a) > len(b):
        a, b = b, a
    return sum(peso * b.get(rasgo, 0.0) for rasgo, peso in a.items())


class IndiceTfidf:
    def __init__(self, peso_palabra: float = 1.0, peso_char: float = 1.0,
                 max_df_candidatos: float = 0.10, n_candidatos: int = 400, n_min: int = 3, n_max: int = 5,
                 alfa: float = 0.5):
        self.alfa = alfa
        self.n_min, self.n_max = n_min, n_max
        self.peso_palabra = peso_palabra
        self.peso_char = peso_char
        self.max_df_candidatos = max_df_candidatos
        self.n_candidatos = n_candidatos
        self.idf: dict[str, float] = {}
        self.docs: list[Vector] = []
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)

    def _ponderar(self, texto: str) -> Vector:
        """Vector TF-IDF normalizado. Solo usa rasgos conocidos del catálogo.

        Cada palabra aporta una «masa» igual a su IDF, repartida entre el rasgo de palabra y sus
        n-gramas. Así una palabra larga («antiempañante», 30+ n-gramas) no pesa más que una corta
        («M8») solo por tener más letras.
        """
        vec: Vector = defaultdict(float)
        for tok in texto.split():
            palabra = "w:" + tok
            gramas = [g for g in _gramas(tok, self.n_min, self.n_max) if g in self.idf]
            idf_palabra = self.idf.get(palabra)
            if idf_palabra is None and not gramas:
                continue     # palabra sin rasgos en el catálogo: no ayuda a encontrar nada
            masa = idf_palabra if idf_palabra is not None else sum(self.idf[g] for g in gramas) / len(gramas)
            if idf_palabra is not None:
                vec[palabra] += self.peso_palabra * masa
            if gramas:
                pesos = Counter()
                for g in gramas:
                    pesos[g] += self.idf[g]
                norma = math.sqrt(sum(v * v for v in pesos.values()))
                for g, v in pesos.items():
                    vec[g] += self.peso_char * masa * v / norma
        norma = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {r: v / norma for r, v in vec.items()}

    def ajustar(self, textos: list[str]) -> "IndiceTfidf":
        df: Counter = Counter()
        for t in textos:
            df.update(rasgos(t, self.n_min, self.n_max))
        n = len(textos)
        self.idf = {r: math.log((n + 1) / (d + 1)) + 1.0 for r, d in df.items()}
        self._df = df
        self._limite_df = max(1, int(self.max_df_candidatos * n))
        self.docs = [self._ponderar(t) for t in textos]
        self.postings = defaultdict(list)
        for i, vec in enumerate(self.docs):
            for rasgo, peso in vec.items():
                self.postings[rasgo].append((i, peso))
        return self

    def vectorizar(self, texto: str) -> Vector:
        return self._ponderar(texto)

    def similitud(self, q: Vector, doc: Vector) -> float:
        """Mezcla de coseno y cobertura de la consulta.

        El coseno castiga al producto por todo lo que la glosa no menciona (y los compradores omiten
        mucho: marca, presentación, color). La cobertura mide qué parte del peso de la consulta
        explica el producto, sin castigar lo que sobra. La mezcla conserva lo mejor de ambos.
        """
        cobertura = sum(peso * peso for rasgo, peso in q.items() if rasgo in doc)
        return self.alfa * coseno(q, doc) + (1 - self.alfa) * cobertura

    def buscar(self, texto: str, k: int = 10) -> list[tuple[int, float]]:
        """Devuelve los ``k`` documentos más similares como (índice, similitud), de mayor a menor."""
        q = self.vectorizar(texto)
        if not q:
            return []
        acumulado: dict[int, float] = defaultdict(float)
        for rasgo, peso in q.items():
            if self._df[rasgo] > self._limite_df:
                continue
            for doc, peso_doc in self.postings[rasgo]:
                acumulado[doc] += peso * peso_doc
        if len(acumulado) < k:   # consulta hecha solo de rasgos frecuentes: recorrer todo
            for rasgo, peso in q.items():
                for doc, peso_doc in self.postings[rasgo]:
                    acumulado.setdefault(doc, 0.0)
        preliminares = heapq.nlargest(self.n_candidatos, acumulado.items(), key=lambda x: x[1])
        exactos = [(doc, self.similitud(q, self.docs[doc])) for doc, _ in preliminares]
        exactos.sort(key=lambda x: (-x[1], x[0]))
        return exactos[:k]
