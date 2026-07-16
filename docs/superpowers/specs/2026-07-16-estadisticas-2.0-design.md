# Estadísticas 2.0 — Diseño

**Fecha:** 2026-07-16
**Estado:** Aprobado por Sergio (pendiente de plan de implementación)

## Objetivo

Reescribir la página de Estadísticas (`app/pages/4_estadisticas.py`) como un cuadro de mando orientado a **decisión de compra**: entender cómo respira el mercado (entradas, ventas, precios, presión), ver tendencias de precio por barrio, y obtener un rango de oferta sugerido y justificado para cada propiedad favorita, utilizable como argumentario en una negociación o contraoferta.

**Restricciones:** Streamlit + **Plotly** para todos los gráficos (única dependencia nueva: `plotly`, añadida a `requirements.txt`; renderizado vía `st.plotly_chart`, compatible con Streamlit Cloud). Volumen pequeño (<500 propiedades). La valoración es una **heurística transparente por comparables**, no un modelo estadístico: cada ajuste se muestra y justifica; nada de regresiones.

**Estilo de gráficos:** todos los charts comparten un tema Plotly propio definido una
vez en `app/ui/chart_theme.py`: paleta de colores consistente, fondo transparente
(se integra con el tema claro/oscuro de Streamlit), tooltips unificados
(`hovermode="x unified"` en series temporales), sin barra de herramientas de Plotly
salvo zoom/pan, tipografía y márgenes compactos, y formato español de números
(separador de miles con punto, sufijo €). Barras con esquinas y colores por
categoría; líneas con suavizado ligero y marcadores en hover; deltas/tendencias en
verde/rojo coherentes con la semántica compradora definida en §2.

## 1. Estructura de la página

Desaparece el sidebar actual (checkboxes "Excluir descartadas" / "Solo favoritas"):
las descartadas siempre cuentan como oferta de mercado en los análisis (son mercado
aunque no interesen), y "solo favoritas" queda cubierto por la pestaña Ofertas.

```
📊 Mercado
[📈 Pulso] [🗺️ Zonas] [🎯 Ofertas]    ← st.segmented_control con required=True,
                                        default "pulso" (mismo patrón que Propiedades 2.0)
```

## 2. Pestaña 📈 Pulso

**KPIs con delta 30 días vs 30 días anteriores** (`st.metric(delta=...)`):

| KPI | Fuente | Delta |
|---|---|---|
| Nuevas propiedades (30d) | count por `fecha_scraping` | vs 30d anteriores |
| Ventas (30d) | count por `fecha_baja` (activa=False) | vs 30d anteriores |
| €/m² mediano de activas | precio/superficie de activas hoy | vs mediana de hace 30d reconstruida desde `PrecioHistorico` |
| Bajadas de precio (30d) | nº de propiedades con al menos un descenso de precio registrado en `PrecioHistorico` dentro de la ventana | vs 30d anteriores (mismo criterio) |
| Días en mercado mediano | fecha_baja−fecha_scraping de vendidas en la ventana | vs vendidas de los 30d anteriores |

Deltas con `delta_color` correcto para un comprador: más oferta/bajadas/días = verde
(mercado comprador); €/m² subiendo = rojo.

**Gráficos (Plotly, tema común de §Estilo):**
1. Entradas nuevas por semana (últimas 12 semanas) — barras con tooltip
   "semana del D/M: N nuevas".
2. Ventas por mes (todo el histórico disponible) — barras.
3. Evolución mensual del €/m² mediano de activas — línea con área degradada bajo la
   curva y tooltip unificado; calculado desde `PrecioHistorico` unido a la
   superficie de cada propiedad (refleja bajadas de precio, no solo altas nuevas).
   Para cada mes: mediana de (último precio registrado del mes por propiedad /
   superficie), sobre propiedades con superficie conocida.

Una línea de lectura interpretativa bajo los KPIs (texto fijo condicionado a los
deltas, p. ej. "Más oferta y más bajadas que el mes pasado: margen para negociar").

## 3. Pestaña 🗺️ Zonas

Granularidad: campo `barrio`. Los barrios con <3 propiedades activas se agrupan en
«Otros». Propiedades sin barrio se agrupan en «Sin zona».

**Tabla por barrio** (ordenable, `st.dataframe`):

| Columna | Cálculo |
|---|---|
| Activas | count activas (incluye descartadas por el usuario) |
| €/m² mediano | mediana de precio/superficie de activas |
| Precio mediano | mediana de precio de activas |
| Vendidas (6m) | count con fecha_baja en los últimos 180 días |
| Días en mercado | mediana de fecha_baja−fecha_scraping de esas vendidas |
| % con bajada | precio_anterior≠NULL sobre activas |
| Tendencia €/m² | Δ% de €/m² mediano: últimos 90 días vs 90 anteriores (desde PrecioHistorico), con ▲/▼/= |

**Gráfico de evolución:** multiselect de barrios → líneas Plotly de €/m² mediano
mensual por barrio (misma serie mensual que Pulso, segmentada por barrio): una
línea coloreada por barrio, leyenda clicable para aislar series, tooltip unificado
por mes. Aviso bajo el gráfico si algún barrio seleccionado tiene meses con <3
propiedades ("líneas con pocos datos, interpretar con cautela" listando cuáles).

## 4. Pestaña 🎯 Ofertas

Selectbox de favoritas (`favorita=True`), formato "título — precio". Si no hay
favoritas: mensaje invitando a marcar alguna en Propiedades. Para la seleccionada:

### a) Selección de comparables

Universo: activas (incluidas descartadas) + vendidas con `fecha_baja` en los últimos
180 días; siempre con precio y superficie conocidos; excluida la propia favorita.

Criterios en cascada, usando el primero que alcance **mínimo 4 comparables**:
1. mismo `barrio` + mismo `tipo_propiedad` + superficie dentro de ±40% de la favorita
2. mismo `barrio` + superficie ±40% (sin tipo)
3. mismo `municipio` + mismo `tipo_propiedad` + superficie ±40%
4. mismo `municipio` + superficie ±40%

La UI muestra siempre qué nivel se usó y cuántos comparables hay. Si ni el nivel 4
llega a 4 comparables, se calcula igualmente con los que haya (mínimo 1) pero con un
aviso destacado de baja fiabilidad. Con 0 comparables, o si la favorita no tiene
superficie o precio, no se valora y se explica el motivo exacto.

### a-bis) Solicitud de datos que faltan

Antes de valorar, se comprueban los campos de la favorita que afectan a la calidad
de la valoración, en dos niveles:

- **Imprescindibles** (sin ellos no hay valoración): `precio`, `superficie_m2`.
- **Mejoran los comparables**: `barrio`, `tipo_propiedad`.

Si falta alguno, la pestaña muestra un formulario inline (`st.form`) titulado
"📝 Completa datos para afinar la valoración" con un input por campo ausente:
`superficie_m2` (number_input), `precio` (number_input), `barrio` (selectbox con
los barrios existentes vía `PropiedadCRUD.get_distinct_barrios` + opción de texto
libre), `tipo_propiedad` (selectbox con los tipos distintos existentes). Al
guardar, se persiste con `PropiedadCRUD.update`, se limpia la caché de datos de la
página y se re-ejecuta (st.rerun), recalculando la valoración con los nuevos datos.

- Si faltan imprescindibles: el formulario aparece EN LUGAR de la valoración, con
  el motivo ("No se puede valorar sin superficie").
- Si solo faltan los de mejora: la valoración se muestra igualmente (con el nivel
  de comparables degradado que corresponda) y el formulario aparece plegado en un
  expander debajo, indicando qué mejoraría ("Añadir el barrio afinaría los
  comparables del nivel 4 al nivel 1").

### b) Valor estimado

`valor_estimado = mediana(€/m² de comparables) × superficie de la favorita`

### c) Rango de oferta sugerido

Ajustes de presión, acumulativos y mostrados como desglose línea a línea:

| Señal | Ajuste |
|---|---|
| Días en mercado de la favorita > mediana de días en mercado de las vendidas de su zona (nivel de comparables usado) | −1% por cada 30 días completos de exceso, tope −5%. Si no hay vendidas para calcular la mediana de referencia, este ajuste no aplica y se indica. |
| La favorita ya bajó de precio (`precio_anterior` > `precio`) | −2% fijo |
| €/m² de la favorita > €/m² mediano de comparables | Sin descuento adicional (evita doble conteo): se muestra el % de sobreprecio como argumento de negociación |

Resultado:
- **Máximo razonable** = min(valor_estimado, precio anunciado)
- **Oferta inicial sugerida** = Máximo razonable × (1 − suma de descuentos)

Presentación: los dos números grandes (`st.metric`), un **gráfico de rango** Plotly
(barra horizontal tipo bullet: eje de precio con marcadores para oferta inicial,
máximo razonable, valor estimado y precio anunciado, y los comparables como puntos
sobre el mismo eje), desglose línea a línea de cada
ajuste con su justificación en texto, y debajo la **tabla de comparables** (título,
barrio, tipo, m², precio, €/m², estado activa/vendida, días en mercado si vendida,
enlace al anuncio) para auditar la base del cálculo.

Disclaimer fijo en la UI: heurística orientativa basada en la oferta anunciada
observada, no una tasación.

## 5. Arquitectura y código

Mismo patrón que Propiedades 2.0 — lógica pura testeable separada de la página:

| Archivo | Responsabilidad |
|---|---|
| `app/pages/4_estadisticas.py` | Orquestación: pestañas, selectores, métricas y render de gráficos |
| `app/ui/market_stats.py` | Cálculos de Pulso y Zonas: funciones puras (entrada: lista de dicts / DataFrames; salida: DataFrames/dicts). Sin Streamlit, sin BD, sin Plotly. |
| `app/ui/offer_advisor.py` | Comparables + valoración + rango: funciones puras. Sin Streamlit, sin BD, sin Plotly. |
| `app/ui/chart_theme.py` | Tema Plotly común (colores, layout, formato español) y constructores de figuras: `line_chart(df, ...)`, `bar_chart(df, ...)`, `offer_range_chart(...)` que devuelven `go.Figure` listas para `st.plotly_chart`. |

Datos: dos fetches cacheados en la página con `@st.cache_data(ttl=300)` que
devuelven listas de dicts planos (nunca objetos ORM): uno de `Propiedad` (campos
necesarios) y otro de `PrecioHistorico` (propiedad_id, precio, fecha). Todo el
cálculo posterior es pandas puro en memoria — con <500 propiedades es trivial.

## 6. Manejo de errores

- try/except global de página como el actual.
- Cada bloque cubre su caso vacío con mensaje específico: sin vendidas, sin
  historial de precios, barrio sin datos, sin favoritas, favorita sin
  superficie/precio, cero comparables.
- División por cero/NULL: los cálculos de €/m² exigen superficie > 0.

## 7. Tests

- `tests/test_market_stats.py`: deltas 30/30 (incluyendo ventanas vacías), serie
  semanal de entradas, serie mensual de ventas, serie mensual de €/m² desde
  historial (último precio del mes por propiedad), agregados por barrio (incluida
  agrupación «Otros» <3 activas y «Sin zona»), tendencia 90/90.
- `tests/test_offer_advisor.py`: cascada de comparables (cada nivel, umbral de 4,
  caída al siguiente), exclusión de la propia favorita, filtro ±40% superficie,
  ventana 180 días para vendidas, valor estimado, cada ajuste por separado y
  combinados, tope −5%, máximo razonable = min(estimado, anunciado), casos sin
  datos (sin superficie, sin comparables, sin vendidas de referencia).
- `tests/test_chart_theme.py`: los constructores devuelven `go.Figure` con el nº de
  trazas esperado y el layout del tema aplicado (smoke tests; el aspecto visual se
  valida a mano).
- Patrón de tests existente: `sys.path.insert` al dir `app`, funciones puras sin BD.

## Fuera de alcance

- Regresión/modelos estadísticos de valoración.
- Datos externos (Idealista API, catastro, testigos de portales).
- Mapa geográfico (latitud/longitud).
- Cambios en scrapers, alertas u otras páginas.
