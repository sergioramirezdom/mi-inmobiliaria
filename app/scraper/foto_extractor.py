"""Extracción genérica de fotos a partir del HTML de una ficha.

Mismo reparto que url_extractor: una función pura con el algoritmo y un
envoltorio async fino para el fetch. La parte pura se testea con HTML fijo,
nunca contra portales reales (cambian y volverían los tests inestables).
"""

import logging
import re
from typing import List
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Formatos que nunca son la foto de un piso.
_EXT_MALAS = (".svg", ".gif", ".ico")
_EXT_BUENAS = (".jpg", ".jpeg", ".png", ".webp")

# Fragmentos de ruta propios de la plantilla del portal, no del anuncio.
_RUTA_MALA = (
    "logo", "banner", "icon", "avatar", "sprite",
    "placeholder", "thumb", "small", "blank",
    "bandera", "header", "footer", "nav", "menu",
)

# Por debajo de esto es iconografía. Solo se aplica cuando el <img> declara
# width/height: conocer el tamaño real exigiría descargar cada imagen.
_MIN_DIM = 300


def _sin_query(url: str) -> str:
    """Quita query y fragmento: '?w=800' y '?w=1200' son la misma foto."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def _carpeta(url: str) -> str:
    """Dominio + directorio, sin el nombre de fichero.

    Es la clave de agrupación: las fotos de un anuncio viven juntas en el
    CDN, mientras que los adornos de la plantilla están dispersos.
    """
    p = urlparse(url)
    return f"{p.netloc}{p.path.rsplit('/', 1)[0]}"


def _es_imagen(url: str) -> bool:
    """True si la extensión (ignorando el query) es de imagen aprovechable."""
    return _sin_query(url).lower().endswith(_EXT_BUENAS)


def _descartable(url: str) -> bool:
    """True si la URL es iconografía o decoración del portal."""
    limpia = _sin_query(url).lower()
    if limpia.endswith(_EXT_MALAS):
        return True
    return any(malo in limpia for malo in _RUTA_MALA)


def _dimension_declarada_pequena(tag) -> bool:
    """True si el <img> declara width/height por debajo de _MIN_DIM."""
    for attr in ("width", "height"):
        valor = tag.get(attr)
        if not valor:
            continue
        m = re.match(r"^\s*(\d+)", str(valor))
        if m and int(m.group(1)) < _MIN_DIM:
            return True
    return False


def _recolectar_candidatas(soup, url: str) -> List[str]:
    """Todas las URLs de imagen del documento, ya absolutas.

    Mira src, data-src/data-original (carga diferida), srcset, y los <a href>
    que apunten a una imagen: algunos portales cuelgan la miniatura del <img>
    y la foto grande del enlace que la envuelve.
    """
    candidatas: List[str] = []

    for img in soup.find_all("img"):
        if _dimension_declarada_pequena(img):
            continue
        for attr in ("src", "data-src", "data-original"):
            valor = img.get(attr)
            if valor and not valor.startswith("data:"):
                candidatas.append(urljoin(url, valor.strip()))
        srcset = img.get("srcset")
        if srcset:
            for parte in srcset.split(","):
                cand = parte.strip().split(" ")[0]
                if cand and not cand.startswith("data:"):
                    candidatas.append(urljoin(url, cand))

    # Puerto Inmobiliaria uses a custom "cargafoto" attribute for lazy-loaded property images
    for tag in soup.find_all(attrs={"cargafoto": True}):
        valor = tag.get("cargafoto", "")
        if valor and not valor.startswith("data:"):
            candidatas.append(urljoin(url, valor.strip()))

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith("data:"):
            absoluta = urljoin(url, href)
            if _es_imagen(absoluta):
                candidatas.append(absoluta)

    return candidatas


def extraer_fotos(html: str, url: str = "") -> List[str]:
    """Devuelve las URLs de las fotos del anuncio. Función pura, sin HTTP.

    Recolecta, filtra por formato y ruta, deduplica ignorando el query, y se
    queda con el grupo de imágenes que comparte carpeta más numeroso. Si no
    queda nada, cae a og:image.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    candidatas = [
        u for u in _recolectar_candidatas(soup, url)
        if _es_imagen(u) and not _descartable(u)
    ]

    # Deduplicar preservando el orden de aparición, que suele ser el orden
    # real de la galería.
    vistas = set()
    limpias: List[str] = []
    for u in candidatas:
        sin_query = _sin_query(u)
        if sin_query not in vistas:
            vistas.add(sin_query)
            limpias.append(sin_query)

    if limpias:
        grupos: dict = {}
        for u in limpias:
            grupos.setdefault(_carpeta(u), []).append(u)
        best_group = max(grupos.values(), key=len)

        # Prefer full-size versions: "3-2s.jpg" → "3-2.jpg"
        # CDN pattern: thumbnails have "s" before extension (e.g. 3-2s.jpg).
        resolved = []
        seen_paths = set()
        for u in best_group:
            p = urlparse(u)
            path = p.path
            # Convert thumbnail to full-size: remove trailing "s" before extension
            if re.match(r".*s\.\w+$", path):
                full_path = re.sub(r"s(\.\w+)$", r"\1", path)
                full_url = urlunparse((p.scheme, p.netloc, full_path, "", "", ""))
            else:
                full_url = urlunparse((p.scheme, p.netloc, path, "", "", ""))

            # Deduplicate by final path
            final_path = urlparse(full_url).path
            if final_path not in seen_paths:
                seen_paths.add(final_path)
                resolved.append(full_url)

        return resolved

    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return [_sin_query(urljoin(url, og["content"]))]

    return []


async def obtener_fotos(url: str) -> dict:
    """Descarga una ficha y extrae sus fotos.

    Nunca lanza: en caso de error devuelve {"error": "..."}, igual que
    url_extractor.extract_from_url.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, verify=True,
                                     timeout=15) as client:
            response = await client.get(url, headers=BROWSER_HEADERS)
            if response.status_code == 404:
                return {"error": "URL no encontrada (404)"}
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}"}
            html = response.text
    except Exception as e:
        return {"error": str(e)}

    return {"fotos": extraer_fotos(html, url=url)}