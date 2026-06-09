# 🤖 Automated Scraper Scheduler Guide

## Overview

The ScraperScheduler automatically executes `run_paginated_scraper()` for each fuente based on its `intervalo_horas` setting.

```
Por ejemplo:
Puerto Inmobiliaria (intervalo=24h)
  ├─ 08:00 UTC: Última ejecución = 2 días atrás → 🚀 SCRAPEANDO
  ├─ 20:00 UTC: Última ejecución = 12 horas atrás → ⏭️ Demasiado pronto
  └─ Próximo: 08:00 UTC (en 20h)
```

---

## How It Works

### Logic
```python
FOR each activa fuente:
  time_passed = now - ultima_ejecucion
  time_needed = intervalo_horas
  
  IF time_passed >= time_needed:
    🚀 RUN scraping
    UPDATE ultima_ejecucion = now
  ELSE:
    ⏭️ Skip (too soon)
```

### Workflow
```
1. Check all active fuentes (every 1 minute)
2. For each: compare time_passed vs time_needed
3. If ready: execute run_paginated_scraper()
4. Update ultima_ejecucion in database
5. Log results (nuevas, duplicadas, errores, tiempo)
6. Repeat
```

---

## 🚀 How to Use

### Option 1: Local Testing (Terminal)

**Start scheduler**:
```bash
python scripts/scheduler.py
```

Options:
```bash
python scripts/scheduler.py --interval 1              # Check every 1 minute (default)
python scripts/scheduler.py --interval 5              # Check every 5 minutes
python scripts/scheduler.py --results-per-page 48     # Adjust page size
python scripts/scheduler.py --help                    # Show all options
```

**Output**:
```
2026-06-09 21:30:00 | INFO     | root       | 🚀 ScraperScheduler daemon started
2026-06-09 21:30:00 | INFO     | root       | ⏰ Check interval: 1 minute(s)
2026-06-09 21:30:01 | INFO     | scraper.scheduler | 🚀 Starting scrape for Puerto Inmobiliaria...
2026-06-09 21:31:45 | INFO     | scraper.scheduler | ✅ Scrape completed: Puerto Inmobiliaria | nuevas=12, duplicadas=85, errores=0, páginas=2, tiempo=104s
```

**Stop scheduler**: Press `Ctrl+C`

---

### Option 2: Background Process (Unix/Linux/Mac)

**Start in background**:
```bash
nohup python scripts/scheduler.py > logs/scheduler_bg.log 2>&1 &
```

**Check if running**:
```bash
ps aux | grep "scheduler.py"
```

**Stop process**:
```bash
kill <PID>
```

---

### Option 3: GitHub Actions (Production)

**Automatic scheduling**:
- `.github/workflows/scheduler.yml` runs at:
  - 08:00 UTC daily
  - 20:00 UTC daily

**Manual trigger**:
- Go to GitHub Actions → "Automated Scraper Scheduler"
- Click "Run workflow"

**Logs**:
- Check Actions → Latest run
- Artifacts: `scraper-logs-*`

---

## 📊 Example Scenarios

### Scenario 1: Multiple Fuentes with Different Intervals

```
Current time: 08:00 UTC

Puerto Inmobiliaria (intervalo=24h, última=48h atrás)
  ✅ 8:00 → Should scrape → 🚀 SCRAPING
     ✓ Nuevas: 12, Duplicadas: 85
     ✓ Updated: ultima_ejecucion = 08:00 UTC

Idealista (intervalo=12h, última=6h atrás)
  ❌ 8:00 → Too soon (next in 6h)

Next check in 1 minute:
  Puerto: Too soon (next in 24h)
  Idealista: Too soon (next in 6h)
```

### Scenario 2: Second Run (Same Day)

```
Current time: 20:00 UTC (same day)

Puerto Inmobiliaria (intervalo=24h, última=12h ago @ 08:00)
  ❌ Too soon (next in 12h) → Skip

Idealista (intervalo=12h, última=6h ago @ 14:00)
  ✅ Exactly 6h passed → 🚀 SCRAPING
     ✓ Nuevas: 3, Duplicadas: 95 (already had most)
     ✓ Updated: ultima_ejecucion = 20:00 UTC
```

### Scenario 3: New Fuente (Never Scraped)

```
Nueva Fuente (intervalo=48h, última=NULL)

Scheduler: "Última ejecución es null → SCRAPE NOW!"
  🚀 SCRAPING
  ✓ Todas propiedades son nuevas
  ✓ Updated: ultima_ejecucion = now
```

---

## 🔧 Configuration

### Per-Fuente Settings

**In Streamlit** → Gestión de Fuentes:
1. Click fuente → Edit
2. Set "Intervalo de scraping (horas)"
   - 24 = once a day
   - 12 = twice a day
   - 6 = every 6 hours
   - etc.
3. Save

### Scheduler Settings

**In code** → `scripts/scheduler.py` or CLI args:
```python
scheduler = ScraperScheduler(
    check_interval_minutes=1,      # How often to check (default 1)
    results_per_page=48            # Pagination size (default 48)
)
```

**CLI args**:
```bash
python scripts/scheduler.py --interval 5 --results-per-page 36
```

---

## 📋 Database Fields

**Fuente model**:
```python
intervalo_horas: int                  # Hours between scrapes (24, 12, 6, etc)
ultima_ejecucion: Optional[datetime]  # When last scrape ran
```

**Scheduler logic**:
```python
if (now - ultima_ejecucion) >= timedelta(hours=intervalo_horas):
    scrape()
    ultima_ejecucion = now
```

---

## 📊 Monitoring & Logging

### Log Location
- **Local**: `logs/scheduler.log`
- **GitHub Actions**: Actions artifacts (`scraper-logs-*`)

### Log Format
```
2026-06-09 08:00:00 | INFO     | scraper.scheduler | ✅ Scrape completed: Puerto Inmobiliaria | nuevas=12, duplicadas=85, errores=0, páginas=2, tiempo=104s
```

### Check Recent Logs
```bash
tail -50 logs/scheduler.log        # Last 50 lines
tail -f logs/scheduler.log         # Follow (live updates)
grep "nuevas=" logs/scheduler.log  # Find scraping results
```

---

## 🚨 Troubleshooting

### Issue: "No active fuentes found"
**Reason**: All fuentes have `activa=False`
**Fix**: Go to Streamlit, enable at least one fuente

### Issue: "Scraper runs but never scrapes"
**Reason**: All fuentes are "too soon" (not enough time passed)
**Fix**: Either:
1. Wait until interval has passed
2. Use `test_scheduler.py` → Option 3 to manually update test data
3. Reduce `intervalo_horas` in Streamlit

### Issue: "Database connection error"
**Reason**: DATABASE_URL missing or invalid
**Fix**: 
- Local: Check `.env` file
- GitHub Actions: Check secrets in Settings

### Issue: "Script runs indefinitely in background"
**Solution**: Kill it:
```bash
ps aux | grep scheduler.py
kill -9 <PID>
```

---

## ✅ Testing

### Quick Test (Check Logic, No Scraping)
```bash
python test_scheduler.py
# Select option 1
```

### Test Scheduling Decision
```bash
python test_scheduler.py
# Select option 1 → See which fuentes would scrape now
```

### Prepare Test Data
```bash
python test_scheduler.py
# Select option 3 → Set Puerto Inmobiliaria's ultima_ejecucion to 48h ago
```

### Run One Scraping Cycle
```bash
python test_scheduler.py
# Select option 2 → Will actually scrape if any fuente is due
```

---

## 📈 Performance

### Expected Times
- Check cycle: ~100-500ms (just checking, no scraping)
- First scrape (all new): ~3-5 minutes for ~95 properties
- Second scrape (all duplicates): ~30 seconds
- Each fuente: parallel or sequential? (depends on implementation)

### Resource Usage
- RAM: ~100-200MB (depending on cache_resource in Streamlit)
- CPU: Minimal when idle (1-2%), high during scraping
- Network: Heavy during scraping, none when checking

---

## 🚀 Deployment

### Docker Compose (if using)
```yaml
scheduler:
  build: .
  command: python scripts/scheduler.py
  environment:
    DATABASE_URL: postgresql://...
    TELEGRAM_TOKEN: ${TELEGRAM_TOKEN}
    TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID}
  volumes:
    - ./logs:/app/logs
  restart: unless-stopped
```

### GitHub Actions (Current)
- Edit `.github/workflows/scheduler.yml`
- Runs at 08:00 and 20:00 UTC daily
- Can manually trigger anytime

---

## 💡 Best Practices

1. **Start with longer intervals** (24h, 12h)
   - Then reduce if needed
   - Too frequent = wasted resources

2. **Monitor logs regularly**
   - `tail -f logs/scheduler.log` while developing
   - Check GitHub Actions artifacts in production

3. **Use separate test fuente**
   - Before enabling on production fuentes
   - Verify it works with small data first

4. **Set reasonable intervalo_horas**
   - Real estate: 12-24h is typical (market changes slow)
   - Stock prices: 1-6h needed (faster changes)
   - Adjust based on your use case

---

## 🎯 Next Step: Telegram Notifications

After scheduler is working, add notifications:
- Send message when `nuevas > 0`
- Format: Título, Precio, Dirección, URL
- Via Telegram bot

See: Sprint 3 Fase 3 plan
