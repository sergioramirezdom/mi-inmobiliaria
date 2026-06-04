# 🏠 Mi Inmobiliaria Personal

Una herramienta de búsqueda de vivienda inteligente que te ayuda a centralizar la búsqueda en múltiples portales inmobiliarios, con filtros avanzados y alertas automáticas en Telegram.

**Stack:** Streamlit + PostgreSQL (Neon) + GitHub Actions + Python

**Coste:** 0€ (100% servicios gratuitos)

---

## 🚀 Características

- ✅ **Gestión de fuentes** — Añade URLs de inmobiliarias (Idealista, Fotocasa, Habitaclia, etc.)
- ✅ **Scraping automático** — Extrae propiedades periódicamente via GitHub Actions
- ✅ **Filtros avanzados** — Por precio, m², habitaciones, ascensor, garaje, ubicación, etc.
- ✅ **Alertas Telegram** — Recibe notificaciones de nuevas propiedades que cumplen tus filtros
- ✅ **Base de datos centralizada** — PostgreSQL en Neon (gratuito)
- ✅ **Despliegue sin coste** — Streamlit Community Cloud + GitHub Actions free

---

## 📋 Requisitos Previos

### Cuentas necesarias (todas gratuitas)

1. **GitHub** — Para hospedar el código y ejecutar Actions
2. **Neon Tech** (https://neon.tech) — Para la base de datos PostgreSQL
3. **Telegram** — Bot y chat para recibir alertas
4. **Streamlit Community Cloud** (https://streamlit.io/cloud) — Para hostear la app

### Software local (desarrollo)

- Python 3.11+
- Git
- pip o conda (gestor de paquetes Python)

---

## 🔧 Setup Local (Desarrollo)

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/mi-inmobiliaria-personal.git
cd mi-inmobiliaria-personal
```

### 2. Crear y activar un entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Copia `.env.example` a `.env` y rellena los valores:

```bash
cp .env.example .env
```

Edita `.env` y añade:

```
DATABASE_URL=postgresql://user:password@host/database
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DEBUG=true
```

### 5. Inicializar la base de datos

```bash
python scripts/init_db.py
```

### 6. Ejecutar la app localmente

```bash
streamlit run app/main.py
```

La app se abrirá en `http://localhost:8501`

---

## ☁️ Setup Cloud (Producción)

### 1. Crear cuenta en Neon Tech

1. Ir a https://console.neon.tech
2. Registrarse con GitHub (recomendado)
3. Crear un nuevo proyecto
4. Copiar el `DATABASE_URL` (formato `postgresql://...`)

### 2. Crear un bot de Telegram

1. Abre Telegram y busca `@BotFather`
2. Escribe `/newbot` y sigue las instrucciones
3. Te dará un token de la forma `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
4. Copia este token (será `TELEGRAM_TOKEN`)

### 3. Obtener tu chat ID

1. Crea un grupo privado con el bot o envíale un mensaje directo
2. Abre en el navegador: `https://api.telegram.org/bot<TELEGRAM_TOKEN>/getUpdates`
3. Busca `"chat":{"id":<ID>}` — ese es tu `TELEGRAM_CHAT_ID`

### 4. Crear repositorio GitHub

1. Crea un repo público en GitHub: https://github.com/new
2. Nombra el repo `mi-inmobiliaria-personal`
3. Clona y sube el código:

```bash
git remote add origin https://github.com/tu-usuario/mi-inmobiliaria-personal.git
git push -u origin main
```

### 5. Desplegar en Streamlit Community Cloud

1. Ve a https://streamlit.io/cloud
2. Conecta con tu cuenta GitHub
3. Haz clic en "New app"
4. Selecciona el repositorio y la rama `main`
5. En las opciones, configura los secrets (próximo paso)
6. Deploy

### 6. Configurar Secrets en Streamlit Cloud

En la app de Streamlit Cloud, ve a Settings → Secrets y añade:

```toml
DATABASE_URL = "postgresql://..."
TELEGRAM_TOKEN = "your_token"
TELEGRAM_CHAT_ID = "your_chat_id"
DEBUG = "false"
```

### 7. Configurar GitHub Actions (scraping automático)

En tu repositorio de GitHub:

1. Ve a Settings → Secrets and variables → Actions
2. Crea las siguientes secrets:
   - `DATABASE_URL` — Tu PostgreSQL URL
   - `TELEGRAM_TOKEN` — Token del bot
   - `TELEGRAM_CHAT_ID` — Tu chat ID

El workflow `.github/workflows/scraping.yml` se ejecutará automáticamente a las 8h y 20h UTC.

---

## 📖 Uso

### 1. Página: Fuentes

- Añade URLs de inmobiliarias (ej: `https://www.idealista.com/venta/viviendas/madrid/`)
- Configura el intervalo de scraping (horas)
- Haz clic en "Probar scraping" para validar

### 2. Página: Propiedades

- Visualiza todas las propiedades encontradas
- Aplica filtros avanzados (precio, m², habitaciones, ubicación, etc.)
- Marca propiedades como "vista" o "descartada"

### 3. Página: Alertas

- Crea filtros de alerta personalizados
- Las nuevas propiedades que coincidan se notificarán automáticamente en Telegram

---

## 🔄 Cómo funciona el flujo

1. **Configuración inicial**: Añades URLs de inmobiliarias en la página "Fuentes"
2. **Scraping manual**: Desde la UI puedes hacer scraping bajo demanda
3. **Scraping automático**: GitHub Actions ejecuta el scraping a horas fijas (cron)
4. **Deduplicación**: Solo se guardan propiedades nuevas (hash único)
5. **Alertas**: Si una nueva propiedad coincide con tus filtros → Telegram
6. **Visualización**: Exploras las propiedades en la web con filtros

---

## 📊 Modelo de datos

### Tablas principales

- **Fuente** — URLs de inmobiliarias, intervalo de scraping, estado
- **Propiedad** — Datos de propiedades encontradas (precio, m², habitaciones, ubicación, etc.)
- **FiltroAlerta** — Tus filtros personalizados para recibir alertas

Todas las propiedades tienen un `hash_unico` para evitar duplicados.

---

## 🚨 Solución de problemas

### "No se puede conectar a la BD"

- Verifica que `DATABASE_URL` es correcta (copia desde Neon)
- En local, revisa que `.env` existe y está en el root del proyecto
- En Streamlit Cloud, verifica que los secrets están configurados

### "El scraping no funciona"

- Algunos sitios (Idealista, Fotocasa) bloquean scraping simple
- Por ahora usamos httpx + BeautifulSoup4 (sin Playwright en GitHub Actions)
- Intenta primero con un sitio de prueba (ej: un portal personal)

### "No recibo mensajes de Telegram"

- Verifica que `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` son correctos
- Prueba manualmente: `curl https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>&text=Hola`

---

## 🛠️ Desarrollo

### Estructura de directorios

```
mi-inmobiliaria-personal/
├── app/
│   ├── main.py               # Entrada Streamlit
│   ├── pages/
│   │   ├── 1_fuentes.py      # Gestión de fuentes
│   │   ├── 2_propiedades.py  # Visualización y filtros
│   │   └── 3_alertas.py      # Config de alertas
│   ├── scraper/
│   │   ├── base.py           # Clase base
│   │   ├── generic.py        # Scraper genérico
│   │   └── runner.py         # Orquestador
│   ├── db/
│   │   ├── models.py         # SQLModel models
│   │   └── database.py       # CRUD y engine
│   ├── telegram_bot/
│   │   └── notifier.py       # Envío de mensajes
│   └── config.py             # Configuración
├── scripts/
│   ├── init_db.py            # Inicializar BD
│   └── scrape_and_notify.py  # Ejecutado por GitHub Actions
├── .github/workflows/
│   └── scraping.yml          # Cron job
└── requirements.txt
```

### Añadir un nuevo scraper específico

En `app/scraper/`, crea un archivo `idealista.py`:

```python
from app.scraper.base import ScraperBase

class IdealistaScrapercraper(ScraperBase):
    def scrape(self, url: str) -> list[dict]:
        # Tu lógica de scraping
        pass
```

---

## 📜 Licencia

MIT

---

## 💬 Soporte

Para problemas, abre un issue en GitHub.

---

**Creado con ❤️ para encontrar la vivienda perfecta**
