"""Línea de comandos.

    python -m catalog_matching generar                 # catálogo + glosas sintéticas en data/
    python -m catalog_matching buscar "gte nitr M s/p cj x100"
    python -m catalog_matching evaluar --ablacion      # métricas, curva y archivos en output/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import sintetico
from .evaluacion import (buscar_todas, cargar_consultas, curva, decidir, guardar_salidas, metricas, num, pct,
                         tabla_curva, tabla_resumen)
from .matcher import MARGEN_POR_DEFECTO, UMBRAL_POR_DEFECTO, Matcher, cargar_catalogo, enrutar

RAIZ = Path.cwd()


def _matcher(args, usar_reglas: bool = True) -> Matcher:
    productos = cargar_catalogo(args.catalogo)
    reranker = None
    if getattr(args, "embeddings", "local") == "openai":
        from .embeddings import EmbeddingsOpenAI, RerankerEmbeddings
        reranker = RerankerEmbeddings(EmbeddingsOpenAI(ruta_cache=Path(args.salida) / "cache_embeddings.json"))
    return Matcher(productos, usar_reglas=usar_reglas, reranker=reranker)


def cmd_generar(args) -> None:
    catalogo = sintetico.generar_catalogo(args.semilla_catalogo)
    consultas = sintetico.generar_consultas(catalogo, n=args.n, semilla=args.semilla)
    ruta_cat, ruta_q = sintetico.guardar(catalogo, consultas, Path(args.salida), args.archivo_consultas)
    sin_match = sum(q["sku_correcto"] is None for q in consultas)
    print(f"{len(catalogo)} SKU → {ruta_cat}")
    print(f"{len(consultas)} glosas ({sin_match} sin match en catálogo) → {ruta_q}")


def cmd_buscar(args) -> None:
    m = _matcher(args)
    candidatos = m.buscar(args.texto, k=max(args.k, 50))
    d = enrutar("consulta", args.texto, candidatos, args.umbral, args.margen)
    print(f"ruta: {d.ruta} · {d.motivo} · score {d.score:.3f} · margen {d.margen:.3f}")
    for i, c in enumerate(candidatos[:args.k], 1):
        print(f"{i:>2}. {c.score:.3f}  {c.sku}  {c.descripcion}  (texto {c.similitud:.3f}, reglas {c.ajuste_medidas:+.2f})")


def cmd_evaluar(args) -> None:
    consultas = cargar_consultas(args.consultas)
    inicio = time.time()
    m = _matcher(args)
    resultados = buscar_todas(m, consultas)
    segundos = time.time() - inicio
    decisiones = decidir(resultados, args.umbral, args.margen)
    met = metricas(resultados, decisiones)
    umbrales = [round(0.50 + 0.05 * i, 2) for i in range(10)]
    filas = curva(resultados, umbrales, args.margen)

    partes = [f"# Reporte de evaluación ({args.embeddings})", "",
              f"Catálogo: `{args.catalogo}` ({len(m.productos)} SKU) · glosas: `{args.consultas}` · "
              f"tiempo total {segundos:.1f} s", "", "## Punto de operación", "", tabla_resumen(met, args.umbral, args.margen),
              "", f"## Curva umbral vs. automatización (margen {num(args.margen)})", "", tabla_curva(filas)]

    if args.ablacion:
        configs = [("TF-IDF sin reglas", Matcher(m.productos, usar_reglas=False), False),
                   ("+ normalización y regla de medidas", m, False),
                   ("+ margen contra rivales distinguibles (completo)", m, True)]
        lineas = ["| Configuración | Recall@1 | Recall@3 | Automatización | Precisión automatizado |",
                  "|---|---:|---:|---:|---:|"]
        cache = {}
        for nombre, matcher, agrupar in configs:
            res = cache.setdefault(id(matcher), resultados if matcher is m else buscar_todas(matcher, consultas))
            mm = metricas(res, decidir(res, args.umbral, args.margen, agrupar_equivalentes=agrupar))
            lineas.append(f"| {nombre} | {pct(mm['recall@1'])} | {pct(mm['recall@3'])} | "
                          f"{pct(mm['tasa_automatizacion'])} | {pct(mm['precision_automatizado'])} |")
        partes += ["", f"## Ablación (umbral {num(args.umbral)}, margen {num(args.margen)})", "", "\n".join(lineas)]

    reporte = "\n".join(partes) + "\n"
    guardar_salidas(Path(args.salida), resultados, decisiones, reporte)
    print(reporte)
    print(f"Archivos: {args.salida}/decisiones.jsonl, {args.salida}/cola_revision.csv, {args.salida}/reporte.md")
    if args.json:
        print(json.dumps(met, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="catalog_matching", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)

    g = sub.add_parser("generar", help="genera el catálogo y las glosas sintéticas")
    g.add_argument("--semilla", type=int, default=42, help="semilla de las glosas")
    g.add_argument("--semilla-catalogo", type=int, default=2026)
    g.add_argument("--n", type=int, default=1000)
    g.add_argument("--salida", default="data")
    g.add_argument("--archivo-consultas", default="consultas.jsonl")
    g.set_defaults(func=cmd_generar)

    for nombre, func, ayuda in (("buscar", cmd_buscar, "busca una glosa en el catálogo"),
                                ("evaluar", cmd_evaluar, "evalúa contra el set etiquetado")):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("--catalogo", default="data/catalogo.csv")
        s.add_argument("--umbral", type=float, default=UMBRAL_POR_DEFECTO)
        s.add_argument("--margen", type=float, default=MARGEN_POR_DEFECTO)
        s.add_argument("--embeddings", choices=["local", "openai"], default="local",
                       help="local: TF-IDF sin red (por defecto). openai: re-puntúa con embeddings (requiere OPENAI_API_KEY)")
        s.add_argument("--salida", default="output")
        s.set_defaults(func=func)
        if nombre == "buscar":
            s.add_argument("texto")
            s.add_argument("--k", type=int, default=5)
        else:
            s.add_argument("--consultas", default="data/consultas.jsonl")
            s.add_argument("--ablacion", action="store_true", help="compara la línea base sin reglas")
            s.add_argument("--json", action="store_true", help="imprime las métricas en JSON")

    args = p.parse_args(argv)
    if getattr(args, "embeddings", "local") == "openai" and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Falta OPENAI_API_KEY. Usa --embeddings local para correr sin red.")
    args.func(args)


if __name__ == "__main__":
    main()
