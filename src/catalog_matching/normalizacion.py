"""Reglas de normalización de descripciones comerciales.

Los compradores escriben como pueden: «gte nitr T-M s/polvo cj x100», «jer 10cc c/ag 21x1½»,
«alcohol 70 1 lt». Antes de comparar textos conviene llevarlos a una forma canónica:

- unidades: ``cc`` → ``ml``, litros → mililitros, pulgadas → milímetros, ``Fr``, calibres, tallas;
- abreviaturas y sinónimos: ``gte`` → ``guante``, ``bránula`` → ``cateter``, ``arandela`` → ``golilla``;
- negaciones como un solo token (``sin polvo`` → ``sinpolvo``) para que «sin» no se pierda;
- presentaciones: ``cj x100``, ``c/100`` y ``100 unidades`` → ``100un``.

Las mismas reglas se aplican al catálogo y a la consulta, así ambos lados quedan en el mismo
vocabulario. ``extraer_medidas`` saca los atributos medibles que usa la regla de consistencia del
matcher (por ejemplo, para no aceptar una jeringa de 5 ml cuando piden una de 10 ml).
"""
from __future__ import annotations

import re
import unicodedata

# Abreviaturas, plurales irregulares y sinónimos frecuentes en órdenes de compra.
ABREVIATURAS = {
    # insumos médicos
    "gte": "guante", "gtes": "guante", "guant": "guante", "gts": "guante",
    "jer": "jeringa", "jering": "jeringa", "jrga": "jeringa",
    "ag": "aguja", "agj": "aguja", "agja": "aguja",
    "cat": "cateter", "branula": "cateter", "venoclisis": "cateter",
    "masc": "mascarilla", "mascara": "mascarilla", "tapaboca": "mascarilla",
    "cubreboca": "mascarilla", "barbijo": "mascarilla",
    "exam": "examen", "procedimiento": "examen", "proced": "examen",
    "quir": "quirurgico", "quirurg": "quirurgico", "qx": "quirurgico", "cirugia": "quirurgico",
    "est": "esteril", "esterilizado": "esteril", "estril": "esteril",
    "desech": "desechable", "desch": "desechable", "descartable": "desechable",
    "nitr": "nitrilo", "nit": "nitrilo",
    "ltx": "latex", "vin": "vinilo", "vinil": "vinilo",
    "alc": "alcohol", "clorhex": "clorhexidina", "clorh": "clorhexidina", "chg": "clorhexidina",
    "vendaje": "venda", "vend": "venda", "elast": "elastica", "elastico": "elastica",
    "cta": "cinta", "adh": "adhesiva", "adhesivo": "adhesiva",
    "microp": "microporosa", "microporo": "microporosa", "transp": "transparente",
    "apos": "aposito", "electr": "electrodo", "snd": "sonda",
    "isoprop": "isopropilico",
    # ferretería e insumos industriales
    "torn": "tornillo", "tornill": "tornillo", "autop": "autoperforante",
    "autoperf": "autoperforante", "galvanizado": "zincado", "galv": "zincado", "zinc": "zincado",
    "hex": "hexagonal", "pern": "perno", "arandela": "golilla", "disc": "disco", "cort": "corte",
    "inoxidable": "inox", "antiparra": "lente", "gafa": "lente", "anteojo": "lente",
    "cbl": "cable", "seg": "seguridad", "soldar": "soldadura", "volcanita": "drywall",
    "pu": "poliuretano", "hormigon": "concreto", "piedra": "concreto", "widia": "concreto",
    "fierro": "metal", "marron": "cafe", "antifog": "antiempanante", "ipa": "isopropilico",
    "autoadherente": "cohesiva", "micro": "microporosa", "ped": "pediatrico",
    "infantil": "pediatrico", "espuma": "foam", "nailon": "nylon", "pga": "poliglicolico",
    "ll": "luerlock", "ls": "luerslip", "buzo": "overol", "mameluco": "overol",
    # empaques
    "cj": "caja", "cja": "caja", "cjs": "caja", "cx": "caja", "bls": "bolsa",
    "paq": "paquete", "pqte": "paquete", "pqt": "paquete", "pack": "paquete", "sob": "sobre",
    # concordancia de género: «negra» y «negro» son el mismo atributo
    "negra": "negro", "blanca": "blanco", "amarilla": "amarillo", "roja": "rojo",
    "oscura": "oscuro", "clara": "claro", "espejada": "espejado", "zincada": "zincado",
    "galvanizada": "zincado", "plastica": "plastico", "quirurgica": "quirurgico",
    # sinónimos del rubro
    "normal": "convencional", "estandar": "convencional", "tiras": "amarras",
    "presion": "hidraulico", "desague": "sanitario",
    "dentada": "estrella", "anillado": "reforzado", "tricapa": "3pliegues",
    # tallas en palabras
    "mediano": "talla_m", "mediana": "talla_m", "grande": "talla_l", "chico": "talla_s",
    "chica": "talla_s", "pequeno": "talla_s", "pequena": "talla_s",
}

# Palabras que no aportan a identificar el producto.
STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "para", "por", "con", "sin", "y", "en", "x", "a", "o",
    "al", "un", "una", "se", "tipo", "marca", "modelo", "segun", "solicita", "solicito", "compra",
    "adquisicion", "req", "insumo", "urgente", "similar", "ver", "especificaciones", "entrega",
    "bodega", "muestra", "stock", "critico", "calidad", "hospitalaria", "pabellon", "uso",
}

# Frases que conviene fijar antes de separar en palabras (sobre todo negaciones).
FRASES = [
    (r"\bs\s*/\s*p\b", " sinpolvo "),
    (r"\b(?:s\s*/|sin|libre\s+de)\s*polvo\b", " sinpolvo "),
    (r"\b(?:c\s*/|con)\s*polvo\b", " conpolvo "),
    (r"\b(?:s\s*/|sin)\s*aguja\b", " sinaguja "),
    (r"\b(?:c\s*/|con)\s*(?:aguja|agja|agj|ag)\b", " conaguja "),
    (r"\b(?:s\s*/|sin)\s*aletas?\b", " sinaletas "),
    (r"\b(?:c\s*/|con)\s*aletas?\b", " conaletas "),
    (r"\b(?:s\s*/|sin)\s*borde\b", " sinborde "),
    (r"\b(?:c\s*/|con)\s*borde\b", " conborde "),
    (r"\bno\s+est(?:eril)?\b", " noesteril "),
    (r"\bk\s*n\s*-?\s*95\b", " kn95 "),
    (r"\bn\s*-?\s*95\b", " n95 "),
    (r"\bdos\s+vias\b", " 2vias "),
    (r"\btres\s+vias\b", " 3vias "),
    (r"\bs\s*/\s*ag\b", " sinaguja "),
    (r"\b(?:s\s*/|sin)\s*(?:balon|cuff)\b", " sinbalon "),
    (r"\b(?:c\s*/|con)\s*(?:balon|cuff)\b", " conbalon "),
    (r"\bpu[nñ]o\s+(?:extra\s+)?largo\b|\bextra\s+largo\b|\bca[nñ]a\s+larga\b", " punolargo "),
    (r"\bcab(?:eza|\.)?\s+", " cabeza "),
    (r"\bluer\s*-?\s*lock\b", " luerlock "),
    (r"\bluer\s*-?\s*slip\b", " luerslip "),
    (r"\bacero\s+inox(?:idable)?\b", " inox "),
    (r"\btapa\s*bocas?\b", " mascarilla "),
    (r"\btapones?\s+(?:de\s+)?oidos?\b", " protector auditivo tapon "),
    (r"\banti\s*-?\s*empa[nñ]ante\b", " antiempanante "),
    (r"\banti\s*-?\s*corte\b", " anticorte "),
    (r"\bdocena\b", " pack 12 pares "),
]

_PULG = r'\s*(?:"|pulgadas?|pulg\.?|plg\.?)'
_NUM = r"(?<![\w.])(\d+(?:\.\d+)?)"


def _fmt(valor: float) -> str:
    """Escribe un número sin ceros sobrantes: 1000.0 → '1000', 7.50 → '7.5'."""
    return f"{valor:.3f}".rstrip("0").rstrip(".")


def _pulgadas_a_mm(valor: float) -> str:
    mm = valor * 25.4
    # medidas chicas con un decimal (1/2" = 12.7 mm); el resto, al milímetro (1 1/2" = 38 mm)
    return f" {_fmt(round(mm, 1)) if mm < 20 else round(mm)}mm "


def quitar_tildes(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar_basico(texto: str) -> str:
    """Normalización mínima (minúsculas, sin tildes ni puntuación). Es la línea base sin reglas."""
    texto = quitar_tildes(texto.lower())
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _unidades(t: str) -> str:
    """Convierte y pega unidades al número para que cada medida sea un solo token."""
    # pernos métricos: «M 8», «M-8» → «m8»
    t = re.sub(r"\bm(?:\s*-\s*|\s+)(\d+)\b", r" m\1 ", t)
    # electrodos de soldadura: «6011», «E-6011» → e6011
    t = re.sub(r"(?<![\w.])e?\s*-?\s*(6011|6013|7018|308l)\b", r" e\1 ", t)
    # pulgadas (mixtas, fracciones y decimales) → milímetros
    t = re.sub(r"(?<![\w.])(\d)\s+(\d+)/(\d+)" + _PULG,
               lambda m: _pulgadas_a_mm(int(m[1]) + int(m[2]) / int(m[3])), t)
    t = re.sub(r"(?<![\d/])(\d+)/(\d+)" + _PULG, lambda m: _pulgadas_a_mm(int(m[1]) / int(m[2])), t)
    t = re.sub(_NUM + _PULG, lambda m: _pulgadas_a_mm(float(m[1])), t)
    t = re.sub(r"(?<![\w.])(\d+)\s+1/2\b", r" \1.5 ", t)       # talla «7 1/2» → 7.5
    # números de tornillo (#8) y calibres de sutura (3-0, 3/0)
    t = re.sub(r"(?:#|\bnro\.?|\bnum\.?)\s*(\d+(?:\.\d+)?)", r" num\1 ", t)
    t = re.sub(r"(?<![\w.])(\d)\s*[-/]\s*0\b", r" \1_0 ", t)
    # secciones de cable
    t = re.sub(_NUM + r"\s*(?:mm2|mm\^2|mm\s+cuadrados?)\b", lambda m: f" {_fmt(float(m[1]))}mm2 ", t)
    # dimensiones 10 x 10 cm, 7.5cm x 7.5cm, 10x10 (sin unidad)
    t = re.sub(_NUM + r"\s*(cm|mm)?\s*x\s*(\d+(?:\.\d+)?)\s*(cm|mm)\b",
               lambda m: f" {_fmt(float(m[1]))}x{_fmt(float(m[3]))}{m[4]} ", t)
    t = re.sub(_NUM + r"\s*x\s*(\d+(?:\.\d+)?)(?![\w.])",
               lambda m: f" {_fmt(float(m[1]))}x{_fmt(float(m[2]))} ", t)
    # volumen: todo a ml
    t = re.sub(_NUM + r"\s*(?:ml|cc|cm3|mililitros?)\b", lambda m: f" {_fmt(float(m[1]))}ml ", t)
    t = re.sub(_NUM + r"\s*(?:l|lt|lts|ltr|litros?)\b", lambda m: f" {_fmt(float(m[1]) * 1000)}ml ", t)
    # espesor de bolsas y aislación acústica
    t = re.sub(_NUM + r"\s*(?:micrones|micras|mic|um)\b", lambda m: f" {_fmt(float(m[1]))}um ", t)
    t = re.sub(r"\bnrr\s*(\d+)\s*(?:db)?\b", r" \1db ", t)
    t = re.sub(_NUM + r"\s*db\b", lambda m: f" {_fmt(float(m[1]))}db ", t)
    # peso
    t = re.sub(_NUM + r"\s*(?:kg|kgs|kilos?)\b", lambda m: f" {_fmt(float(m[1]))}kg ", t)
    # longitud
    t = re.sub(_NUM + r"\s*(?:mm|milimetros?)\b", lambda m: f" {_fmt(float(m[1]))}mm ", t)
    t = re.sub(_NUM + r"\s*(?:cm|cms|centimetros?)\b", lambda m: f" {_fmt(float(m[1]))}cm ", t)
    t = re.sub(_NUM + r"\s*(?:m|mt|mts|mtr|mtrs|metros?)\b", lambda m: f" {_fmt(float(m[1]))}m ", t)
    # calibre de agujas y catéteres (G), french de sondas (Fr)
    t = re.sub(r"\b(?:calibre|gauge)\s*(\d+)\s*g?\b", r" \1g ", t)
    t = re.sub(r"(?<![\w.])(\d+)\s*g\b", r" \1g ", t)
    t = re.sub(r"(?<![\w.])(\d+)\s*(?:fr|french|ch)\b", r" \1fr ", t)
    t = re.sub(r"\b(?:fr|french|ch)\.?\s*(\d+)\b", r" \1fr ", t)
    # porcentajes: «70 %», «70°» (grados de alcohol), «al 70»
    t = re.sub(_NUM + r"\s*°", lambda m: f" {_fmt(float(m[1]))}% ", t)
    t = re.sub(_NUM + r"\s*%", lambda m: f" {_fmt(float(m[1]))}% ", t)
    t = re.sub(r"\bal\s+" + _NUM + r"(?![\w.%])", lambda m: f" {_fmt(float(m[1]))}% ", t)
    # vías y pliegues
    t = re.sub(r"(?<![\w.])(\d+)\s*vias?\b", r" \1vias ", t)
    t = re.sub(r"(?<![\w.])(\d+)\s*(?:pliegues?|capas?|dobleces)\b", r" \1pliegues ", t)
    # tallas explícitas: «talla M», «T-M», «talla 7.5»
    t = re.sub(r"\b(?:talla|tall|tal|t)\s*[-/.:]?\s*(xxxl|xxl|xl|xs|s|m|l)\b", r" talla_\1 ", t)
    t = re.sub(r"\b(?:talla|t)\s*[-/.:]?\s*(\d+(?:\.\d+)?)(?![\w.])", lambda m: f" talla_{_fmt(float(m[1]))} ", t)
    t = re.sub(r"\bextra\s+grande\b", " talla_xl ", t)
    t = re.sub(r"\bpara\s+perno\s+(\d+)\s*mm\b", r" m\1 ", t)
    # presentaciones: «100 unidades», «x100», «c/100», «caja de 100» → 100un
    t = re.sub(r"(?<![\w.])(\d+)\s*(?:unidades|unidad|unid|uds|und|un|u|pcs|piezas)\b", r" \1un ", t)
    t = re.sub(r"(?:\bx|\bc\s*/)\s*(\d+)(?:un)?(?![\w.%])", r" \1un ", t)
    t = re.sub(r"\b(caja|cajas|cj|cja|cjs|bolsa|bolsas|bls|paquete|paq|pqte|sobre|sob|pack|rollo)"
               r"\s*(?:de|x|c/)?\s*(\d+)(?![\w.%])", r" \1 \2un ", t)
    return t


def _plural(token: str) -> str:
    """Singulariza de forma simple: «guantes» → «guante». Se aplica igual a catálogo y consulta."""
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss") and token.isalpha():
        return token[:-1]
    return token


def normalizar(texto: str) -> str:
    """Lleva una descripción (de catálogo o de comprador) a su forma canónica."""
    t = texto.lower()
    for origen, destino in (("½", " 1/2"), ("¼", " 1/4"), ("¾", " 3/4"), ("²", "2"),
                            ("”", '"'), ("“", '"'), ("″", '"'), ("''", '"')):
        t = t.replace(origen, destino)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)          # coma decimal
    t = re.sub(r"\bn\s*[°º]\s*(?=\d)", " #", t)   # «N° 14» → «#14» → «num14»
    t = re.sub(r"\bn\s*[°º]\s*", " ", t)
    t = quitar_tildes(t)
    for patron, reemplazo in FRASES:
        t = re.sub(patron, reemplazo, t)
    t = _unidades(t)

    tokens = []
    for tok in re.findall(r"[a-z0-9_%.]+", t):
        tok = tok.strip(".")
        if not tok:
            continue
        tok = ABREVIATURAS.get(tok, tok)
        tok = ABREVIATURAS.get(_plural(tok), _plural(tok))
        if tok in {"xs", "s", "m", "l", "xl", "xxl", "xxxl"}:   # talla suelta: «guante nitrilo M»
            tok = "talla_" + tok
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
    return " ".join(tokens)


# --- Atributos medibles -------------------------------------------------------------------

_PATRONES_MEDIDA = [
    ("dim", re.compile(r"^(\d+(?:\.\d+)?x\d+(?:\.\d+)?)(?:cm|mm)?$")),
    ("mm2", re.compile(r"^(\d+(?:\.\d+)?)mm2$")),
    ("ml", re.compile(r"^(\d+(?:\.\d+)?)ml$")),
    ("kg", re.compile(r"^(\d+(?:\.\d+)?)kg$")),
    ("mm", re.compile(r"^(\d+(?:\.\d+)?)mm$")),
    ("cm", re.compile(r"^(\d+(?:\.\d+)?)cm$")),
    ("m", re.compile(r"^(\d+(?:\.\d+)?)m$")),
    ("um", re.compile(r"^(\d+(?:\.\d+)?)um$")),
    ("db", re.compile(r"^(\d+)db$")),
    ("g", re.compile(r"^(\d+)g$")),
    ("fr", re.compile(r"^(\d+)fr$")),
    ("%", re.compile(r"^(\d+(?:\.\d+)?)%$")),
    ("vias", re.compile(r"^(\d+)vias$")),
    ("pliegues", re.compile(r"^(\d+)pliegues$")),
    ("un", re.compile(r"^(\d+)un$")),
    ("talla", re.compile(r"^talla_(.+)$")),
    ("metrica", re.compile(r"^m(\d+)$")),
    ("num", re.compile(r"^num(\d+(?:\.\d+)?)$")),
    ("sutura", re.compile(r"^(\d)_0$")),
    ("suelto", re.compile(r"^(\d+(?:\.\d+)?)$")),     # número sin unidad: «N°18», «5 cajas»
]


_A_MM = {"cm": 10.0, "m": 1000.0}


def extraer_medidas(texto_normalizado: str) -> dict[str, set[str]]:
    """Devuelve {tipo de medida: valores}, por ejemplo {'ml': {'10'}, 'g': {'21'}}."""
    medidas: dict[str, set[str]] = {}
    for tok in texto_normalizado.split():
        for tipo, patron in _PATRONES_MEDIDA:
            m = patron.match(tok)
            if m:
                valor = m[1]
                if tipo in _A_MM:      # todas las longitudes se comparan en milímetros
                    valor, tipo = _fmt(float(valor) * _A_MM[tipo]), "mm"
                medidas.setdefault(tipo, set()).add(valor)
                break
    return medidas


def _iguales(a: str, b: str, tolerancia: float = 0.03) -> bool:
    """Compara valores con tolerancia relativa (115 mm ≈ 4 1/2" = 114 mm)."""
    try:
        x, y = float(a), float(b)
    except ValueError:
        return a == b
    return abs(x - y) <= tolerancia * max(abs(x), abs(y), 1e-9)


# Tipos que pueden venir en la glosa sin ser un atributo del producto (cantidades a comprar).
_NO_EXIGIBLES = {"suelto", "un"}


def comparar_medidas(consulta: dict[str, set[str]], candidato: dict[str, set[str]]) -> tuple[int, int, int]:
    """Cuenta (coincidencias, conflictos, sin_explicar) entre consulta y candidato.

    Solo se comparan tipos presentes en ambos lados: si el comprador no indicó la talla, no hay
    conflicto de talla. Un número suelto o con «N°» («sonda foley N°18») suma una coincidencia
    si aparece en cualquier medida del candidato, pero nunca resta: puede ser una cantidad.

    ``sin_explicar`` cuenta medidas pedidas que el candidato no tiene (piden «10 ml» y el candidato
    es una aguja, o piden «N° 10» y ningún atributo vale 10). No bajan el puntaje, pero impiden
    automatizar: falta algo que una persona debe mirar.
    """
    coincidencias = conflictos = sin_explicar = 0
    for tipo, valores in consulta.items():
        if tipo in ("suelto", "num"):
            n = len(numeros_sueltos_coincidentes(valores, candidato))
            coincidencias += n
            if tipo == "num":
                sin_explicar += len(valores) - n
            continue
        if tipo not in candidato:
            if tipo not in _NO_EXIGIBLES:
                sin_explicar += len(valores)
            continue
        for valor in valores:
            if any(_iguales(valor, otro) for otro in candidato[tipo]):
                coincidencias += 1
            else:
                conflictos += 1
    return coincidencias, conflictos, sin_explicar


def numeros_sueltos_coincidentes(valores: set[str], candidato: dict[str, set[str]]) -> set[str]:
    """Números sin unidad (o con «N°») de la consulta que aparecen en alguna medida del candidato."""
    disponibles = set()
    for tipo, vals in candidato.items():
        for v in vals:
            disponibles.update(v.split("x") if tipo == "dim" else [v])
    return {v for v in valores if any(_iguales(v, d, tolerancia=0.0) for d in disponibles)}
