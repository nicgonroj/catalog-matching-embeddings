"""Evaluación del matching y del enrutamiento contra el set sintético etiquetado.

Una respuesta es correcta si el SKU está entre los ``skus_validos`` de la glosa: los SKU que
cumplen todo lo que el comprador escribió (si no dijo la marca, cualquier marca del mismo producto
sirve). También se informa la precisión estricta contra el SKU de origen.

Métricas principales:

- **tasa de automatización**: glosas resueltas sin intervención humana;
- **precisión de lo automatizado**: de esas, cuántas quedaron con un SKU correcto (una glosa sin
  match que se automatiza cuenta como error);
- **recall@3 en la cola humana**: en lo que va a revisión, cuántas veces un SKU correcto está entre
  los tres candidatos que ve la persona;
- **curva umbral vs. automatización / precisión**, para elegir el punto de operación.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .matcher import Candidato, Decision, Matcher, enrutar

K_RUTEO = 50          # candidatos que se miran para calcular el margen contra un rival distinguible


@dataclass
class Resultado:
    consulta: dict
    candidatos: list[Candidato]


def cargar_consultas(ruta: str | Path) -> list[dict]:
    with Path(ruta).open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def buscar_todas(matcher: Matcher, consultas: list[dict]) -> list[Resultado]:
    """Busca una vez por glosa; el enrutamiento se puede recalcular para cualquier umbral."""
    return [Resultado(q, matcher.buscar(q["texto"], k=K_RUTEO)) for q in consultas]


def _es_valido(sku: str | None, consulta: dict) -> bool:
    return sku is not None and sku in set(consulta.get("skus_validos") or [])


def decidir(resultados: list[Resultado], umbral: float, margen: float,
            agrupar_equivalentes: bool = True) -> list[Decision]:
    return [enrutar(r.consulta["id"], r.consulta["texto"], r.candidatos, umbral, margen,
                    agrupar_equivalentes=agrupar_equivalentes) for r in resultados]


def metricas(resultados: list[Resultado], decisiones: list[Decision]) -> dict:
    n = len(resultados)
    con_match = [r for r in resultados if r.consulta["sku_correcto"]]

    def recall_at(k: int) -> float:
        aciertos = sum(any(_es_valido(c.sku, r.consulta) for c in r.candidatos[:k]) for r in con_match)
        return aciertos / len(con_match) if con_match else 0.0

    pares = list(zip(resultados, decisiones))
    auto = [(r, d) for r, d in pares if d.ruta == "automatico"]
    cola = [(r, d) for r, d in pares if d.ruta == "revision"]
    auto_ok = sum(_es_valido(d.sku, r.consulta) for r, d in auto)
    auto_estricto = sum(d.sku == r.consulta["sku_correcto"] for r, d in auto)
    cola_con_match = [(r, d) for r, d in cola if r.consulta["sku_correcto"]]
    cola_top3 = sum(any(_es_valido(c.sku, r.consulta) for c in d.candidatos[:3]) for r, d in cola_con_match)
    sin_match = [r for r in resultados if not r.consulta["sku_correcto"]]
    return {
        "glosas": n,
        "glosas_con_match": len(con_match),
        "glosas_sin_match": len(sin_match),
        "recall@1": recall_at(1),
        "recall@3": recall_at(3),
        "recall@10": recall_at(10),
        "automatizadas": len(auto),
        "tasa_automatizacion": len(auto) / n if n else 0.0,
        "precision_automatizado": auto_ok / len(auto) if auto else 0.0,
        "precision_automatizado_sku_origen": auto_estricto / len(auto) if auto else 0.0,
        "errores_automatizados": len(auto) - auto_ok,
        "sin_match_automatizadas": sum(not r.consulta["sku_correcto"] for r, _ in auto),
        "en_revision": len(cola),
        "recall@3_cola": cola_top3 / len(cola_con_match) if cola_con_match else 0.0,
        "sin_match_en_cola": sum(not r.consulta["sku_correcto"] for r, _ in cola),
        # glosas con match que quedan resueltas: automáticas correctas o con el SKU en el top-3 de la cola
        "resueltas_o_a_un_clic": (auto_ok + cola_top3) / len(con_match) if con_match else 0.0,
    }


def curva(resultados: list[Resultado], umbrales: list[float], margen: float) -> list[dict]:
    filas = []
    for u in umbrales:
        m = metricas(resultados, decidir(resultados, u, margen))
        filas.append({"umbral": u, "margen": margen, **m})
    return filas


# ------------------------------------------------------------------------------- salidas


def pct(x: float) -> str:
    return f"{100 * x:.1f} %".replace(".", ",")


def num(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def tabla_curva(filas: list[dict]) -> str:
    lineas = ["| Umbral | Automatización | Precisión de lo automatizado | Errores automáticos | Recall@3 en la cola |",
              "|---:|---:|---:|---:|---:|"]
    for f in filas:
        lineas.append(f"| {num(f['umbral'])} | {pct(f['tasa_automatizacion'])} | {pct(f['precision_automatizado'])} "
                      f"| {f['errores_automatizados']} | {pct(f['recall@3_cola'])} |")
    return "\n".join(lineas)


def tabla_resumen(m: dict, umbral: float, margen: float) -> str:
    filas = [
        ("Glosas evaluadas (con match / sin match)", f"{m['glosas']} ({m['glosas_con_match']} / {m['glosas_sin_match']})"),
        ("Recall@1 / @3 / @10 (recuperación)", f"{pct(m['recall@1'])} / {pct(m['recall@3'])} / {pct(m['recall@10'])}"),
        (f"Tasa de automatización (umbral {num(umbral)}, margen {num(margen)})", pct(m["tasa_automatizacion"])),
        ("Precisión de lo automatizado", pct(m["precision_automatizado"])),
        ("Precisión estricta (SKU de origen exacto)", pct(m["precision_automatizado_sku_origen"])),
        ("Glosas sin match automatizadas por error", str(m["sin_match_automatizadas"])),
        ("Recall@3 en la cola de revisión", pct(m["recall@3_cola"])),
        ("Glosas con match resueltas o a un clic", pct(m["resueltas_o_a_un_clic"])),
    ]
    return "\n".join(["| Métrica | Valor |", "|---|---:|"] + [f"| {a} | {b} |" for a, b in filas])


def guardar_salidas(carpeta: Path, resultados: list[Resultado], decisiones: list[Decision],
                    reporte: str) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    with (carpeta / "decisiones.jsonl").open("w", encoding="utf-8") as f:
        for r, d in zip(resultados, decisiones):
            fila = d.a_dict()
            fila["sku_correcto"] = r.consulta["sku_correcto"]
            fila["correcto"] = _es_valido(d.sku, r.consulta) if d.ruta == "automatico" else None
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    with (carpeta / "cola_revision.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cab = ["id", "glosa", "motivo"]
        for i in (1, 2, 3):
            cab += [f"sku_{i}", f"descripcion_{i}", f"score_{i}"]
        w.writerow(cab)
        for d in decisiones:
            if d.ruta != "revision":
                continue
            fila = [d.id, d.texto, d.motivo]
            for c in d.candidatos[:3]:
                fila += [c.sku, c.descripcion, f"{c.score:.3f}"]
            w.writerow(fila)
    (carpeta / "reporte.md").write_text(reporte, encoding="utf-8")
