import unittest

import _ruta  # noqa: F401
from catalog_matching.matcher import Candidato, Matcher, Producto, enrutar

CATALOGO = [
    Producto("JER-1", "Jeringa desechable 5 ml sin aguja luer lock caja 100 un Vexora"),
    Producto("JER-2", "Jeringa desechable 10 ml sin aguja luer lock caja 100 un Vexora"),
    Producto("JER-3", 'Jeringa desechable 10 ml con aguja 21G x 1 1/2" luer lock caja 100 un Vexora'),
    Producto("JER-4", "Jeringa desechable 10 ml sin aguja luer lock caja 100 un Tralmed"),
    Producto("GEX-1", "Guante de examen nitrilo azul sin polvo talla M caja 100 un Vexora"),
    Producto("GEX-2", "Guante de examen nitrilo azul sin polvo talla L caja 100 un Vexora"),
    Producto("GEX-3", "Guante de examen látex blanco con polvo talla M caja 100 un Brelan"),
    Producto("SFO-1", "Sonda Foley 16 Fr 2 vías silicona Nevisur"),
    Producto("SFO-2", "Sonda Foley 18 Fr 2 vías silicona Nevisur"),
    Producto("TOR-1", 'Tornillo drywall cabeza trompeta #8 1 1/4" negro fosfatado caja 100 un Quilmar'),
]


class TestMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = Matcher(CATALOGO)

    def test_glosa_abreviada_encuentra_el_sku(self):
        self.assertEqual(self.m.buscar("gte nitr T-L s/polvo cj x100")[0].sku, "GEX-2")

    def test_unidades_distintas(self):
        top = self.m.buscar("jer 10cc c/ag 21G x 38mm")[0]
        self.assertEqual(top.sku, "JER-3")

    def test_regla_de_medidas_castiga_conflictos(self):
        candidatos = {c.sku: c for c in self.m.buscar("jeringa 10 cc sin aguja")}
        self.assertLess(candidatos["JER-1"].ajuste_medidas, 0)
        self.assertGreater(candidatos["JER-2"].score, candidatos["JER-1"].score)

    def test_numero_con_N(self):
        self.assertEqual(self.m.buscar("sonda foley N°18 2 vias")[0].sku, "SFO-2")

    def test_errores_de_tipeo(self):
        self.assertEqual(self.m.buscar("tornilo drywal trompeta #8 1 1/4 pulg")[0].sku, "TOR-1")

    def test_sin_reglas_es_la_linea_base(self):
        base = Matcher(CATALOGO, usar_reglas=False)
        self.assertEqual(base.buscar("jeringa 10 cc")[0].ajuste_medidas, 0.0)


class TestEnrutamiento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = Matcher(CATALOGO)

    def test_ganador_claro_se_automatiza(self):
        d = enrutar("q", "x", self.m.buscar("guante examen nitrilo azul sin polvo talla M caja 100 un Vexora"), 0.8, 0.05)
        self.assertEqual((d.ruta, d.sku), ("automatico", "GEX-1"))

    def test_equivalentes_no_bloquean(self):
        # sin marca, JER-2 (Vexora) y JER-4 (Tralmed) cumplen lo pedido: no son rivales
        d = enrutar("q", "x", self.m.buscar("jeringa 10 ml sin aguja luer lock caja 100"), 0.8, 0.05)
        self.assertEqual(d.ruta, "automatico")
        self.assertIn(d.sku, {"JER-2", "JER-4"})
        self.assertGreaterEqual(d.equivalentes, 1)
        sin_agrupar = enrutar("q", "x", self.m.buscar("jeringa 10 ml sin aguja luer lock caja 100"), 0.8, 0.05,
                              agrupar_equivalentes=False)
        self.assertEqual(sin_agrupar.ruta, "revision")

    def test_bajo_umbral_va_a_revision_con_top3(self):
        d = enrutar("q", "x", self.m.buscar("termometro digital axilar"), 0.8, 0.05)
        self.assertEqual(d.ruta, "revision")
        self.assertLessEqual(len(d.candidatos), 3)

    def test_margen_insuficiente(self):
        a = Candidato("A", "a", 0.90, 0.90, firma=frozenset({"a"}))
        b = Candidato("B", "b", 0.88, 0.88, firma=frozenset({"b"}))
        d = enrutar("q", "x", [a, b], 0.8, 0.05)
        self.assertEqual(d.ruta, "revision")
        self.assertIn("margen", d.motivo)

    def test_medida_sin_explicar_no_se_automatiza(self):
        a = Candidato("A", "a", 0.95, 0.95, medidas_sin_explicar=1)
        self.assertEqual(enrutar("q", "x", [a], 0.8, 0.05).ruta, "revision")

    def test_sin_candidatos(self):
        self.assertEqual(enrutar("q", "x", [], 0.8, 0.05).motivo, "sin candidatos")


if __name__ == "__main__":
    unittest.main()
