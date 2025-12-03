#!/usr/bin/env python3
"""
Script to download API feed example sub-pages
"""
import requests
import time
from pathlib import Path
from urllib.parse import urljoin

# Base URL for the Confluence wiki
BASE_URL = "https://statscore.atlassian.net"

# List of all pages to download (path, filename, description)
PAGES = [
    ("/wiki/spaces/SCOUT/pages/6983065/areas.index+example", "extra_08_areas_index_example.html", "areas.index example"),
    ("/wiki/spaces/SCOUT/pages/6983073/booked-events.index+example", "extra_09_booked_events_index_example.html", "booked-events.index example"),
    ("/wiki/spaces/SCOUT/pages/6983072/competitions.index+expample", "extra_10_competitions_index_example.html", "competitions.index example"),
    ("/wiki/spaces/SCOUT/pages/6983071/competitions.show+expample", "extra_11_competitions_show_example.html", "competitions.show example"),
    ("/wiki/spaces/SCOUT/pages/6983070/events.index+example", "extra_12_events_index_example.html", "events.index example"),
    ("/wiki/spaces/SCOUT/pages/6983062/events.show+example", "extra_13_events_show_example.html", "events.show example"),
    ("/wiki/spaces/SCOUT/pages/6983068/feed.index+example", "extra_14_feed_index_example.html", "feed.index example"),
    ("/wiki/spaces/SCOUT/pages/2027127133/feed.show+example", "extra_15_feed_show_example.html", "feed.show example"),
    ("/wiki/spaces/SCOUT/pages/6983067/incidents.index+example", "extra_16_incidents_index_example.html", "incidents.index example"),
    ("/wiki/spaces/SCOUT/pages/6983078/languages.index+example", "extra_17_languages_index_example.html", "languages.index example"),
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
    
    print(f"Starting download of {len(PAGES)} API feed example sub-pages...")
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
        f.write("## API Feed Examples (Sub-pages)\n\n")
        for i, (url, filename, description) in enumerate(PAGES, 1):
            f.write(f"{i}. [{description}]({filename})\n")
    
    print(f"\nIndex file updated: {index_path}")

if __name__ == "__main__":
    main()
