import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gateway import db

def test_sync_logic():
    print("Testing Sync Logic...")
    
    # Ensure DB is initialized and migrated
    db.init_db()
    
    # 1. Create a test user
    username = "test_sync_user"
    print(f"Creating/Getting user: {username}")
    user_id = db.get_or_create_user_via_lastfm(username)
    print(f"User ID: {user_id}")
    
    # 2. Test Selected Artists Duplicate Prevention
    artist_name = "Test Artist Sync"
    print(f"Adding artist: {artist_name}")
    db.add_user_selected_artist(user_id, artist_name, source="manual")
    
    print("Adding same artist again (should be ignored)...")
    db.add_user_selected_artist(user_id, artist_name, source="manual")
    
    artists = db.get_user_selected_artists(user_id)
    test_artist = [a for a in artists if a["artist_name"] == artist_name]
    
    if len(test_artist) == 1:
        print("✓ Artist duplicate prevention working")
    else:
        print(f"✗ Artist duplicate prevention FAILED. Found {len(test_artist)} records")
        
    # 3. Test Recommendation Upsert
    rec_artist = "Test Rec Artist"
    rec_album = "Test Rec Album"
    
    print(f"Upserting recommendation: {rec_artist} - {rec_album} (favorite)")
    db.upsert_recommendation_status(user_id, rec_artist, rec_album, "favorite")
    
    recs = db.get_recommendations_for_user(user_id)
    target_rec = next((r for r in recs if r["artist_name"] == rec_artist and r["album_title"] == rec_album), None)
    
    if target_rec and target_rec["status"] == "favorite":
        print("✓ Recommendation inserted correctly")
    else:
        print("✗ Recommendation insert FAILED")
        
    print("Updating same recommendation to 'owned'...")
    db.upsert_recommendation_status(user_id, rec_artist, rec_album, "owned")
    
    recs = db.get_recommendations_for_user(user_id)
    target_rec = next((r for r in recs if r["artist_name"] == rec_artist and r["album_title"] == rec_album), None)
    
    if target_rec and target_rec["status"] == "owned":
        print("✓ Recommendation updated correctly")
    else:
        print(f"✗ Recommendation update FAILED. Status is {target_rec['status'] if target_rec else 'None'}")

    # Cleanup
    print("Cleaning up...")
    # (Optional: delete user and data if needed, but for now we leave it or manual cleanup)

if __name__ == "__main__":
    try:
        test_sync_logic()
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
