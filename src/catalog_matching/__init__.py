"""Matching de descripciones comerciales libres contra un catálogo de productos."""
from .matcher import Candidato, Decision, Matcher, Producto, cargar_catalogo, enrutar
from .normalizacion import normalizar

__all__ = ["Candidato", "Decision", "Matcher", "Producto", "cargar_catalogo", "enrutar", "normalizar"]
__version__ = "0.1.0"
