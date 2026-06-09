#!/usr/bin/env python3
"""Detailed debug of HTML structure."""

import sys
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent / "app"))


def analyze_structure(url: str):
    """Analyze HTML structure in detail."""
    print(f"🔍 Analyzing: {url}\n")

    # Fetch
    response = httpx.get(url, follow_redirects=True, timeout=30)
    content = response.text
    soup = BeautifulSoup(content, "html.parser")

    # Look for divs/articles with "propiedad" class
    print("📍 Elements with 'propiedad' in class:")
    propiedad_elements = soup.find_all(class_=lambda x: x and 'propiedad' in x.lower())
    print(f"   Found {len(propiedad_elements)} elements\n")

    if propiedad_elements:
        elem = propiedad_elements[0]
        print(f"   First element: <{elem.name} class=\"{elem.get('class', [])}\"")
        print(f"   HTML snippet:")
        print(f"   {str(elem)[:300]}...\n")

    # Look for articles
    print("📍 Article elements:")
    articles = soup.find_all('article')
    print(f"   Found {len(articles)} articles\n")

    if articles:
        elem = articles[0]
        print(f"   First article:")
        print(f"   {str(elem)[:300]}...\n")

    # Look for specific patterns in the page
    print("📍 Looking for specific selectors that might work:")

    test_selectors = [
        '.propiedad',
        '[class*="propiedad"]',
        'article.propiedad',
        '.item-propiedad',
        '.producto-inmobiliario',
        '[data-property]',
        '[data-id]',
        '.card',
        '.property',
        '.listing',
    ]

    for selector in test_selectors:
        elements = soup.select(selector)
        if elements:
            print(f"   ✓ {selector}: {len(elements)} elements")
            elem = elements[0]
            # Try to find price
            price = elem.find(string=lambda text: text and '€' in text)
            # Try to find title/link
            link = elem.find('a')
            print(f"      Price: {price[:30] if price else 'N/A'}")
            print(f"      Link: {link.get('href', 'N/A')[:50] if link else 'N/A'}")

    # Check if page uses JavaScript
    print("\n📍 JavaScript detection:")
    scripts = soup.find_all('script')
    print(f"   Total <script> tags: {len(scripts)}")

    # Look for data in script tags
    for script in scripts:
        if script.string and ('window.' in script.string or 'document.' in script.string or 'propiedad' in script.string.lower()):
            print(f"   ⚠️ Found script with dynamic content")
            if 'propiedad' in script.string.lower():
                print(f"      Contains 'propiedad' references")
            break

    # Check meta tags
    print("\n📍 Meta information:")
    og_title = soup.find('meta', property='og:title')
    if og_title:
        print(f"   og:title: {og_title.get('content', 'N/A')}")

    # Look at actual content structure
    print("\n📍 Content container analysis:")
    main = soup.find('main') or soup.find('body')
    if main:
        # Find largest div
        divs = main.find_all('div', recursive=True)
        print(f"   Total divs: {len(divs)}")

        # Find by common property container names
        for name in ['contenedor', 'container', 'content', 'principal', 'main-content', 'products', 'listings']:
            elements = soup.find_all(class_=lambda x: x and name in x.lower())
            if elements:
                print(f"   ✓ Found {len(elements)} elements with '{name}' in class")


if __name__ == "__main__":
    url = "https://www.puertoinmobiliaria.es/"
    if len(sys.argv) > 1:
        url = sys.argv[1]

    analyze_structure(url)
