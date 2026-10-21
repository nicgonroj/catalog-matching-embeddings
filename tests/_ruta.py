"""Permite correr los tests sin instalar el paquete: agrega src/ al path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
