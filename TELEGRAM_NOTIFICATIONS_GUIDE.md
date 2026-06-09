# 🔔 Telegram Notifications with Advanced Filtering

## What We Built

### FilterMatcher — Smart Property Matching
```
Criterios: precio_max=200000, habitaciones=3, barrio="Crevillet"

Property: "Piso 150m² 3 hab - €180.000 - Centro"
   ❌ REJECT: barrio != "Crevillet"

Property: "Casa 120m² 3 hab - €195.000 - Crevillet"  
   ✅ MATCH: Todos los criterios coinciden
   📤 ENVIAR NOTIFICACIÓN
```

### TelegramNotifier — Multi-Format Alerts
- Summary notifications (counts + stats)
- Detailed property lists (título, precio, m², baños, dirección, URL)
- Filter-based alerts (notifies when filter has matches)
- Graceful error handling

### Alerts Management UI (Streamlit)
Complete interface to:
- ➕ Create new alert filters
- 🔧 Set advanced criteria
- 🟢 Activate/Deactivate alerts
- 🗑️ Delete alerts
- 📋 View all active alerts

---

## How It Works

### Step 1: Create Alert (Streamlit)
```
User creates filter:
  Name: "Nuevo en Crevillet 3 hab"
  Precio máximo: €200.000
  Zona: Crevillet
  Habitaciones: 3+
  (+ optional: m², baños, estado, amenidades)
```

### Step 2: Scheduler Runs (Automatic)
```
Cada minuto (or 08:00/20:00 UTC):
1. Scrapeea Puerto Inmobiliaria
2. Encuentra 12 propiedades nuevas
3. Para cada filtro activo:
   - Chequea si propiedades coinciden
   - Si 3+ coinciden con el filtro:
     → ENVIAR NOTIFICACIÓN
```

### Step 3: User Gets Notified (Telegram)
```
Message recibida:
🎯 Puerto Inmobiliaria
✅ Nuevas: 12
⚠️ Duplicadas: 85

🔍 Filtros Aplicados:
• Nuevo en Crevillet 3 hab

🏠 Nuevo en Crevillet 3 hab
Found 3 matching properties:

1. Casa nueva 150m² 4 hab - €185.000
   📍 Crevillet, Centro
   🔗 [Ver ficha](url)

2. Piso nuevo 120m² 3 hab - €160.000
   📍 Avenida del Ejercito
   🔗 [Ver ficha](url)

3. Duplex 140m² 3 hab - €195.000
   📍 Crevillet, Este
   🔗 [Ver ficha](url)
```

---

## Available Filter Criteria

| Criterio | Type | Example | Behavior |
|----------|------|---------|----------|
| `precio_min` | float | 150000 | Mínimo precio (€) |
| `precio_max` | float | 200000 | Máximo precio (€) |
| `m2_min` | float | 80 | Mínimo tamaño (m²) |
| `m2_max` | float | 150 | Máximo tamaño (m²) |
| `habitaciones` | int | 3 | Mínimo habitaciones |
| `habitaciones_max` | int | 4 | Máximo habitaciones |
| `banos` | int | 2 | Mínimo baños |
| `barrio` | string | "Crevillet" | Zona (búsqueda parcial) |
| `tipo_propiedad` | string | "Casa" | Tipo (Piso, Casa, etc) |
| `estado` | string | "Nueva" | Condición |
| `año_construccion_min` | int | 2020 | Año mínimo construcción |
| `gastos_comunidad_max` | float | 200 | Máximo gastos/mes (€) |
| `amenidades` | string | "Ascensor" | Amenidades (comma-separated) |

### Logic: ALL criteria must match (AND)
```
Si filtro tiene:
  - precio_max = 200000
  - habitaciones = 3
  - barrio = "Crevillet"

Property solo coincide si:
  - Precio <= 200.000 AND
  - Habitaciones >= 3 AND
  - Barrio contiene "Crevillet"
```

---

## 🚀 How to Use

### 1. Create Filter in Streamlit
```
Go to: http://localhost:8501 → Alertas

1. Set "Nombre de la alerta": "Casa barata en Crevillet"
2. Set criteria:
   - Precio máximo: €200.000
   - Zona: Crevillet
   - Mínimo habitaciones: 3
3. Click "✅ Crear Alerta"
```

### 2. Start Scheduler (Background)
```bash
python scripts/scheduler.py
```

### 3. Receive Telegram Notifications
```
When new properties match your filter:
→ Get Telegram message with details
→ Click link to view property
```

---

## 📋 Example Filters

### Inversor Inmobiliario
```json
{
  "precio_max": 100000,
  "m2_min": 50
}
// Any property cheap but with decent size
```

### Primera Vivienda en Centro
```json
{
  "barrio": "Centro",
  "precio_max": 250000,
  "habitaciones": 2,
  "estado": "Buen estado"
}
// Comfortable 2-bedroom in the center
```

### Rentable Property
```json
{
  "tipo_propiedad": "Apartamento",
  "precio_max": 120000,
  "habitaciones": 1,
  "amenidades": "Ascensor"
}
// Studio with elevator (easy to rent)
```

### Luxury Home
```json
{
  "precio_min": 500000,
  "m2_min": 200,
  "habitaciones": 4,
  "amenidades": "Piscina,Terraza"
}
// Big premium property with amenities
```

---

## 🔧 Configuration

### Environment Variables (.env)
```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklmNOpqrsTUVwxyz...
TELEGRAM_CHAT_ID=-987654321
DATABASE_URL=postgresql://...
```

### How to Get Telegram Credentials

1. **Create Bot**
   - Message @BotFather on Telegram
   - Create new bot: `/newbot`
   - Get token (keep it secret!)

2. **Get Chat ID**
   - Message your bot: `/start`
   - Forward message from @userinfobot
   - Copy your chat ID

---

## 📊 Filter Matching Examples

### Example 1: Simple Price Filter
```
Filter: precio_max = 200000

✅ Property €150.000 → Match
❌ Property €250.000 → No match
```

### Example 2: Zone + Price
```
Filter: barrio="Centro", precio_max=200000

✅ "Piso Centro €150k" → Match (both)
❌ "Piso Periferia €150k" → No match (wrong zone)
❌ "Piso Centro €250k" → No match (too expensive)
```

### Example 3: Complete Filter
```
Filter: 
  barrio="Crevillet"
  precio_max=200000
  habitaciones=3
  amenidades="Ascensor"

✅ "Casa Crevillet 3hab €180k Ascensor" → MATCH
❌ "Casa Crevillet 2hab €180k" → No (hab count)
❌ "Piso Centro 3hab €180k Ascensor" → No (zone)
```

---

## 🔍 How Matching Works

### Step by Step
```python
property = {
  "titulo": "Casa 3hab en Crevillet",
  "precio": 180000,
  "habitaciones": 3,
  "barrio": "Crevillet"
}

filter = {
  "precio_max": 200000,
  "habitaciones": 3,
  "barrio": "Crevillet"
}

# Check ALL criteria:
1. precio_max: 180000 <= 200000? ✅ YES
2. habitaciones: 3 >= 3? ✅ YES
3. barrio: "Crevillet" in "Crevillet"? ✅ YES

# Result: ✅ MATCH → Send notification!
```

---

## 📱 Notification Types

### 1. Summary (Always)
```
🎯 Puerto Inmobiliaria
✅ Nuevas: 12
⚠️ Duplicadas: 85
📄 Páginas: 2
⏱️ Tiempo: 104s
```

### 2. Filter Matches (When found)
```
🏠 Casa barata en Crevillet
Found 3 matching properties:

1. Casa 150m² 3hab - €180.000
   📍 Crevillet Centro
   🔗 [Ver ficha](url)
```

### 3. No Matches (If new but no filter matches)
```
🎯 Puerto Inmobiliaria
✅ Nuevas propiedades: 12
❌ Sin coincidencias con filtros (2 activos)
```

---

## ⚙️ How Notifications Are Sent

### Automatic Flow
```
1. Scheduler.check_and_scrape() runs
   ↓
2. Finds new properties in pagination
   ↓
3. Looks for active filters (FiltroAlerta.activo=True)
   ↓
4. For each filter:
      a. Get all newly added properties
      b. Apply filter criteria (FilterMatcher)
      c. If matches found: send notification
   ↓
5. Log all results to logs/scheduler.log
```

### Optional Manual Test
```bash
python test_filter_matcher.py
# Run filter matching tests (no Telegram)
```

---

## 🚨 Troubleshooting

### "No notifications received"
**Check:**
1. ✅ Scheduler running? `python scripts/scheduler.py`
2. ✅ Filter activated? (🟢 green icon in UI)
3. ✅ Telegram creds set? (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
4. ✅ New properties found? (Check scraping stats)
5. ✅ Filter criteria matching? (Check logs/scheduler.log)

### "Filter created but no matches"
**Debug:**
1. Check filter criteria are reasonable
2. Look at actual property values in database
3. Try less strict filter first
4. Check FilterMatcher logic in test

### "Invalid Telegram credentials"
```
Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set

Fix:
1. Get real credentials from @BotFather
2. Add to .env:
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
3. Restart scheduler
```

---

## 💡 Best Practices

1. **Start with loose filters**
   - Too strict = never matches
   - Too loose = too many notifications
   - Adjust based on results

2. **Use zone filters wisely**
   - "Crevillet" matches "Crevillet Centro", "Crevillet Este", etc
   - Case-insensitive partial match

3. **Monitor logs**
   - `tail -f logs/scheduler.log`
   - Check for errors in matching or sending

4. **Test filters**
   - Create test filter first
   - Verify matches make sense
   - Then create production filters

5. **Keep filters updated**
   - Deactivate old filters (🔴)
   - Delete filters you don't use
   - Prevents notification spam

---

## 📈 Performance

### Database Queries
- Filter matching: O(new_properties × active_filters)
- Notification sending: Async (fast)

### Example
```
100 new properties
3 active filters
→ 300 property comparisons (~100ms)
→ 3 Telegram messages sent (~3-5 seconds)
Total: ~5 seconds added to scheduler run
```

---

## Next Steps

**After notifications are working:**
- Optional: Telegram command handlers (future feature)
- Optional: Notification history (future feature)
- Next: Sprint 3 Fase 4 (Property Visualization Page)

---

**Status: ✅ Advanced Filters + Telegram Notifications Complete!**
