#!/usr/bin/env python3
"""
Debug script to see HTML structure from Bajo el Volcán
"""
import asyncio
import httpx
from bs4 import BeautifulSoup

async def debug_bajo_volcan():
    query = "Radiohead+OK+Computer"
    url = f"https://www.bajoelvolcan.es/busqueda/listaLibros.php?tipoBus=full&palabrasBusqueda={query}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0, follow_redirects=True)
        soup = BeautifulSoup(response.text, 'lxml')
        
        print("=" * 80)
        print("BAJO EL VOLCÁN HTML STRUCTURE")
        print("=" * 80)
        
        # Find all potential product containers
        print("\n1. Looking for product containers...")
        products = soup.find_all(['div', 'article', 'li'], class_=True)
        print(f"   Found {len(products)} elements with classes")
        
        # Show first few
        for i, prod in enumerate(products[:5]):
            classes = ' '.join(prod.get('class', []))
            print(f"   [{i}] Classes: {classes}")
        
        # Look for anything with "OK COMPUTER" in text
        print("\n2. Looking for 'OK COMPUTER' text...")
        ok_computer_elements = soup.find_all(string=lambda text: text and 'OK COMPUTER' in text.upper())
        for elem in ok_computer_elements[:5]:
            parent = elem.parent
            print(f"   Found in: <{parent.name}> class='{parent.get('class', [])}'")
            print(f"   Text: {elem.strip()[:100]}")
            print()
        
        # Look for prices
        print("\n3. Looking for prices (29.80 or 29,80)...")
        price_elements = soup.find_all(string=lambda text: text and ('29.80' in text or '29,80' in text))
        for elem in price_elements:
            parent = elem.parent
            print(f"   Found in: <{parent.name}> class='{parent.get('class', [])}'")
            print(f"   Text: {elem.strip()}")
            print()
        
        # Save HTML for inspection
        with open('/tmp/bajo_volcan_debug.html', 'w') as f:
            f.write(response.text)
        print("\n4. Full HTML saved to: /tmp/bajo_volcan_debug.html")

if __name__ == "__main__":
    asyncio.run(debug_bajo_volcan())
