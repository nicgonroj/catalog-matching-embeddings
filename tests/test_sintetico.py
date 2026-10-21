import unittest
from collections import Counter

import _ruta  # noqa: F401
from catalog_matching.sintetico import MARCAS, generar_catalogo, generar_consultas


class TestSintetico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogo = generar_catalogo()
        cls.consultas = generar_consultas(cls.catalogo, n=300, semilla=42)

    def test_tamano_del_catalogo(self):
        self.assertGreater(len(self.catalogo), 9_500)
        skus = [p["sku"] for p in self.catalogo]
        self.assertEqual(len(skus), len(set(skus)))

    def test_determinista(self):
        self.assertEqual(generar_consultas(self.catalogo, n=300, semilla=42), self.consultas)
        self.assertNotEqual(generar_consultas(self.catalogo, n=300, semilla=7), self.consultas)

    def test_etiquetas_consistentes(self):
        skus = {p["sku"] for p in self.catalogo}
        for q in self.consultas:
            if q["sku_correcto"]:
                self.assertIn(q["sku_correcto"], q["skus_validos"])
                self.assertTrue(set(q["skus_validos"]) <= skus)
            else:
                self.assertEqual(q["skus_validos"], [])

    def test_hay_casos_sin_match(self):
        tipos = Counter(q["tipo"] for q in self.consultas)
        self.assertGreater(tipos["sin_match_fuera_catalogo"], 0)
        self.assertGreater(tipos["sin_match_variante_inexistente"], 0)
        self.assertGreater(tipos["match"], 0.8 * len(self.consultas))

    def test_marcas_ficticias(self):
        self.assertTrue({p["marca"] for p in self.catalogo} <= set(MARCAS))


if __name__ == "__main__":
    unittest.main()
