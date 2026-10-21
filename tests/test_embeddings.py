import math
import unittest

import _ruta  # noqa: F401
from catalog_matching.embeddings import EmbeddingsHashing, EmbeddingsOpenAI, RerankerEmbeddings
from catalog_matching.matcher import Matcher, Producto


class TransporteFalso:
    """Simula la API de embeddings: vector según palabras clave, sin red."""

    def __init__(self):
        self.llamadas = 0

    def __call__(self, url, cuerpo, cabeceras):
        self.llamadas += 1
        assert cabeceras["Authorization"] == "Bearer clave-de-prueba"
        datos = []
        for i, texto in enumerate(cuerpo["input"]):
            t = texto.lower()
            datos.append({"index": i, "embedding": [float("guante" in t), float("jeringa" in t), 0.1]})
        return {"data": datos}


class TestEmbeddings(unittest.TestCase):
    def test_openai_con_transporte_falso_y_cache(self):
        transporte = TransporteFalso()
        emb = EmbeddingsOpenAI(api_key="clave-de-prueba", transporte=transporte)
        self.assertEqual(len(emb.embed(["guante", "jeringa", "guante"])), 3)
        emb.embed(["guante"])
        self.assertEqual(transporte.llamadas, 1)   # el segundo pedido sale del caché

    def test_reranker_en_el_matcher(self):
        productos = [Producto("G", "Guante de examen nitrilo"), Producto("J", "Jeringa desechable 10 ml")]
        emb = EmbeddingsOpenAI(api_key="clave-de-prueba", transporte=TransporteFalso())
        m = Matcher(productos, reranker=RerankerEmbeddings(emb))
        self.assertEqual(m.buscar("guante")[0].sku, "G")

    def test_hashing_normalizado_y_determinista(self):
        emb = EmbeddingsHashing(dim=64)
        a, b = emb.embed(["gte nitrilo M", "gte nitrilo M"])
        self.assertEqual(a, b)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in a)), 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
