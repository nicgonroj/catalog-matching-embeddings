"""Matching de descripciones libres contra el catálogo y enrutamiento por excepción.

Flujo por cada descripción:

1. normalizar (unidades, abreviaturas, sinónimos);
2. recuperar candidatos por similitud coseno (TF-IDF local u, opcionalmente, embeddings);
3. ajustar el puntaje con una regla de consistencia de medidas: si el comprador pide 10 ml y el
   candidato es de 5 ml, el candidato baja aunque el texto se parezca mucho;
4. enrutar: **automático** si el mejor candidato supera el umbral y le saca suficiente margen al
   segundo; si no, **revisión humana** con los tres mejores candidatos.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .normalizacion import (comparar_medidas, extraer_medidas, normalizar, normalizar_basico,
                            numeros_sueltos_coincidentes)
from .vectorizador import IndiceTfidf

# Pesos de la regla de medidas que ajusta la similitud del texto:
BONO_MEDIDA = 0.02         # por cada medida que coincide (10 ml = 10 cc)
CASTIGO_CONFLICTO = 0.30   # por cada medida que contradice lo pedido (pidieron 10 ml, es de 5 ml)

# Punto de operación elegido sobre el set de validación (semilla 7), no sobre el de prueba.
UMBRAL_POR_DEFECTO = 0.85
MARGEN_POR_DEFECTO = 0.05


@dataclass
class Producto:
    sku: str
    descripcion: str
    familia: str = ""
    marca: str = ""


@dataclass
class Candidato:
    sku: str
    descripcion: str
    score: float           # puntaje final usado para rankear y enrutar
    similitud: float       # coseno del texto (TF-IDF o embedding)
    ajuste_medidas: float = 0.0
    medidas_sin_explicar: int = 0   # medidas pedidas que este candidato no tiene
    # Lo que la consulta «ve» de este candidato: palabras en común y números coincidentes. Dos
    # candidatos con la misma firma solo difieren en atributos que el comprador no especificó.
    firma: frozenset = field(default_factory=frozenset, repr=False, compare=False)

    def a_dict(self) -> dict:
        d = asdict(self)
        d.pop("firma")
        return d


@dataclass
class Decision:
    id: str
    texto: str
    ruta: str              # "automatico" | "revision"
    sku: str | None        # SKU asignado si es automático; mejor candidato si va a revisión
    score: float
    margen: float
    motivo: str
    equivalentes: int = 0   # otros candidatos indistinguibles del mejor según lo que dice la glosa
    candidatos: list[Candidato] = field(default_factory=list)

    def a_dict(self) -> dict:
        d = asdict(self)
        d["candidatos"] = [c.a_dict() for c in self.candidatos]
        return d


class Reranker(Protocol):
    """Recalcula la similitud de los candidatos (por ejemplo, con embeddings de OpenAI)."""

    def similitudes(self, consulta: str, descripciones: list[str]) -> list[float]: ...


def cargar_catalogo(ruta: str | Path) -> list[Producto]:
    with Path(ruta).open(encoding="utf-8") as f:
        return [Producto(r["sku"], r["descripcion"], r.get("familia", ""), r.get("marca", ""))
                for r in csv.DictReader(f)]


class Matcher:
    def __init__(self, productos: list[Producto], usar_reglas: bool = True,
                 reranker: Reranker | None = None, n_candidatos: int = 200, n_rerank: int = 50):
        self.productos = productos
        self.usar_reglas = usar_reglas
        self.reranker = reranker
        self.n_candidatos = n_candidatos
        self.n_rerank = n_rerank      # con embeddings, solo se re-puntúan los mejores del TF-IDF
        self._normalizar: Callable[[str], str] = normalizar if usar_reglas else normalizar_basico
        normalizados = [self._normalizar(p.descripcion) for p in productos]
        self._medidas = [extraer_medidas(t) for t in normalizados] if usar_reglas else []
        self._tokens = [set(t.split()) for t in normalizados]
        self.indice = IndiceTfidf().ajustar(normalizados)

    def buscar(self, consulta: str, k: int = 10) -> list[Candidato]:
        """Top-k candidatos para una descripción libre, de mayor a menor puntaje."""
        texto = self._normalizar(consulta)
        crudos = self.indice.buscar(texto, k=max(k, self.n_candidatos))
        if not crudos:
            return []
        similitudes = [s for _, s in crudos]
        if self.reranker is not None:
            crudos = crudos[:max(k, self.n_rerank)]
            similitudes = self.reranker.similitudes(consulta, [self.productos[i].descripcion for i, _ in crudos])
        medidas_q = extraer_medidas(texto) if self.usar_reglas else {}
        tokens_q = set(texto.split())
        candidatos = []
        for (i, _), sim in zip(crudos, similitudes):
            ajuste, sin_explicar = 0.0, 0
            firma = set(tokens_q & self._tokens[i])
            if medidas_q:
                coincide, conflicto, sin_explicar = comparar_medidas(medidas_q, self._medidas[i])
                ajuste += BONO_MEDIDA * coincide - CASTIGO_CONFLICTO * conflicto
                numeros = medidas_q.get("suelto", set()) | medidas_q.get("num", set())
                firma |= {"#" + v for v in numeros_sueltos_coincidentes(numeros, self._medidas[i])}
            p = self.productos[i]
            # sin tope superior: recortar en 1,0 empataría a candidatos que la regla sí distingue
            candidatos.append(Candidato(p.sku, p.descripcion, round(max(0.0, sim + ajuste), 4),
                                        round(sim, 4), round(ajuste, 4), sin_explicar, frozenset(firma)))
        candidatos.sort(key=lambda c: (-c.score, c.sku))
        return candidatos[:k]


def enrutar(id_: str, texto: str, candidatos: list[Candidato], umbral: float, margen_minimo: float,
            n_revision: int = 3, agrupar_equivalentes: bool = True) -> Decision:
    """Automatiza solo si hay un ganador claro; si no, la persona elige entre los top-3.

    El margen se mide contra el mejor candidato **distinguible** del primero. Si el comprador no
    indicó marca ni presentación, «caja 100 marca A» y «caja 200 marca B» empatan, pero ambos
    cumplen lo pedido: el empate no debe bloquear la automatización. Con
    ``agrupar_equivalentes=False`` el margen se mide contra el segundo, sin más.
    """
    if not candidatos:
        return Decision(id_, texto, "revision", None, 0.0, 0.0, "sin candidatos")
    mejor = candidatos[0]
    rivales = [c for c in candidatos[1:] if not agrupar_equivalentes or c.firma != mejor.firma]
    segundo = rivales[0].score if rivales else 0.0
    margen = round(mejor.score - segundo, 4)
    equivalentes = len(candidatos) - 1 - len(rivales)
    if mejor.score < umbral:
        motivo = f"score {mejor.score:.2f} < umbral {umbral:.2f}"
    elif margen < margen_minimo:
        motivo = f"margen {margen:.3f} < {margen_minimo:.3f} (candidatos ambiguos)"
    elif mejor.medidas_sin_explicar:
        motivo = "la glosa pide medidas que el mejor candidato no tiene"
    else:
        return Decision(id_, texto, "automatico", mejor.sku, mejor.score, margen, "ganador claro",
                        equivalentes, [mejor])
    return Decision(id_, texto, "revision", mejor.sku, mejor.score, margen, motivo, equivalentes,
                    candidatos[:n_revision])
