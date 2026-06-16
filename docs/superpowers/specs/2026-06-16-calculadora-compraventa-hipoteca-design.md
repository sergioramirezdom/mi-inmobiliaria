# Calculadora de Compraventa e Hipoteca

**Fecha:** 2026-06-16  
**Sprint:** 9  
**Estado:** Aprobado por usuario

---

## Objetivo

Añadir una calculadora financiera que estime los gastos totales de compraventa, los gastos hipotecarios y la cuota mensual resultante. Disponible como página independiente y como modal desde cada tarjeta de propiedad.

---

## Arquitectura

```
app/
├── utils/
│   ├── __init__.py
│   └── calculadora.py        # lógica pura, sin Streamlit
├── pages/
│   ├── 2_propiedades.py      # + botón 🧮 en tarjeta → modal
│   └── 6_calculadora.py      # página standalone
```

`utils/calculadora.py` expone funciones puras (sin efectos secundarios, sin imports de Streamlit):

```python
def calcular_compraventa(precio, aportacion, itp_pct, notaria, registro, agencia_pct) -> dict
def calcular_gastos_hipoteca(prestamo, comision_apertura, gestoria, tasacion, registro_hip, ajd_pct) -> dict
def calcular_aportacion_necesaria(precio, financiacion_pct, total_gastos_a, total_gastos_b) -> float
def calcular_hipoteca(prestamo, tipo_interes_final, plazo_anos) -> dict
```

---

## Bloque A — Gastos de Compraventa

### Inputs

| Campo | Tipo | Default |
|-------|------|---------|
| Precio de la vivienda | € | — |
| Aportación inicial | € | calculada (ver abajo) |
| ITP | selector 3.5% / 6% / 7% | 7% |
| Notaría | € | 700 |
| Registro | € | 350 |
| Agencia | % sobre precio | 0 |

### Cálculos

```
itp_importe     = precio × itp_pct
agencia_importe = precio × agencia_pct
total_a         = itp_importe + notaria + registro + agencia_importe
```

---

## Bloque B — Gastos Hipotecarios

### Inputs

| Campo | Tipo | Default |
|-------|------|---------|
| Comisión de apertura | € | 0 |
| Gestoría | € | 350 |
| Tasación | € | 450 |
| Registro hipoteca | € | 0 |
| AJD | % sobre préstamo | 1.0% |

### Cálculos

```
ajd_importe  = prestamo_solicitado × ajd_pct
total_b      = comision_apertura + gestoria + tasacion + registro_hip + ajd_importe
```

---

## Aportación inicial y préstamo solicitado

### Modo manual
El usuario introduce directamente la aportación inicial.

### Modo por % de financiación
Selector: **80% / 90% / 100%** de financiación del precio.

```
banco_financia       = precio × financiacion_pct
aportacion_necesaria = precio - banco_financia + total_a + total_b
prestamo_solicitado  = precio × financiacion_pct
```

Esto muestra al usuario el **mínimo de ahorros necesarios** para afrontar la compra con ese nivel de financiación, incluyendo todos los gastos.

### Total general

```
prestamo_solicitado = precio + total_a + total_b - aportacion_inicial
coste_total         = precio + total_a + total_b
```

---

## Calculadora de Hipoteca (amortización francesa)

### Inputs

| Campo | Tipo | Default |
|-------|------|---------|
| Préstamo solicitado | € | calculado arriba, editable |
| Tipo de interés base | % | 3.0% |
| Bonificaciones | lista dinámica (nombre + reducción %) | vacía |
| Tipo final | % | base − Σ bonificaciones (calculado) |
| Plazo | slider 5–40 años | 30 |

### Bonificaciones
Lista dinámica: el usuario añade filas con `st.data_editor` o botón "➕ Añadir bonificación". Cada fila: nombre (nómina, seguro vida, seguro hogar, aportación fondo, etc.) + reducción en %.

### Cálculos (amortización francesa)

```
tipo_mensual = tipo_final / 12 / 100
n            = plazo_anos × 12
cuota        = prestamo × (tipo_mensual × (1+tipo_mensual)^n) / ((1+tipo_mensual)^n - 1)
total_pagado = cuota × n
total_intereses = total_pagado - prestamo
```

### Outputs mostrados
- Cuota mensual
- Total pagado al banco
- Total intereses
- % intereses sobre capital
- Tabla de amortización: primeros 12 meses visible, resto en expander (solo en página standalone)

---

## UI — Página standalone (`6_calculadora.py`)

Layout **dos columnas**:

**Columna izquierda — Formularios**
1. Sección "A) Gastos de compraventa" (inputs con defaults)
2. Selector de financiación (manual / 80% / 90% / 100%) → calcula aportación mínima
3. Sección "B) Gastos hipotecarios" (inputs con defaults)
4. Sección "Calculadora hipoteca" (tipo base, bonificaciones, plazo)

**Columna derecha — Resumen en tiempo real**
- Métricas: Total gastos A, Total gastos B, Total gastos A+B
- Préstamo solicitado
- Aportación inicial necesaria (destacada si modo %)
- Cuota mensual (métrica grande y destacada)
- Total pagado / Total intereses
- Expander "📊 Tabla de amortización"

---

## UI — Modal desde tarjeta de propiedad

- Botón `🧮` en cada tarjeta (4ª posición junto a ✏️ 🔗 ❌)
- Abre `@st.dialog("🧮 Calculadora", width="large")`
- El precio de la propiedad se pre-rellena automáticamente
- Layout una sola columna (formularios arriba, resumen abajo)
- Sin tabla de amortización
- Selector de financiación incluido (para ver aportación necesaria)

---

## Comportamiento de la aportación mínima

Cuando el usuario selecciona % de financiación:
- Se muestra en un `st.info` o `st.metric` destacado:
  > "Con financiación del 80%, necesitas al menos **€45.320** de ahorros (entrada + todos los gastos)"
- La aportación se actualiza reactivamente al cambiar precio, gastos o % de financiación

---

## Fuera de alcance

- Guardar simulaciones en BD
- Comparativa entre varios escenarios simultáneos
- Cálculo de subrogación o novación
- Integración con tipos de interés en tiempo real

---

## Archivos a crear/modificar

| Archivo | Acción |
|---------|--------|
| `app/utils/__init__.py` | crear |
| `app/utils/calculadora.py` | crear |
| `app/pages/6_calculadora.py` | crear |
| `app/pages/2_propiedades.py` | modificar — añadir botón 🧮 y modal |
