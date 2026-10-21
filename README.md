# catalog-matching-embeddings

Matching de descripciones comerciales libres contra un catálogo de productos, con **candidatos
rankeados** y **revisión humana por excepción**. Es una recreación, con datos 100 % sintéticos, de un
sistema que diseñé y llevé a producción: cruzaba las glosas que los compradores escriben en sus órdenes
de compra con un catálogo de más de 10.000 productos. En el caso real, **más del 85 % de las glosas
quedó con match automático** y el resto llegó a una persona con los mejores candidatos ya ordenados.

> Este repositorio no contiene código, datos ni nombres de ningún cliente. El catálogo, las marcas y las
> glosas son inventados.

## El problema

El comprador no escribe el SKU. Escribe «gte nitr T-M s/polvo cj x100», «jer 10cc c/ag 21G x 1½» o
«bránulas N°18 c/aletas». La misma jeringa aparece como `10 ml`, `10cc` o `10 mL`, una aguja de
`1 1/2"` aparece como `38 mm`, faltan la marca o la presentación y hay errores de tipeo. Hay que llevar
cada glosa a un SKU de un catálogo de miles de productos casi idénticos (la sonda de 16 Fr y la de
18 Fr se diferencian en un número). Hacerlo a mano no escala. Automatizarlo todo sin control tampoco
sirve: un SKU equivocado termina en una cotización o un despacho equivocados.

## La solución

```text
glosa del comprador ──► normalización ──► top-k por similitud ──► regla de medidas ──► enrutamiento
«jer 10cc c/ag 21G     cc→ml, "→mm,       TF-IDF local (demo)     10 ml ≠ 5 ml: castiga  ├─ automático: score ≥ umbral
 x 1½ cj 100»          abreviaturas,      o embeddings +          4 1/2" ≈ 115 mm: suma  │  y margen ≥ mínimo contra el
                       sinónimos          pgvector (producción)                          │  mejor rival distinguible
                                                                                         └─ persona: top-3 candidatos
```

- **Normalización** (`normalizacion.py`): unidades a una forma canónica (`cc` → `ml`, litros → `ml`,
  pulgadas → `mm`, `Fr`, calibres, tallas, `cj x100` → `100un`), abreviaturas y sinónimos (`gte`,
  `bránula`, `arandela`, `volcanita`), concordancia de género y negaciones como un solo token
  (`sin polvo` → `sinpolvo`) para que el «sin» no se pierda.
- **Recuperación** (`vectorizador.py`): TF-IDF de palabras más n-gramas de caracteres, implementado con
  la biblioteca estándar, con índice invertido. Los n-gramas toleran errores de tipeo; cada palabra pesa
  según su IDF y no según su largo. El puntaje mezcla coseno y cobertura de la glosa, porque los
  compradores omiten atributos y el coseno solo castiga lo que falta.
- **Regla de medidas** (`matcher.py`): compara los atributos medibles de la glosa con los de cada
  candidato, con tolerancia de redondeo. Una medida en conflicto baja el puntaje y una medida pedida que
  el candidato no tiene impide automatizar.
- **Enrutamiento por excepción** (`matcher.enrutar`): solo se automatiza si el mejor candidato supera
  el umbral y le saca margen al mejor rival **distinguible**. Si la glosa no dice marca ni presentación,
  «caja 100 marca A» y «caja 200 marca B» empatan, pero ambos cumplen lo pedido y ese empate no bloquea.
  Todo lo demás va a una persona con los tres mejores candidatos y el motivo.
- **Embeddings opcionales** (`embeddings.py`): `text-embedding-3-small` de OpenAI vía `urllib`, sin SDK,
  para re-puntuar los candidatos, y `sql/pgvector_esquema.sql` con la tabla y el índice HNSW para
  producción. El demo corre sin claves, sin red y sin Postgres.
- **Generador sintético** (`sintetico.py`) y **evaluación** (`evaluacion.py`): catálogo combinatorio,
  glosas etiquetadas con su SKU correcto y casos sin match.

## Resultados medidos (modo offline)

**Datos.** Catálogo de 9.994 SKU en 29 familias de insumos médicos e industriales y 10 marcas
ficticias. Set de prueba de 1.000 glosas (`--semilla 42`): 92 % usan otra forma de escribir algún
atributo, 41 % traen errores de tipeo, 37 % omiten algún atributo y 13 % **no tienen match** en el
catálogo (un termómetro, o una jeringa de 2 ml que no existe). El umbral (0,85) y el margen (0,05) se
eligieron sobre un set de validación distinto (`--semilla 7`), no sobre el de prueba.

Una respuesta cuenta como correcta si el SKU cumple todo lo que el comprador escribió: si no dijo la
marca, cualquier marca del mismo producto sirve.

| Métrica | TF-IDF local + reglas |
|---|---:|
| Recall@1 / @3 / @10 (recuperación) | 93,0 % / 97,5 % / 99,2 % |
| Tasa de automatización | 53,4 % |
| Precisión de lo automatizado | **98,5 %** (8 errores en 534) |
| Glosas sin match automatizadas por error | **0** de 129 |
| Recall@3 en la cola de revisión | 94,1 % |
| Glosas con match resueltas o a un clic (automático correcto o SKU en el top-3) | 96,8 % |

La curva sirve para elegir el punto de operación según el costo de un error:

| Umbral | Automatización | Precisión de lo automatizado | Errores automáticos | Recall@3 en la cola |
|---:|---:|---:|---:|---:|
| 0,70 | 66,0 % | 95,8 % | 28 | 92,0 % |
| 0,75 | 63,6 % | 96,9 % | 20 | 92,8 % |
| 0,80 | 59,2 % | 97,8 % | 13 | 93,9 % |
| **0,85** | **53,4 %** | **98,5 %** | **8** | **94,1 %** |
| 0,90 | 45,1 % | 98,9 % | 5 | 95,0 % |
| 0,95 | 31,8 % | 98,7 % | 4 | 96,2 % |

Qué aporta cada pieza (mismo umbral y margen):

| Configuración | Recall@1 | Recall@3 | Automatización | Precisión de lo automatizado |
|---|---:|---:|---:|---:|
| TF-IDF sin reglas | 72,0 % | 85,8 % | 2,9 % | 100,0 % |
| + normalización y regla de medidas | 93,0 % | 97,5 % | 25,3 % | 100,0 % |
| + margen contra rivales distinguibles | 93,0 % | 97,5 % | 53,4 % | 98,5 % |

Tres glosas del set de prueba muestran cómo se comporta:

> «Se solicita tornillos cab. plana 1 1/2 plg atorroscante #6 bicromatado» → automático:
> `Tornillo autorroscante cabeza plana #6 1 1/2" bicromatado caja 500 un` (score 0,97).

> «10 cajas de compresa de gasa 10x10cm 8 caps esteril paquete x100» → revisión: «caps» no está en
> las reglas y el score queda en 0,75, pero el SKU correcto es el primero de los tres candidatos.

> «abrazadera zincadda tralmed 12-20mm» → **error automático**: el tipeo cayó justo en el único
> atributo que distinguía a los candidatos y el sistema eligió la versión inoxidable.

El último caso explica la mayor parte de los errores que quedan: ruido sobre la palabra que decide.
Ahí un embedding semántico y las correcciones de los revisores rinden más que agregar reglas.

**Por qué el demo automatiza 53 % y el caso real más de 85 %.** El set sintético está hecho para ser
difícil (41 % de glosas con tipeos, 37 % con atributos omitidos y 13 % sin match) y el TF-IDF no
entiende sinónimos que no estén en las reglas; el sistema real usaba embeddings semánticos. Las dos
cifras no son comparables y no lo pretenden. La precisión estricta contra el SKU de origen exacto es 71,0 %:
la diferencia con el 98,5 % corresponde a glosas que no dicen marca o presentación, donde cualquier SKU
que cumpla lo pedido es válido. No publico cifras con embeddings de OpenAI: el modo está implementado,
pero aquí solo informo lo que se puede reproducir sin claves.

## Cómo usarlo

```bash
# datos sintéticos (el catálogo y los dos sets ya vienen en data/)
PYTHONPATH=src python -m catalog_matching generar --semilla 42
PYTHONPATH=src python -m catalog_matching generar --semilla 7 --archivo-consultas consultas_validacion.jsonl

# buscar una glosa
PYTHONPATH=src python -m catalog_matching buscar "gte nitr T-M s/polvo azul cj x100"

# evaluar: métricas, curva y ablación
PYTHONPATH=src python -m catalog_matching evaluar --ablacion
PYTHONPATH=src python -m catalog_matching evaluar --umbral 0.80 --margen 0.05

# con embeddings de OpenAI (opcional; recalibra el umbral con la curva)
export OPENAI_API_KEY=...
PYTHONPATH=src python -m catalog_matching evaluar --embeddings openai

# exportar el catálogo con vectores a SQL para pgvector (no necesita Postgres)
python scripts/exportar_pgvector.py                         # vectores locales (hashing, 256 dim.)
python scripts/exportar_pgvector.py --embeddings openai     # text-embedding-3-small, 1536 dim.
psql "$DATABASE_URL" -f output/pgvector_catalogo.sql

python -m unittest discover -s tests
```

La evaluación de 1.000 glosas contra 9.994 SKU tarda unos 7 segundos en un portátil. Las salidas quedan
en `output/`: `decisiones.jsonl` (ruta, score, margen y motivo de cada glosa), `cola_revision.csv` (lo
que ve la persona: la glosa, el motivo y los tres candidatos) y `reporte.md`.

## Qué llevé a producción en el caso real

- Embeddings de OpenAI del catálogo guardados en PostgreSQL con pgvector y búsqueda top-k por
  similitud coseno.
- Una API en FastAPI que entrega los candidatos rankeados y una interfaz en React para la revisión por
  excepción: la persona elige o corrige entre los mejores candidatos.
- Más del 85 % de match automático sobre un catálogo de más de 10.000 productos.

## Stack

Python 3.10+ (solo biblioteca estándar) · TF-IDF de n-gramas de caracteres · OpenAI embeddings
(opcional) · pgvector (esquema de referencia) · unittest. En el caso real: Python, OpenAI, pgvector,
FastAPI y React.

---

**Nicolás González Rojas** · Head of Data & BI · [LinkedIn](https://www.linkedin.com/in/nicolas-gonzalez-rojas)
