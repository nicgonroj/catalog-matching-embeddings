"""Generador de datos 100 % sintéticos.

1. **Catálogo** (~10.000 SKU): se arma de forma combinatoria a partir de familias de producto
   (guantes, jeringas, sondas, tornillos, cables…) y sus atributos (material, talla, volumen,
   calibre, presentación). Cada combinación la ofrecen una o dos marcas ficticias.
2. **Descripciones de compradores** (~1.000): para un SKU elegido se escribe una glosa como la
   escribiría un comprador real: abreviaturas, unidades distintas (``cc`` en vez de ``ml``,
   milímetros en vez de pulgadas), sinónimos, atributos omitidos, errores de tipeo, mayúsculas y
   ruido («Se solicita…», «urgente»). Cada descripción guarda su SKU correcto.
3. **Casos sin match**: productos que el catálogo no tiene (un termómetro) y variantes que no
   existen de una familia que sí existe (una jeringa de 2 ml). Lo correcto es que no se
   automaticen.

Todas las marcas y textos son inventados. La misma semilla produce siempre los mismos datos.
"""
from __future__ import annotations

import csv
import itertools
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

MARCAS = ["Vexora", "Tralmed", "Cordilix", "Nevisur", "Quilmar", "Brelan", "Sotavia", "Mirvak",
          "Austrel", "Pumaq"]


@dataclass(frozen=True)
class Valor:
    """Un valor de atributo: cómo aparece en el catálogo y cómo lo escriben los compradores."""
    cat: str
    variantes: tuple[str, ...]


def V(cat: str, *variantes: str) -> Valor:
    return Valor(cat, variantes or (cat,))


@dataclass
class Familia:
    codigo: str
    nombre: Valor
    dims: list[tuple[str, list[Valor]]]
    opcionales: set[str] = field(default_factory=set)       # atributos que el comprador suele omitir
    ausentes: dict[str, list[Valor]] = field(default_factory=dict)  # valores que no están en catálogo


def _tallas(*tallas: str) -> list[Valor]:
    vals = []
    for t in tallas:
        if t.replace(",", "").isdigit():
            punto = t.replace(",", ".")
            vals.append(V(f"talla {t}", f"talla {t}", f"talla {punto}", f"T{punto}", f"t-{t}", f"N° {t}"))
        else:
            vals.append(V(f"talla {t}", f"talla {t}", f"T-{t}", t, f"t/{t.lower()}", f"talla {t.lower()}"))
    return vals


_ABREV_PACK = {"caja": "cj", "sobre": "sob", "paquete": "paq", "bolsa": "bls"}


def _pack(prefijo: str, *cantidades: int) -> list[Valor]:
    corto = _ABREV_PACK.get(prefijo, prefijo)
    return [V(f"{prefijo} {n} un", f"{prefijo} {n} un", f"{prefijo} x{n}", f"x {n} unidades", f"c/{n}",
              f"{prefijo} de {n}", f"{corto} {n}") for n in cantidades]


def _ml(*vols: str) -> list[Valor]:
    vals = []
    for v in vols:
        if v.endswith(" L"):
            litros = v[:-2]
            ml = str(int(float(litros.replace(",", ".")) * 1000))
            vals.append(V(v, v, f"{litros} lt", f"{litros} litro", f"{ml} ml", f"{ml}cc"))
        else:
            n = v.split()[0]
            vals.append(V(v, v, f"{n}ml", f"{n}cc", f"{n} cc", f"{n} mL"))
    return vals


def _pulg(texto: str, mm: int) -> Valor:
    """Medida en pulgadas con variantes en mm, como suelen mezclarse en las órdenes de compra."""
    num = texto.rstrip('"')
    return V(texto, texto, f"{num} pulg", f"{mm} mm", f"{num.replace(' 1/2', '½')}\"", f"{num} plg")


FAMILIAS: list[Familia] = [
    # ---------------------------------------------------------------- insumos médicos
    Familia("GEX", V("Guante de examen", "guante examen", "guantes de procedimiento", "gte examen", "gtes",
                     "guantes", "guante procedimiento", "gte. exam", "guantes desechables"),
            [("material", [V("nitrilo", "nitrilo", "nitr", "nitrilo"), V("látex", "latex", "ltx", "látex"),
                           V("vinilo", "vinilo", "vinil")]),
             ("color", [V("azul", "azul", "azules"), V("blanco", "blanco"), V("negro", "negro", "negros")]),
             ("polvo", [V("sin polvo", "sin polvo", "s/polvo", "s/p", "libre de polvo"),
                        V("con polvo", "con polvo", "c/polvo")]),
             ("talla", _tallas("XS", "S", "M", "L", "XL")),
             ("puno", [V("puño estándar", "puño estandar", "puño normal"),
                       V("puño extra largo", "puño largo", "extra largo", "caña larga")]),
             ("pack", _pack("caja", 50, 100, 200))],
            opcionales={"color", "polvo", "puno", "pack"},
            ausentes={"talla": [V("talla XXL", "talla XXL", "XXL", "t-xxl")], "pack": _pack("caja", 500)}),
    Familia("GQX", V("Guante quirúrgico estéril", "guante quirurgico esteril", "gte quir est",
                     "guantes cirugía estériles", "guante qx esteril", "guante esteril", "guantes quirúrgicos"),
            [("material", [V("látex", "latex", "látex natural"), V("nitrilo", "nitrilo"),
                           V("poliisopreno", "poliisopreno", "sintético")]),
             ("talla", _tallas("6", "6,5", "7", "7,5", "8", "8,5")),
             ("polvo", [V("sin polvo", "sin polvo", "s/polvo"), V("con polvo", "con polvo", "c/polvo")]),
             ("pack", [V("caja 50 pares", "caja 50 pares", "cj 50 pares", "x50 pares")])],
            opcionales={"polvo", "pack"},
            ausentes={"talla": _tallas("9")}),
    Familia("JER", V("Jeringa desechable", "jeringa", "jeringas", "jer", "jeringa desechable", "jering. desech",
                     "jeringa hipodermica", "jeringas desech."),
            [("volumen", _ml("1 ml", "3 ml", "5 ml", "10 ml", "20 ml", "60 ml")),
             ("aguja", [V("sin aguja", "sin aguja", "s/aguja", "s/ag"),
                        V('con aguja 21G x 1 1/2"', 'c/aguja 21G x 1 1/2"', "21G x 1½\"", "con aguja 21G x 38mm",
                          "21g 1 1/2 pulg", 'aguja 21G x 1,5"'),
                        V('con aguja 22G x 1 1/2"', 'c/aguja 22G x 1 1/2"', "22G x 38 mm", "22g 1½\""),
                        V('con aguja 23G x 1"', 'c/aguja 23G x 1"', "23G x 25mm", "23g 1 pulg"),
                        V('con aguja 25G x 5/8"', 'c/aguja 25G x 5/8"', "25G x 16 mm", "25g 5/8 pulg")]),
             ("punta", [V("luer lock", "luer lock", "luer-lock", "LL"), V("luer slip", "luer slip", "slip", "LS")]),
             ("pack", _pack("caja", 50, 100))],
            opcionales={"punta", "pack"},
            ausentes={"volumen": _ml("2 ml", "30 ml"),
                      "aguja": [V('con aguja 18G x 1 1/2"', 'c/aguja 18G x 1 1/2"', "18G x 38mm")]}),
    Familia("AGU", V("Aguja hipodérmica", "aguja hipodermica", "aguja", "ag hipodérmica", "agujas desechables",
                     "aguja desechable"),
            [("calibre", [V(f"{g}G", f"{g}G", f"{g} G", f"calibre {g}", f"{g}g") for g in (18, 20, 21, 22, 23, 25, 26, 27)]),
             ("largo", [_pulg('1/2"', 13), _pulg('5/8"', 16), _pulg('1"', 25), _pulg('1 1/2"', 38)]),
             ("pack", _pack("caja", 50, 100))],
            opcionales={"pack"},
            ausentes={"calibre": [V("30G", "30G", "calibre 30")], "largo": [_pulg('2"', 51)]}),
    Familia("CIV", V("Catéter intravenoso periférico", "cateter iv", "bránula", "branula", "cateter venoso periferico",
                     "cat. iv", "catéter intravenoso", "branulas"),
            [("calibre", [V(f"{g}G", f"{g}G", f"N°{g}", f"calibre {g}", f"{g} G") for g in (14, 16, 18, 20, 22, 24)]),
             ("aletas", [V("con aletas", "con aletas", "c/aletas"), V("sin aletas", "sin aletas", "s/aletas")]),
             ("sistema", [V("de seguridad", "de seguridad", "seguridad", "c/ sistema seguridad"),
                          V("convencional", "convencional", "estándar")]),
             ("pack", _pack("caja", 50))],
            opcionales={"aletas", "pack"},
            ausentes={"calibre": [V("26G", "26G", "N°26")]}),
    Familia("TET", V("Tubo endotraqueal", "tubo endotraqueal", "tubo ET", "TET", "tubo endotraq."),
            [("diametro", [V(f"{d} mm", f"{d} mm", f"N° {d}", f"{d.replace(',', '.')}mm", f"DI {d}")
                           for d in ("3,0", "3,5", "4,0", "4,5", "5,0", "5,5", "6,0", "6,5", "7,0", "7,5", "8,0", "8,5", "9,0")]),
             ("balon", [V("con balón", "con balon", "c/cuff", "con cuff"), V("sin balón", "sin balon", "s/cuff", "sin cuff")]),
             ("tipo", [V("estándar", "estandar", "normal"), V("reforzado", "reforzado", "anillado")])],
            opcionales={"tipo"},
            ausentes={"diametro": [V("10,0 mm", "10 mm", "N° 10")]}),
    Familia("GAS", V("Gasa", "gasa", "gasas", "compresa de gasa", "gasa tejida"),
            [("medida", [V(f"{d} x {d} cm", f"{d}x{d} cm", f"{d}x{d}", f"{d} cm x {d} cm", f"{d}x{d}cm")
                         for d in ("5", "7,5", "10")]),
             ("pliegues", [V(f"{p} pliegues", f"{p} pliegues", f"{p} capas", f"{p} dobleces") for p in (8, 12, 16)]),
             ("esterilidad", [V("estéril", "esteril", "est.", "estéril"), V("no estéril", "no esteril", "no est")]),
             ("pack", _pack("sobre", 2, 5) + _pack("paquete", 100))],
            opcionales={"pliegues", "pack"},
            ausentes={"medida": [V("20 x 20 cm", "20x20 cm", "20x20")]}),
    Familia("VEN", V("Venda elástica", "venda elastica", "venda", "vendaje elástico", "venda elast"),
            [("ancho", [V(f"{a} cm", f"{a} cm", f"{a}cm", f"{a} cms") for a in (5, 7, 10, 12, 15)]),
             ("largo", [V("4,5 m", "4,5 m", "4.5 mts", "4,5 metros"), V("5 m", "5 m", "5 mts", "5 metros")]),
             ("tejido", [V("tejida", "tejida"), V("cohesiva", "cohesiva", "autoadherente")])],
            opcionales={"largo"},
            ausentes={"ancho": [V("20 cm", "20 cm", "20cm")]}),
    Familia("CIN", V("Cinta adhesiva médica", "cinta adhesiva", "cinta", "tela adhesiva", "cta adh", "cinta medica"),
            [("tipo", [V("microporosa", "microporosa", "micro", "microp"), V("seda", "seda", "de seda"),
                       V("transparente", "transparente", "transp")]),
             ("ancho", [V("1,25 cm", "1,25 cm", "1.25cm", "1/2 pulgada"), V("2,5 cm", "2,5 cm", "2.5cm", "1 pulgada"),
                        V("5 cm", "5 cm", "5cm", "2 pulgadas"), V("7,5 cm", "7,5 cm", "7.5 cm", "3 pulgadas")]),
             ("largo", [V("5 m", "5 m", "5 mts"), V("9,1 m", "9,1 m", "9.1 mts", "9 m")])],
            opcionales={"largo"}),
    Familia("MAS", V("Mascarilla", "mascarilla", "mascarillas", "tapabocas", "masc.", "mascara"),
            [("tipo", [V("quirúrgica 3 pliegues", "quirurgica 3 pliegues", "3 pliegues", "quirurgica tricapa",
                         "qx 3 capas"),
                       V("N95", "N95", "n-95", "N 95"), V("KN95", "KN95", "kn-95")]),
             ("color", [V("azul", "azul", "celeste"), V("blanca", "blanca"), V("negra", "negra")]),
             ("sujecion", [V("con elástico", "con elastico", "elasticos"), V("con amarras", "amarras", "tiras")]),
             ("pack", _pack("caja", 10, 50))],
            opcionales={"color", "sujecion", "pack"}),
    Familia("ALC", V("Alcohol", "alcohol", "alc.", "alcohol"),
            [("tipo", [V("etílico", "etilico", "etílico", "etil."), V("isopropílico", "isopropilico", "isoprop.", "IPA")]),
             ("concentracion", [V(f"{c}%", f"{c}%", f"{c} %", f"{c}°", f"al {c}") for c in (70, 96)]),
             ("volumen", _ml("250 ml", "500 ml", "1 L", "5 L"))],
            opcionales={"tipo"},
            ausentes={"volumen": _ml("2 L")}),
    Familia("CLX", V("Clorhexidina", "clorhexidina", "clorhex.", "CHG", "clorhexidina solucion"),
            [("concentracion", [V(f"{c}%", f"{c}%", f"{c} %", f"al {c}") for c in ("0,5", "2", "4")]),
             ("tipo", [V("jabonosa", "jabonosa", "jabón"), V("acuosa", "acuosa"), V("alcohólica", "alcoholica")]),
             ("volumen", _ml("100 ml", "500 ml", "1 L"))]),
    Familia("SFO", V("Sonda Foley", "sonda foley", "foley", "sonda vesical foley", "snd foley", "sondas foley"),
            [("french", [V(f"{f} Fr", f"{f} Fr", f"{f}fr", f"Fr {f}", f"N°{f}", f"{f} french", f"CH{f}")
                         for f in (8, 10, 12, 14, 16, 18, 20, 22, 24)]),
             ("vias", [V("2 vías", "2 vias", "dos vías", "2 vías"), V("3 vías", "3 vias", "tres vias")]),
             ("material", [V("látex siliconado", "latex siliconado", "látex silic."),
                           V("silicona", "silicona", "100% silicona", "silicon")])],
            opcionales={"material"},
            ausentes={"french": [V("26 Fr", "26 Fr", "26fr", "CH26")]}),
    Familia("APO", V("Apósito transparente", "aposito transparente", "apósito film", "aposito adhesivo transparente"),
            [("medida", [V(f"{a} x {b} cm", f"{a}x{b}", f"{a}x{b} cm", f"{a} x {b}cm") for a, b in ((6, 7), (10, 12), (15, 20))]),
             ("borde", [V("con borde", "con borde", "c/borde"), V("sin borde", "sin borde", "s/borde")]),
             ("pack", _pack("caja", 50, 100))],
            opcionales={"borde", "pack"}),
    Familia("ECG", V("Electrodo ECG", "electrodo ecg", "electrodos", "electrodo monitoreo", "electr. ecg"),
            [("paciente", [V("adulto", "adulto", "adultos"), V("pediátrico", "pediatrico", "ped.", "infantil")]),
             ("material", [V("foam", "foam", "espuma"), V("tela", "tela")]),
             ("pack", _pack("bolsa", 50, 100))],
            opcionales={"material", "pack"}),
    Familia("SUT", V("Sutura", "sutura", "hilo sutura", "sut.", "suturas"),
            [("material", [V("nylon", "nylon", "nailon", "monofilamento nylon"), V("seda", "seda", "seda trenzada"),
                           V("polipropileno", "polipropileno"), V("ácido poliglicólico", "acido poliglicolico", "PGA"),
                           V("poliglactina", "poliglactina", "absorbible trenzada")]),
             ("calibre", [V(f"{c}-0", f"{c}-0", f"{c}/0") for c in (6, 5, 4, 3, 2)]),
             ("aguja", [V("aguja 3/8 círculo 19 mm", "aguja 3/8 19mm", "ag 3/8 c 19mm"),
                        V("aguja 3/8 círculo 24 mm", "aguja 3/8 24mm", "ag 3/8 c 24 mm"),
                        V("aguja 1/2 círculo 26 mm", "aguja 1/2 26mm", "ag 1/2 circ 26 mm"),
                        V("aguja 1/2 círculo 36 mm", "aguja 1/2 36mm", "ag 1/2 c 36mm")]),
             ("hebra", [V("hebra 45 cm", "45 cm", "hebra 45cm"), V("hebra 75 cm", "75 cm", "hebra 75cm")])],
            opcionales={"hebra"},
            ausentes={"calibre": [V("7-0", "7-0", "7/0")]}),
    # ---------------------------------------------------------------- insumos industriales
    Familia("GSE", V("Guante de seguridad", "guante seguridad", "guantes de trabajo", "gte seg", "guante industrial"),
            [("material", [V("recubierto nitrilo", "nitrilo", "palma nitrilo", "recubierto de nitrilo"),
                           V("poliuretano", "poliuretano", "PU", "palma PU"),
                           V("cuero descarne", "cuero", "descarne", "cuero descarne"),
                           V("anticorte nivel 3", "anticorte nivel 3", "anticorte n3"),
                           V("anticorte nivel 5", "anticorte nivel 5", "anticorte n5")]),
             ("talla", _tallas("7", "8", "9", "10", "11")),
             ("pack", [V("par", "par", "1 par"), V("pack 12 pares", "docena", "12 pares", "pack x12")])],
            opcionales={"pack"},
            ausentes={"talla": _tallas("12")}),
    Familia("LEN", V("Lente de seguridad", "lentes seguridad", "antiparras", "gafas de seguridad", "lente seg"),
            [("mica", [V("mica clara", "claro", "transparente", "mica clara"), V("mica oscura", "oscuro", "mica oscura"),
                       V("mica ámbar", "ambar", "amarillo"), V("mica espejada", "espejado", "espejada")]),
             ("tratamiento", [V("antiempañante", "antiempañante", "anti-empañante", "antifog"),
                              V("estándar", "estandar", "normal")])],
            opcionales={"tratamiento"}),
    Familia("PAU", V("Protector auditivo", "protector auditivo", "tapón auditivo", "fono auditivo"),
            [("tipo", [V("tapón espuma", "tapon espuma", "tapones de oido espuma"), V("tapón silicona", "tapon silicona"),
                       V("tipo fono", "fono", "tipo orejera")]),
             ("nrr", [V(f"NRR {n} dB", f"NRR {n}", f"{n} dB", f"nrr{n}") for n in (25, 29, 33)])],
            opcionales={"nrr"}),
    Familia("TOR", V("Tornillo", "tornillo", "tornillos", "torn.", "tornillo acero"),
            [("tipo", [V("autoperforante punta broca", "autoperforante", "autop. punta broca", "punta broca"),
                       V("autorroscante", "autorroscante", "autorrosc."), V("drywall", "drywall", "volcanita"),
                       V("para madera", "madera", "p/madera")]),
             ("cabeza", [V("cabeza hexagonal", "cab hex", "hexagonal", "cabeza hex"),
                         V("cabeza lenteja", "lenteja", "cab lenteja"), V("cabeza plana", "plana", "cab. plana"),
                         V("cabeza trompeta", "trompeta", "cab trompeta")]),
             ("diametro", [V(f"#{n}", f"#{n}", f"nro {n}", f"# {n}", f"N°{n}") for n in (6, 8, 10, 12, 14)]),
             ("largo", [_pulg('1/2"', 13), _pulg('3/4"', 19), _pulg('1"', 25), _pulg('1 1/4"', 32),
                        _pulg('1 1/2"', 38), _pulg('2"', 51), _pulg('2 1/2"', 64), _pulg('3"', 76)]),
             ("acabado", [V("zincado", "zincado", "galvanizado", "zinc"), V("negro fosfatado", "negro", "fosfatado"),
                          V("bicromatado", "bicromatado")]),
             ("pack", _pack("caja", 100, 500))],
            opcionales={"cabeza", "acabado", "pack"},
            ausentes={"largo": [_pulg('4"', 102)]}),
    Familia("PER", V("Perno hexagonal", "perno hex", "perno", "pernos cabeza hexagonal", "perno cab. hexagonal"),
            [("diametro", [V(f"M{d}", f"M{d}", f"m {d}", f"M-{d}", f"m{d}") for d in (6, 8, 10, 12, 14, 16, 20)]),
             ("largo", [V(f"x {l} mm", f"x {l} mm", f"{l}mm", f"largo {l} mm", f"{l / 10:g} cm".replace(".", ","))
                        for l in (20, 30, 40, 50, 60, 70, 80, 100, 120)]),
             ("grado", [V(f"grado {g}", f"grado {g}", f"gr {g}", g) for g in ("5.8", "8.8", "10.9")]),
             ("acabado", [V("zincado", "zincado", "galvanizado"), V("negro", "negro"), V("inoxidable", "inox", "acero inoxidable")]),
             ("hilo", [V("hilo grueso", "hilo grueso", "paso normal"), V("hilo fino", "hilo fino", "paso fino")])],
            opcionales={"grado", "acabado", "hilo"},
            ausentes={"diametro": [V("M24", "M24", "m 24")]}),
    Familia("TUE", V("Tuerca", "tuerca", "tuercas"),
            [("tipo", [V("hexagonal", "hexagonal", "hex"), V("autoblocante", "autoblocante", "c/nylon", "seguridad"),
                       V("mariposa", "mariposa")]),
             ("diametro", [V(f"M{d}", f"M{d}", f"m {d}", f"M-{d}") for d in (4, 5, 6, 8, 10, 12, 16, 20)]),
             ("acabado", [V("zincado", "zincado", "galvanizada"), V("negro", "negra"), V("inoxidable", "inox")]),
             ("pack", _pack("caja", 100))],
            opcionales={"acabado", "pack"}),
    Familia("GOL", V("Golilla", "golilla", "arandela", "golillas", "arandelas"),
            [("tipo", [V("plana", "plana"), V("de presión", "presion", "de presión"), V("estrella", "estrella", "dentada")]),
             ("diametro", [V(f"M{d}", f"M{d}", f"m {d}", f"para perno {d} mm") for d in (4, 5, 6, 8, 10, 12, 16, 20)]),
             ("acabado", [V("zincada", "zincado", "galvanizada"), V("negra", "negra"), V("inoxidable", "inox")]),
             ("pack", _pack("caja", 100))],
            opcionales={"acabado", "pack"}),
    Familia("DIS", V("Disco de corte", "disco corte", "disco", "disco de corte abrasivo", "disco p/ corte"),
            [("diametro", [_pulg('4 1/2"', 115), _pulg('7"', 180), _pulg('9"', 230)]),
             ("espesor", [V(f"espesor {e} mm", f"{e} mm", f"{e.replace(',', '.')}mm", f"esp {e} mm")
                          for e in ("1,0", "1,6", "2,5", "3,2")]),
             ("material", [V("para metal", "metal", "p/metal", "fierro"), V("para acero inoxidable", "inox", "acero inox"),
                           V("para concreto", "concreto", "piedra", "hormigón"), V("para aluminio", "aluminio")]),
             ("pack", _pack("caja", 25, 50))],
            opcionales={"pack"},
            ausentes={"diametro": [_pulg('14"', 355)]}),
    Familia("BRO", V("Broca", "broca", "brocas", "broca acero"),
            [("material", [V("HSS para metal", "hss", "p/metal", "acero rapido"), V("para concreto", "concreto", "widia"),
                           V("para madera", "madera", "p/madera")]),
             ("diametro", [V(f"{d} mm", f"{d} mm", f"{d}mm", f"{d.replace(',', '.')} mm")
                           for d in ("3", "4", "5", "6", "6,5", "8", "10", "12", "14")])]),
    Familia("CAB", V("Cable eléctrico", "cable", "conductor", "cable electrico", "cbl"),
            [("seccion", [V(f"{s} mm²", f"{s} mm2", f"{s.replace(',', '.')}mm2", f"{s} mm cuadrados")
                          for s in ("1,5", "2,5", "4", "6", "10", "16")]),
             ("tipo", [V("THHN", "THHN", "thhn"), V("NYA", "NYA", "nya"), V("flexible", "flexible", "flex", "multifilar"),
                       V("libre de halógenos", "libre halogenos", "LH")]),
             ("color", [V(c, c) for c in ("rojo", "negro", "azul", "blanco", "verde", "amarillo")]),
             ("rollo", [V("rollo 100 m", "rollo 100 mts", "x 100 m", "100 metros"),
                        V("rollo 50 m", "rollo 50 mts", "x 50 m", "50 metros")])],
            opcionales={"rollo"}),
    Familia("PVC", V("Tubo PVC", "tubo pvc", "cañería pvc", "tuberia pvc", "tubo de pvc"),
            [("diametro", [V(f"{d} mm", f"{d} mm", f"{d}mm", f"diam {d}") for d in (20, 25, 32, 40, 50, 63, 75, 90, 110)]),
             ("clase", [V(f"clase {c}", f"clase {c}", f"c-{c}", f"cl {c}") for c in (4, 6, 10)]),
             ("largo", [V("tira 3 m", "3 m", "tira 3 mts"), V("tira 6 m", "6 m", "tira 6 mts", "6 metros")]),
             ("uso", [V("hidráulico", "hidraulico", "presión"), V("sanitario", "sanitario", "desagüe")])],
            opcionales={"clase", "largo"},
            ausentes={"diametro": [V("160 mm", "160 mm", "160mm")]}),
    Familia("ABR", V("Abrazadera", "abrazadera", "abrazaderas", "abrazadera sinfín", "abraz."),
            [("rango", [V(f"{a}-{b} mm", f"{a}-{b} mm", f"{a} a {b} mm", f"{a}-{b}mm")
                        for a, b in ((8, 12), (10, 16), (12, 20), (16, 25), (20, 32), (25, 40), (32, 50), (40, 60))]),
             ("material", [V("acero inoxidable", "inox", "acero inox"), V("acero zincado", "zincada", "galvanizada")]),
             ("banda", [V("banda 9 mm", "banda 9mm", "9 mm"), V("banda 12 mm", "banda 12mm", "12 mm")])],
            opcionales={"banda"}),
    Familia("EMB", V("Cinta de embalaje", "cinta embalaje", "cinta para embalar", "cinta packing", "cta embalaje"),
            [("ancho", [V("48 mm", "48 mm", "48mm", "4,8 cm"), V("72 mm", "72 mm", "72mm", "7,2 cm")]),
             ("largo", [V(f"{l} m", f"{l} m", f"{l} mts", f"{l} metros") for l in (40, 100, 150)]),
             ("color", [V("transparente", "transparente", "transp"), V("café", "cafe", "marron"), V("blanca", "blanca")]),
             ("pack", [V("unidad", "unidad", "un"), V("pack 6 un", "pack x6", "6 un", "paquete 6 rollos")])],
            opcionales={"pack"}),
    Familia("BOL", V("Bolsa de basura", "bolsa basura", "bolsas de residuos", "bolsa residuo", "bolsas basura"),
            [("medida", [V(f"{a} x {b} cm", f"{a}x{b}", f"{a}x{b} cm", f"{a} x {b}cm") for a, b in ((50, 70), (70, 90), (80, 110), (110, 130))]),
             ("color", [V(c, c) for c in ("negra", "verde", "amarilla", "roja")]),
             ("espesor", [V(f"{e} micrones", f"{e} micrones", f"{e} mic", f"{e} micras") for e in (40, 60, 80)]),
             ("pack", _pack("paquete", 10, 100))],
            opcionales={"espesor", "pack"}),
    Familia("ELS", V("Electrodo de soldadura", "electrodo soldar", "soldadura", "electrodo", "varilla soldadura"),
            [("tipo", [V(f"E{t}", f"E{t}", t, f"E-{t}") for t in ("6011", "6013", "7018", "308L")]),
             ("diametro", [V("2,5 mm", "2,5 mm", "3/32\""), V("3,2 mm", "3,2 mm", "1/8\"", "3.2mm"),
                           V("4,0 mm", "4 mm", "5/32\"", "4.0mm")]),
             ("peso", [V(f"caja {p} kg", f"{p} kg", f"{p}kg", f"{p} kilos", f"caja {p} kg") for p in (1, 5, 20)])],
            opcionales={"peso"}),
    Familia("OVE", V("Overol desechable", "overol", "buzo desechable", "overol desech.", "mameluco desechable"),
            [("talla", _tallas("S", "M", "L", "XL", "XXL")),
             ("material", [V("polipropileno", "polipropileno", "PP"), V("laminado microporoso", "laminado", "microporoso")])],
            ausentes={"talla": [V("talla XXXL", "talla XXXL", "XXXL")]}),
]

# Productos que el catálogo no tiene: deben terminar en revisión humana, nunca automatizados.
FUERA_DE_CATALOGO = [
    "Termómetro digital axilar", "Bisturí desechable N°{n}", "Hoja de bisturí N°{n} caja 100 un",
    "Esfigmomanómetro aneroide adulto", "Estetoscopio doble campana", "Silla de ruedas estándar",
    "Tóner impresora láser negro", "Resma papel carta", "Café en grano 1 kg", "Pilas alcalinas AA pack 4",
    "Cloro gel 900 ml", "Papel higiénico doble hoja 50 m", "Taladro percutor 800 W",
    "Escalera tijera aluminio 6 peldaños", "Extintor PQS 6 kg", "Candado de bronce 40 mm",
    "Llave de paso 3 vías", "Bajada de suero macrogotero", "Oxímetro de pulso de dedo",
    "Martillo carpintero 16 oz", "Silicona selladora transparente 280 ml", "Pañal adulto talla M paquete 20 un",
    "Guante de jardinería talla 9", "Jabón líquido 1 L", "Cinta métrica 5 m",
]

PREFIJOS = ["Se solicita ", "Compra de ", "Adquisición de ", "Req: ", "Solicito ", "Insumo: ", "{q} cajas de ",
            "{q} ", "Cant. {q} - "]
SUFIJOS = [" para pabellón", " urgente", " según muestra", " entrega en bodega", " (ver especificaciones)",
           " o similar", " calidad hospitalaria", " - stock crítico", " uso diario"]


def generar_catalogo(semilla: int = 2026) -> list[dict]:
    """Combina atributos por familia; cada combinación la venden una o dos marcas."""
    rng = random.Random(semilla)
    productos = []
    for fam in FAMILIAS:
        marcas_fam = rng.sample(MARCAS, 3)
        nombres = [d for d, _ in fam.dims]
        contador = 0
        for combo in itertools.product(*(vals for _, vals in fam.dims)):
            n_marcas = 1 if rng.random() < 0.60 else 2
            for marca in rng.sample(marcas_fam, n_marcas):
                contador += 1
                atributos = {d: v.cat for d, v in zip(nombres, combo)}
                productos.append({
                    "sku": f"{fam.codigo}-{contador:05d}",
                    "descripcion": " ".join([fam.nombre.cat, *atributos.values(), marca]),
                    "familia": fam.codigo,
                    "marca": marca,
                    "atributos": atributos,
                })
    return productos


def _typo(palabra: str, rng: random.Random) -> str:
    """Un error de tipeo realista: letras cambiadas, faltantes, repetidas o vecinas en el teclado."""
    i = rng.randrange(1, len(palabra) - 1)
    op = rng.choice(["swap", "del", "dup", "vecina"])
    if op == "swap":
        return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]
    if op == "del":
        return palabra[:i] + palabra[i + 1:]
    if op == "dup":
        return palabra[:i] + palabra[i] + palabra[i:]
    vecinas = {"a": "s", "e": "r", "i": "o", "o": "p", "n": "m", "r": "t", "t": "y", "l": "k", "s": "d", "u": "y"}
    return palabra[:i] + vecinas.get(palabra[i], palabra[i]) + palabra[i + 1:]


def _ensuciar(partes: list[str], rng: random.Random, etiquetas: list[str]) -> str:
    """Aplica el ruido típico de una glosa escrita a mano."""
    if rng.random() < 0.3:
        cabeza, resto = partes[:1], partes[1:]
        rng.shuffle(resto)
        partes = cabeza + resto
        etiquetas.append("orden_cambiado")
    palabras = " ".join(partes).split()
    candidatas = [i for i, p in enumerate(palabras) if p.isalpha() and len(p) >= 5]
    n_typos = (rng.random() < 0.35) + (rng.random() < 0.10)
    for _ in range(n_typos):
        if candidatas:
            i = rng.choice(candidatas)
            palabras[i] = _typo(palabras[i], rng)
            etiquetas.append("typo")
    texto = " ".join(palabras)
    if rng.random() < 0.4:
        texto = rng.choice(PREFIJOS).format(q=rng.choice([2, 5, 10, 20, 50, 100, 300])) + texto
        etiquetas.append("prefijo")
    if rng.random() < 0.25:
        texto += rng.choice(SUFIJOS)
        etiquetas.append("sufijo")
    r = rng.random()
    if r < 0.25:
        texto = texto.upper()
    elif r < 0.6:
        texto = texto.lower()
    return texto


def _describir(fam: Familia, atributos: dict[str, Valor], marca: str | None, rng: random.Random,
               etiquetas: list[str]) -> str:
    partes = [rng.choice(fam.nombre.variantes)]
    for dim, valor in atributos.items():
        if dim in fam.opcionales and rng.random() < 0.3:
            etiquetas.append(f"omite_{dim}")
            continue
        variante = rng.choice(valor.variantes)
        if variante != valor.cat:
            etiquetas.append("variante")
        partes.append(variante)
    if marca and rng.random() < 0.5:
        partes.append(rng.choice([marca, marca.lower(), marca.upper(), f"marca {marca}"]))
        etiquetas.append("con_marca")
    return _ensuciar(partes, rng, etiquetas)


def generar_consultas(catalogo: list[dict], n: int = 1000, semilla: int = 42,
                      tasa_fuera: float = 0.05, tasa_variante_ausente: float = 0.07) -> list[dict]:
    """Descripciones de compradores con su SKU correcto (``None`` si no existe en el catálogo)."""
    rng = random.Random(semilla)
    por_familia: dict[str, list[dict]] = {}
    for p in catalogo:
        por_familia.setdefault(p["familia"], []).append(p)
    fam_por_codigo = {f.codigo: f for f in FAMILIAS}
    con_ausentes = [f for f in FAMILIAS if f.ausentes]
    consultas = []
    for i in range(n):
        etiquetas: list[str] = []
        r = rng.random()
        if r < tasa_fuera:
            plantilla = rng.choice(FUERA_DE_CATALOGO)
            texto = _ensuciar([plantilla.format(n=rng.choice([11, 15, 20, 23]))], rng, etiquetas)
            sku, tipo = None, "sin_match_fuera_catalogo"
        elif r < tasa_fuera + tasa_variante_ausente:
            fam = rng.choice(con_ausentes)
            producto = rng.choice(por_familia[fam.codigo])
            atributos = _valores(fam, producto)
            dim = rng.choice(list(fam.ausentes))
            atributos[dim] = rng.choice(fam.ausentes[dim])
            fam_sin_omitir = Familia(fam.codigo, fam.nombre, fam.dims, fam.opcionales - {dim}, fam.ausentes)
            texto = _describir(fam_sin_omitir, atributos, producto["marca"], rng, etiquetas)
            sku, tipo = None, "sin_match_variante_inexistente"
        else:
            fam = fam_por_codigo[rng.choice(list(por_familia))]   # demanda pareja entre familias
            producto = rng.choice(por_familia[fam.codigo])
            texto = _describir(fam, _valores(fam, producto), producto["marca"], rng, etiquetas)
            sku, tipo = producto["sku"], "match"
        validos = _skus_validos(producto, por_familia, etiquetas) if sku else []
        consultas.append({"id": f"Q{i + 1:04d}", "texto": texto, "sku_correcto": sku, "skus_validos": validos,
                          "tipo": tipo, "perturbaciones": sorted(set(etiquetas))})
    return consultas


def _skus_validos(producto: dict, por_familia: dict[str, list[dict]], etiquetas: list[str]) -> list[str]:
    """SKUs que cumplen todo lo que el comprador escribió.

    Si la glosa no dice la marca ni la presentación, cualquier SKU de la misma familia que coincida
    en los atributos mencionados es una respuesta correcta. El SKU de origen siempre está incluido.
    """
    omitidos = {e.removeprefix("omite_") for e in etiquetas if e.startswith("omite_")}
    con_marca = "con_marca" in etiquetas
    return [p["sku"] for p in por_familia[producto["familia"]]
            if all(p["atributos"][d] == v for d, v in producto["atributos"].items() if d not in omitidos)
            and (not con_marca or p["marca"] == producto["marca"])]


def _valores(fam: Familia, producto: dict) -> dict[str, Valor]:
    """Recupera los objetos ``Valor`` (con sus variantes) a partir de los atributos del SKU."""
    salida = {}
    for dim, vals in fam.dims:
        salida[dim] = next(v for v in vals if v.cat == producto["atributos"][dim])
    return salida


def guardar(catalogo: list[dict], consultas: list[dict], carpeta: Path,
            nombre_consultas: str = "consultas.jsonl") -> tuple[Path, Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_cat = carpeta / "catalogo.csv"
    with ruta_cat.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "descripcion", "familia", "marca"])
        for p in catalogo:
            w.writerow([p["sku"], p["descripcion"], p["familia"], p["marca"]])
    ruta_q = carpeta / nombre_consultas
    with ruta_q.open("w", encoding="utf-8") as f:
        for q in consultas:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    return ruta_cat, ruta_q
