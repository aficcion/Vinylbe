#!/usr/bin/env python3
"""
Script to download all documentation pages from Statscore Developer Guide
"""
import requests
import os
import time
from pathlib import Path
from urllib.parse import urljoin

# Base URL for the Confluence wiki
BASE_URL = "https://statscore.atlassian.net"

# List of all pages to download (path, filename)
PAGES = [
    ("/wiki/spaces/SCOUT/pages/6983359/Developer+guide", "01_developer_guide.html"),
    ("/wiki/spaces/SCOUT/pages/6983338/AMQP+service", "02_amqp_service.html"),
    ("/wiki/spaces/SCOUT/pages/6983251/Messages+types", "03_messages_types.html"),
    ("/wiki/spaces/SCOUT/pages/6983115/Message+incident", "04_message_incident.html"),
    ("/wiki/spaces/SCOUT/pages/6983198/Message+event", "05_message_event.html"),
    ("/wiki/spaces/SCOUT/pages/6983109/Message+event_keep_alive", "06_message_event_keep_alive.html"),
    ("/wiki/spaces/SCOUT/pages/3604709377/Message+events_lineups", "07_message_events_lineups.html"),
    ("/wiki/spaces/SCOUT/pages/1805746223/Interrupted+live+data+feed+delivery", "08_interrupted_live_data_feed.html"),
    ("/wiki/spaces/SCOUT/pages/2253095065/Handling+key+incidents+confirmations", "09_handling_key_incidents_confirmations.html"),
    ("/wiki/spaces/SCOUT/pages/2253815960/Handling+incident+attributes", "10_handling_incident_attributes.html"),
    ("/wiki/spaces/SCOUT/pages/6983166/API+service", "11_api_service.html"),
    ("/wiki/spaces/SCOUT/pages/6983143/Sports+data+structure", "12_sports_data_structure.html"),
    ("/wiki/spaces/SCOUT/pages/6983163/Help+support", "13_help_support.html"),
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
    
    print(f"Starting download of {len(PAGES)} pages...")
    print(f"Output directory: {output_dir.absolute()}\n")
    
    successful = 0
    failed = 0
    
    for url, filename in PAGES:
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
    print(f"Total: {len(PAGES)}")
    print(f"{'='*60}")
    
    # Create an index file
    index_path = output_dir / "index.md"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write("# Statscore Developer Guide Documentation\n\n")
        f.write("## Downloaded Pages\n\n")
        for i, (url, filename) in enumerate(PAGES, 1):
            page_name = url.split('/')[-1].replace('+', ' ')
            f.write(f"{i}. [{page_name}]({filename})\n")
    
    print(f"\nIndex file created: {index_path}")

if __name__ == "__main__":
    main()
