#!/usr/bin/env python3
"""
Script to download API resources documentation from Statscore
"""
import requests
import os
import time
from pathlib import Path
from urllib.parse import urljoin

# Base URL for the Confluence wiki
BASE_URL = "https://statscore.atlassian.net"

# List of all API resources pages to download (path, filename)
API_PAGES = [
    ("/wiki/spaces/SCOUT/pages/6983174/API+resources", "api_00_resources.html"),
    ("/wiki/spaces/SCOUT/pages/6983117/booked-events.create", "api_01_booked_events_create.html"),
    ("/wiki/spaces/SCOUT/pages/6983119/booked-events.delete", "api_02_booked_events_delete.html"),
    ("/wiki/spaces/SCOUT/pages/6983208/events.show", "api_03_events_show.html"),
    ("/wiki/spaces/SCOUT/pages/6983151/events.index", "api_04_events_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983194/booked-events.index", "api_05_booked_events_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983103/feed.index", "api_06_feed_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983107/feed.show", "api_07_feed_show.html"),
    ("/wiki/spaces/SCOUT/pages/6983201/incidents.index", "api_08_incidents_index.html"),
    ("/wiki/spaces/SCOUT/pages/4248010789/logo.index", "api_09_logo_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983160/reports.clients-events.index", "api_10_reports_clients_events_index.html"),
    ("/wiki/spaces/SCOUT/pages/4248076289/skins.index", "api_11_skins_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983100/sports.index", "api_12_sports_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983195/sports.show", "api_13_sports_show.html"),
    ("/wiki/spaces/SCOUT/pages/6983196/statuses.index", "api_14_statuses_index.html"),
    ("/wiki/spaces/SCOUT/pages/3761209345/events.sub-participants.index", "api_15_events_sub_participants_index.html"),
    ("/wiki/spaces/SCOUT/pages/6983351/API+feed+examples", "api_16_feed_examples.html"),
]

def download_page(url, filename, output_dir):
    """Download a single page and save it to a file"""
    full_url = urljoin(BASE_URL, url)
    print(f"Downloading: {full_url}")
    
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
        
        print(f"✓ Saved to: {output_path}")
        return True
    except Exception as e:
        print(f"✗ Error downloading {full_url}: {e}")
        return False

def main():
    # Create output directory
    output_dir = Path("statscore_docs")
    output_dir.mkdir(exist_ok=True)
    
    print(f"Starting download of {len(API_PAGES)} API resources pages...")
    print(f"Output directory: {output_dir.absolute()}\n")
    
    successful = 0
    failed = 0
    
    for url, filename in API_PAGES:
        if download_page(url, filename, output_dir):
            successful += 1
        else:
            failed += 1
        
        # Be polite to the server
        time.sleep(1)
    
    print(f"\n{'='*60}")
    print(f"Download complete!")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total: {len(API_PAGES)}")
    print(f"{'='*60}")
    
    # Update the index file
    index_path = output_dir / "index.md"
    
    # Read existing content
    existing_content = ""
    if index_path.exists():
        with open(index_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()
    
    # Append API resources section
    with open(index_path, 'a', encoding='utf-8') as f:
        if existing_content:
            f.write("\n\n---\n\n")
        f.write("## API Resources\n\n")
        for i, (url, filename) in enumerate(API_PAGES, 1):
            page_name = url.split('/')[-1].replace('+', ' ')
            f.write(f"{i}. [{page_name}]({filename})\n")
    
    print(f"\nIndex file updated: {index_path}")

if __name__ == "__main__":
    main()
