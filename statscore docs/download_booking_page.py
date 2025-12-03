#!/usr/bin/env python3
"""
Script to download the Booking events via API page
"""
import requests
from pathlib import Path
from urllib.parse import urljoin

BASE_URL = "https://statscore.atlassian.net"
PAGE_URL = "/wiki/spaces/SCOUT/pages/1879736345/Booking+events+via+API"
FILENAME = "booking_events_via_api.html"

def download_page():
    """Download the Booking events via API page"""
    full_url = urljoin(BASE_URL, PAGE_URL)
    print(f"Downloading: {full_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(full_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Save the HTML content
        output_dir = Path("statscore_docs")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / FILENAME
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"✓ Saved to: {output_path}")
        
        # Update index
        index_path = output_dir / "index.md"
        with open(index_path, 'a', encoding='utf-8') as f:
            f.write("\n\n---\n\n")
            f.write("## Booking Events via API\n\n")
            f.write(f"1. [Booking events via API]({FILENAME})\n")
        
        print(f"✓ Index file updated: {index_path}")
        return True
        
    except Exception as e:
        print(f"✗ Error downloading {full_url}: {e}")
        return False

if __name__ == "__main__":
    download_page()
