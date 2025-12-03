import requests
import json
import sys

# Configuration
BASE_URL = "http://127.0.0.1:5000"

def test_sync_api():
    print("Testing Sync API Endpoint...")

    # 1. Define Guest Data
    guest_data = {
        "lastfm_username": "test_sync_user_e2e",
        "selected_artists": ["Radiohead", "Daft Punk"],
        "album_statuses": {
            "Radiohead|In Rainbows": "favorite",
            "Daft Punk|Discovery": "owned"
        }
    }

    print(f"Sending payload: {json.dumps(guest_data, indent=2)}")

    # 2. Call the endpoint
    try:
        response = requests.post(f"{BASE_URL}/auth/lastfm", json=guest_data)
        response.raise_for_status()
        data = response.json()
        user_id = data.get("user_id")
        print(f"Success! User ID: {user_id}")
    except requests.exceptions.RequestException as e:
        print(f"API Call Failed: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        sys.exit(1)

    # 3. Verify Data in DB (via API if possible, or we assume success if no error)
    # Let's check selected artists via API
    try:
        resp = requests.get(f"{BASE_URL}/users/{user_id}/selected-artists")
        resp.raise_for_status()
        artists = resp.json()
        artist_names = [a['artist_name'] for a in artists]
        print(f"Selected Artists in DB: {artist_names}")
        
        if "Radiohead" in artist_names and "Daft Punk" in artist_names:
            print("✓ Artists synced correctly")
        else:
            print("✗ Artists NOT synced")
            
    except Exception as e:
        print(f"Failed to verify artists: {e}")

    # 4. Verify Recommendations (Album Statuses)
    try:
        resp = requests.get(f"{BASE_URL}/users/{user_id}/recommendations?include_favorites=true")
        resp.raise_for_status()
        recs = resp.json()
        
        # Helper to find status
        def check_status(artist, album, expected_status):
            found = next((r for r in recs if r['artist_name'] == artist and r['album_title'] == album), None)
            if found:
                print(f"Found {artist} - {album}: Status='{found['status']}'")
                if found['status'] == expected_status:
                    return True
            print(f"Missing or wrong status for {artist} - {album}")
            return False

        if check_status("Radiohead", "In Rainbows", "favorite") and \
           check_status("Daft Punk", "Discovery", "owned"):
            print("✓ Album statuses synced correctly")
        else:
            print("✗ Album statuses NOT synced")

    except Exception as e:
        print(f"Failed to verify recommendations: {e}")

if __name__ == "__main__":
    test_sync_api()
