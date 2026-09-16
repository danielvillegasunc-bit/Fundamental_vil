# Motor de Análisis Fundamental Sectorial — MVP

## Cómo correrlo

1. Instalar dependencias:
   ```
   pip install -r requirements.txt
   ```
2. Ejecutar:
   ```
   streamlit run app.py
   ```
3. Se abre en el navegador (por defecto http://localhost:8501).

## Cómo extender la base de datos

Toda la "base de datos" vive en dos diccionarios al inicio de `app.py`:

- `SECTOR_MATRIX`: agregar sectores/subsectores nuevos con sus ratios
  principales/secundarios/con cautela/no recomendados (Sección 4 del Manual
  de Referencia).
- `RATIO_BENCHMARKS`: agregar ratios nuevos con sus cortes de nivel (escala
  de 6 niveles) y, si corresponde, overrides específicos por subsector.

No hace falta tocar el motor de reglas (`interpretar_ratio`,
`analizar_relaciones`, etc.) para agregar sectores o ratios — está separado
de los datos a propósito para que el proyecto pueda escalar la cobertura
sectorial de forma incremental.

## Qué hace y qué NO hace

Hace: clasifica cada ratio ingresado según relevancia sectorial, lo ubica en
una escala de 6 niveles contra un benchmark (marcado como convención de
mercado o inferencia propia), señala advertencias e información faltante,
detecta relaciones/inconsistencias entre ratios, y arma un diagnóstico
descriptivo.

NO hace: no calcula percentiles/z-scores contra una distribución real de
pares (requeriría conectar una fuente de datos de mercado en vivo — ver
Sección 19 del Manual, "Intervalos dinámicos", como próximo paso), no emite
recomendaciones de compra/venta, y los benchmarks son puntos de partida a
validar y actualizar periódicamente contra fuentes primarias.
