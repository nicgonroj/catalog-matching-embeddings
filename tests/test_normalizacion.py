import unittest

import _ruta  # noqa: F401
from catalog_matching.normalizacion import comparar_medidas, extraer_medidas, normalizar


class TestUnidades(unittest.TestCase):
    def test_cc_y_ml_son_lo_mismo(self):
        self.assertEqual(normalizar("Jeringa 10cc"), normalizar("jeringa 10 ml"))

    def test_litros_a_mililitros(self):
        self.assertIn("1000ml", normalizar("alcohol 1 lt"))
        self.assertIn("1000ml", normalizar("Alcohol etílico 1 L"))

    def test_pulgadas_a_milimetros(self):
        self.assertIn("38mm", normalizar('aguja 21G x 1 1/2"'))
        self.assertIn("38mm", normalizar("aguja 21g 1½ pulg"))
        self.assertIn("12.7mm", normalizar("cinta 1/2 pulgada"))

    def test_coma_decimal_y_porcentaje(self):
        self.assertIn("0.5%", normalizar("Clorhexidina 0,5 %"))
        self.assertIn("70%", normalizar("alcohol 70°"))
        self.assertIn("70%", normalizar("alcohol al 70"))

    def test_french_calibre_y_numero(self):
        self.assertIn("14fr", normalizar("Sonda Foley Fr 14"))
        self.assertIn("14fr", normalizar("sonda CH14"))
        self.assertIn("21g", normalizar("aguja calibre 21"))
        self.assertIn("num18", normalizar("branula N°18"))

    def test_dimensiones(self):
        self.assertIn("7.5x7.5cm", normalizar("Gasa 7,5 x 7,5 cm"))
        self.assertIn("10x10", normalizar("gasa 10x10"))


class TestAbreviaturasYSinonimos(unittest.TestCase):
    def test_glosa_abreviada(self):
        texto = normalizar("gte nitr T-M s/polvo cj x100")
        for token in ("guante", "nitrilo", "talla_m", "sinpolvo", "caja", "100un"):
            self.assertIn(token, texto.split())

    def test_negacion_no_se_pierde(self):
        self.assertIn("sinaguja", normalizar("jeringa sin aguja").split())
        self.assertIn("noesteril", normalizar("gasa no estéril").split())
        self.assertNotIn("esteril", normalizar("gasa no estéril").split())

    def test_sinonimos(self):
        self.assertIn("cateter", normalizar("bránulas 20G").split())
        self.assertIn("golilla", normalizar("arandela plana M8").split())
        self.assertIn("drywall", normalizar("tornillo volcanita").split())
        self.assertEqual(normalizar("tuerca negra"), normalizar("tuerca negro"))

    def test_tallas(self):
        self.assertIn("talla_m", normalizar("guante mediano").split())
        self.assertIn("talla_7.5", normalizar("guante talla 7 1/2").split())
        self.assertIn("talla_xxxl", normalizar("overol XXXL").split())


class TestMedidas(unittest.TestCase):
    def test_extraer(self):
        m = extraer_medidas(normalizar('Jeringa 10 ml con aguja 21G x 1 1/2" caja 100 un'))
        self.assertEqual(m["ml"], {"10"})
        self.assertEqual(m["g"], {"21"})
        self.assertEqual(m["mm"], {"38"})
        self.assertEqual(m["un"], {"100"})

    def test_longitudes_se_comparan_en_mm(self):
        consulta = extraer_medidas(normalizar("cinta 1 pulgada"))
        catalogo = extraer_medidas(normalizar("cinta 2,5 cm x 9,1 m"))
        self.assertEqual(comparar_medidas(consulta, catalogo), (1, 0, 0))

    def test_conflicto(self):
        consulta = extraer_medidas(normalizar("jeringa 10cc"))
        catalogo = extraer_medidas(normalizar("Jeringa 5 ml"))
        self.assertEqual(comparar_medidas(consulta, catalogo), (0, 1, 0))

    def test_tolerancia_de_redondeo(self):
        # 4 1/2" son 114,3 mm; el comprador escribe 115 mm
        consulta = extraer_medidas(normalizar("disco 115 mm"))
        catalogo = extraer_medidas(normalizar('Disco de corte 4 1/2"'))
        self.assertEqual(comparar_medidas(consulta, catalogo), (1, 0, 0))

    def test_medida_sin_explicar(self):
        consulta = extraer_medidas(normalizar("aguja 25G 10 ml"))
        catalogo = extraer_medidas(normalizar("Aguja hipodérmica 25G"))
        self.assertEqual(comparar_medidas(consulta, catalogo), (1, 0, 1))

    def test_numero_suelto_no_castiga(self):
        consulta = extraer_medidas(normalizar("5 cajas sonda foley 18"))
        catalogo = extraer_medidas(normalizar("Sonda Foley 18 Fr"))
        self.assertEqual(comparar_medidas(consulta, catalogo), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
