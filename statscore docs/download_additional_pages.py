#!/usr/bin/env python3
"""
Script to download additional Statscore documentation pages
"""
import requests
import time
from pathlib import Path
from urllib.parse import urljoin

# Base URL for the Confluence wiki
BASE_URL = "https://statscore.atlassian.net"

# List of all pages to download (path, filename, description)
PAGES = [
    # These might already exist but we'll download them again to ensure completeness
    ("/wiki/spaces/SCOUT/pages/6983351/API+feed+examples", "extra_01_api_feed_examples.html", "API feed examples"),
    ("/wiki/spaces/SCOUT/pages/6983143/Sports+data+structure", "extra_02_sports_data_structure.html", "Sports data structure"),
    
    # New pages to download
    ("/wiki/spaces/SCOUT/pages/6983259/Statuses", "extra_03_statuses.html", "Statuses"),
    ("/wiki/spaces/SCOUT/pages/6983262/Results", "extra_04_results.html", "Results"),
    ("/wiki/spaces/SCOUT/pages/6983266/Statistics", "extra_05_statistics.html", "Statistics"),
    ("/wiki/spaces/SCOUT/pages/6983254/Event+details", "extra_06_event_details.html", "Event details"),
    ("/wiki/spaces/SCOUT/pages/6983257/Incidents", "extra_07_incidents.html", "Incidents"),
]

def download_page(url, filename, description, output_dir):
    """Download a single page and save it to a file"""
    full_url = urljoin(BASE_URL, url)
    print(f"Downloading: {description}")
    print(f"  URL: {full_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(full_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Save the HTML content
        output_path = output_dir / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"  ✓ Saved to: {output_path}")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    # Create output directory
    output_dir = Path("statscore_docs")
    output_dir.mkdir(exist_ok=True)
    
    print(f"Starting download of {len(PAGES)} additional pages...")
    print(f"Output directory: {output_dir.absolute()}\n")
    print("="*70)
    
    successful = 0
    failed = 0
    
    for url, filename, description in PAGES:
        if download_page(url, filename, description, output_dir):
            successful += 1
        else:
            failed += 1
        
        print("-"*70)
        # Be polite to the server
        time.sleep(1)
    
    print(f"\n{'='*70}")
    print(f"Download complete!")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total: {len(PAGES)}")
    print(f"{'='*70}")
    
    # Update the index file
    index_path = output_dir / "index.md"
    with open(index_path, 'a', encoding='utf-8') as f:
        f.write("\n\n---\n\n")
        f.write("## Additional Documentation Pages\n\n")
        for i, (url, filename, description) in enumerate(PAGES, 1):
            f.write(f"{i}. [{description}]({filename})\n")
    
    print(f"\nIndex file updated: {index_path}")

if __name__ == "__main__":
    main()
