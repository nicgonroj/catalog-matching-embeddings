import unittest

import _ruta  # noqa: F401
from catalog_matching.evaluacion import Resultado, curva, decidir, metricas
from catalog_matching.matcher import Candidato


def cand(sku, score, firma):
    return Candidato(sku, sku, score, score, firma=frozenset({firma}))


RESULTADOS = [
    # correcto y claro → automático correcto
    Resultado({"id": "1", "texto": "a", "sku_correcto": "A", "skus_validos": ["A"]},
              [cand("A", 0.95, "a"), cand("B", 0.50, "b")]),
    # claro pero equivocado → error automático
    Resultado({"id": "2", "texto": "b", "sku_correcto": "C", "skus_validos": ["C"]},
              [cand("B", 0.92, "b"), cand("C", 0.60, "c")]),
    # ambiguo → cola, con el correcto en el top-3
    Resultado({"id": "3", "texto": "c", "sku_correcto": "C", "skus_validos": ["C"]},
              [cand("D", 0.90, "d"), cand("C", 0.89, "c"), cand("E", 0.40, "e")]),
    # sin match en catálogo y puntaje bajo → cola
    Resultado({"id": "4", "texto": "d", "sku_correcto": None, "skus_validos": []},
              [cand("A", 0.30, "a")]),
]


class TestMetricas(unittest.TestCase):
    def test_metricas_basicas(self):
        m = metricas(RESULTADOS, decidir(RESULTADOS, 0.8, 0.05))
        self.assertEqual(m["automatizadas"], 2)
        self.assertAlmostEqual(m["tasa_automatizacion"], 0.5)
        self.assertAlmostEqual(m["precision_automatizado"], 0.5)
        self.assertEqual(m["en_revision"], 2)
        self.assertAlmostEqual(m["recall@3_cola"], 1.0)
        self.assertEqual(m["sin_match_en_cola"], 1)
        self.assertAlmostEqual(m["recall@1"], 1 / 3)

    def test_curva_monotona_en_automatizacion(self):
        filas = curva(RESULTADOS, [0.5, 0.9, 0.99], 0.05)
        tasas = [f["tasa_automatizacion"] for f in filas]
        self.assertEqual(tasas, sorted(tasas, reverse=True))


if __name__ == "__main__":
    unittest.main()
