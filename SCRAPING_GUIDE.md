# Guía de Scraping - Configuración de Fuentes

## Problema: Auto-detect no funciona para todos los sitios

Algunos sitios web tienen estructuras HTML que el auto-detect genérico no puede identificar. En esos casos, necesitas proporcionar **selectores CSS personalizados**.

## Solución: Usar configuración JSON en campo "Notas"

### Ejemplo 1: Puerto Inmobiliaria

Para que funcione con https://www.puertoinmobiliaria.es/, usa estos selectores:

```json
{
  "selectors": {
    "property_container": "article.propiedad",
    "link": "div[onclick]",
    "price": "span",
    "title": "a"
  }
}
```

**Resultado**: ✅ 12 propiedades detectadas

### Cómo encontrar los selectores correctos

1. **Abre las Developer Tools** (F12 en Chrome/Firefox)
2. **Inspecciona un elemento de propiedad** (clic derecho > Inspeccionar)
3. **Identifica patrones**:
   - `property_container`: El elemento que contiene cada propiedad (ej: `<article class="propiedad">`)
   - `link`: Dónde está la URL (ej: atributo `href` en `<a>` o `onclick` en `<div>`)
   - `price`: Dónde está el precio (ej: `<span class="price">€199.000</span>`)
   - `title`: Dónde está el título (ej: `<h2>Piso en Centro</h2>`)

4. **Usa selectores CSS válidos**:
   - `.clase` = por clase
   - `#id` = por ID
   - `elemento` = por etiqueta
   - `[atributo]` = por atributo
   - `elemento.clase` = combinaciones

### Selectores comunes que ya funcionan

- `.propiedad`, `.property`, `.listing` = contenedor principal
- `.precio`, `.price`, `.amount` = precio
- `h2`, `h3`, `a` = título
- `.m2`, `.size`, `.superficie` = metros cuadrados

### Si nada funciona

El sitio probablemente **usa JavaScript para cargar contenido dinámicamente**. En ese caso:
- Tipo de scraper a usar: `playwright` (en futuras versiones)
- O reportar el sitio como problema

## Paso a paso en la UI

1. **Ve a "Gestión de Fuentes"** en la UI de Streamlit
2. **Añade una nueva fuente**:
   - Nombre: "Puerto Inmobiliaria"
   - URL: "https://www.puertoinmobiliaria.es/"
   - Tipo: "generic"
   - Notas (JSON):
     ```json
     {
       "selectors": {
         "property_container": "article.propiedad",
         "link": "div[onclick]",
         "price": "span"
       }
     }
     ```

3. **Haz clic en "Probar scraping"**
4. **Verifica los resultados** en la tabla de propiedades nuevas

## Información técnica

El JSON en "Notas" se parsea automáticamente y configura el `GenericScraper` con:
- `SelectorsConfig`: Selectores CSS personalizados
- `PatternsConfig`: Patrones regex como fallback
- `ScraperConfig`: Timeout, retries, headers

**Flujo**:
1. GenericScraper busca usando selectores CSS
2. Si no encuentra con CSS, intenta regex patterns
3. Si tampoco funciona, la propiedad se salta con warning

