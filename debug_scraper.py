#!/usr/bin/env python3
"""Debug script to analyze website structure for scraping."""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

import httpx
from bs4 import BeautifulSoup
from scraper.generic import GenericScraper
from scraper.config import ScraperConfig
from db.models import Fuente


async def debug_scrape(url: str):
    """Debug scraping of a URL."""
    print(f"🔍 Debugging scrape of: {url}\n")

    # Create scraper
    config = ScraperConfig()
    scraper = GenericScraper(config)

    try:
        # Fetch content
        print("1️⃣ Fetching HTML content...")
        content = await scraper.fetch_content(url)
        print(f"   ✓ Downloaded {len(content)} bytes\n")

        # Parse with BeautifulSoup
        print("2️⃣ Parsing HTML...")
        soup = BeautifulSoup(content, "html.parser")
        print(f"   ✓ HTML parsed\n")

        # Try auto-detect
        print("3️⃣ Attempting auto-detect patterns...")
        patterns = [
            '[class*="property"]',
            '[class*="listing"]',
            '[class*="anuncio"]',
            '[class*="producto"]',
            '[class*="item"]',
            '[class*="vivienda"]',
            '[class*="propiedad"]',
            'article',
            'li[class*="property"]',
            'div[class*="resultado"]',
        ]

        found_elements = {}
        for pattern in patterns:
            elements = soup.select(pattern)
            if elements:
                found_elements[pattern] = len(elements)

        if found_elements:
            print("   ✓ Found elements matching patterns:")
            for pattern, count in sorted(found_elements.items(), key=lambda x: x[1], reverse=True):
                print(f"      - {pattern}: {count} elements")
        else:
            print("   ⚠️ No elements matched common patterns")

        print()

        # Look for links with 'href'
        print("4️⃣ Looking for property links...")
        links = soup.find_all('a', href=True)
        print(f"   - Total <a> tags: {len(links)}")

        # Filter potential property links
        property_keywords = ['propiedad', 'vivienda', 'piso', 'casa', 'inmueble', 'apartamento', 'detalle', 'property', 'listing']
        property_links = [
            link for link in links
            if any(keyword in link.get('href', '').lower() for keyword in property_keywords)
        ]
        print(f"   - Links with property keywords: {len(property_links)}")
        if property_links:
            print("      Sample links:")
            for link in property_links[:3]:
                print(f"        - {link.get('href', '')[:80]}")

        print()

        # Look for price-like content
        print("5️⃣ Looking for price patterns...")
        text_content = soup.get_text()
        import re
        prices = re.findall(r'€\s*[\d.,]+', text_content)
        print(f"   - Found {len(set(prices))} unique prices: {list(set(prices))[:5]}")

        print()

        # Show page structure
        print("6️⃣ Page structure analysis...")
        main_content = soup.find('main') or soup.find('body')
        if main_content:
            divs = main_content.find_all('div', recursive=False, limit=5)
            print(f"   - Main sections: {len(main_content.find_all(recursive=False))} direct children")
            print("   - Top-level divs with class:")
            for div in divs[:5]:
                classes = div.get('class', [])
                print(f"      <div class=\"{' '.join(classes) if classes else 'N/A'}\">")

        print()

        # Try actual scraping
        print("7️⃣ Attempting actual scrape...")
        fuente = Fuente(
            id=1,
            nombre="Debug",
            url=url,
            tipo_scraper="generic",
            activa=True,
            intervalo_horas=24,
        )

        result = await scraper.scrape(fuente)
        print(f"   ✓ Scrape result: {len(result)} properties found")

        if result:
            print("   Sample property:")
            prop = result[0]
            for key, value in list(prop.items())[:5]:
                print(f"      - {key}: {str(value)[:60]}")
        else:
            print("   ⚠️ No properties extracted")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main debug entry point."""
    # Default URL or from command line
    url = "https://www.puertoinmobiliaria.es/"
    if len(sys.argv) > 1:
        url = sys.argv[1]

    await debug_scrape(url)


if __name__ == "__main__":
    asyncio.run(main())
