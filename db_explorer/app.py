#!/usr/bin/env python3
"""
Web-based Database Explorer for Vinylbe
A beautiful UI to explore and manage your SQLite database
"""

from flask import Flask, render_template, jsonify, request
import sqlite3
from typing import List, Dict, Any
import os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vinylbe.db")

def dict_factory(cursor, row):
    """Convert row to dictionary"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_connection():
    """Get database connection with improved concurrency handling"""
    # Use a longer timeout (30 seconds) to handle locked database
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = dict_factory
    
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Enable WAL mode for better concurrency
    # WAL mode allows multiple readers and one writer at the same time
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception as e:
        print(f"Warning: Could not enable WAL mode: {e}")
    
    return conn


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/summary')
def api_summary():
    """Get database summary"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get table counts
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row['name'] for row in cursor.fetchall()]
    
    table_counts = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        table_counts[table] = cursor.fetchone()['count']
    
    # Top artists by album count
    cursor.execute("""
        SELECT a.name, a.image_url, COUNT(al.id) as album_count
        FROM artists a
        LEFT JOIN albums al ON a.id = al.artist_id
        GROUP BY a.id
        ORDER BY album_count DESC
        LIMIT 10
    """)
    top_artists = cursor.fetchall()
    
    # Top rated albums
    cursor.execute("""
        SELECT ar.name as artist, ar.image_url as artist_image, 
               al.title, al.year, al.rating, al.votes, al.cover_url
        FROM albums al
        JOIN artists ar ON al.artist_id = ar.id
        WHERE al.rating IS NOT NULL
        ORDER BY al.rating DESC, al.votes DESC
        LIMIT 10
    """)
    top_albums = cursor.fetchall()
    
    # Recent albums
    cursor.execute("""
        SELECT ar.name as artist, al.title, al.year, al.rating, al.cover_url
        FROM albums al
        JOIN artists ar ON al.artist_id = ar.id
        WHERE al.year != ''
        ORDER BY al.year DESC
        LIMIT 10
    """)
    recent_albums = cursor.fetchall()
    
    # User stats
    cursor.execute("""
        SELECT u.id, u.display_name, u.email,
               COUNT(DISTINCT r.id) as rec_count,
               COUNT(DISTINCT CASE WHEN r.status = 'favorite' THEN r.id END) as favorites
        FROM user u
        LEFT JOIN recommendation r ON u.id = r.user_id
        GROUP BY u.id
        ORDER BY rec_count DESC
    """)
    users = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'table_counts': table_counts,
        'top_artists': top_artists,
        'top_albums': top_albums,
        'recent_albums': recent_albums,
        'users': users
    })

@app.route('/api/artists')
def api_artists():
    """Get artists with pagination and search"""
    conn = get_connection()
    cursor = conn.cursor()
    
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    
    # Get total count
    if search:
        cursor.execute("""
            SELECT COUNT(*) as count FROM artists WHERE name LIKE ?
        """, (f"%{search}%",))
    else:
        cursor.execute("SELECT COUNT(*) as count FROM artists")
    
    total = cursor.fetchone()['count']
    
    # Get artists
    if search:
        cursor.execute("""
            SELECT a.*, 
                   (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) as album_count
            FROM artists a
            WHERE a.name LIKE ?
            ORDER BY a.name
            LIMIT ? OFFSET ?
        """, (f"%{search}%", per_page, offset))
    else:
        cursor.execute("""
            SELECT a.*, 
                   (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) as album_count
            FROM artists a
            ORDER BY a.name
            LIMIT ? OFFSET ?
        """, (per_page, offset))
    
    artists = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'artists': artists,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/artist/<int:artist_id>')
def api_artist_detail(artist_id):
    """Get artist details with albums"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get artist
    cursor.execute("SELECT * FROM artists WHERE id = ?", (artist_id,))
    artist = cursor.fetchone()
    
    if not artist:
        conn.close()
        return jsonify({'error': 'Artist not found'}), 404
    
    # Get albums
    cursor.execute("""
        SELECT * FROM albums 
        WHERE artist_id = ?
        ORDER BY year, title
    """, (artist_id,))
    albums = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'artist': artist,
        'albums': albums
    })

@app.route('/api/albums')
def api_albums():
    """Get albums with pagination and search"""
    conn = get_connection()
    cursor = conn.cursor()
    
    search = request.args.get('search', '')
    artist_id = request.args.get('artist_id', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    
    # Build query
    where_clauses = []
    params = []
    
    if search:
        where_clauses.append("(al.title LIKE ? OR ar.name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    if artist_id:
        where_clauses.append("al.artist_id = ?")
        params.append(artist_id)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Get total count
    cursor.execute(f"""
        SELECT COUNT(*) as count 
        FROM albums al
        JOIN artists ar ON al.artist_id = ar.id
        WHERE {where_sql}
    """, params)
    total = cursor.fetchone()['count']
    
    # Get albums
    cursor.execute(f"""
        SELECT al.*, ar.name as artist_name, ar.image_url as artist_image
        FROM albums al
        JOIN artists ar ON al.artist_id = ar.id
        WHERE {where_sql}
        ORDER BY ar.name, al.year, al.title
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    
    albums = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'albums': albums,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/album/<int:album_id>')
def api_album_detail(album_id):
    """Get album details"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get album with artist name
    cursor.execute("""
        SELECT al.*, ar.name as artist_name
        FROM albums al
        JOIN artists ar ON al.artist_id = ar.id
        WHERE al.id = ?
    """, (album_id,))
    album = cursor.fetchone()
    
    conn.close()
    
    if not album:
        return jsonify({'error': 'Album not found'}), 404
    
    return jsonify({'album': album})


@app.route('/api/users')
def api_users():
    """Get all users with their stats"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT u.*,
               COUNT(DISTINCT r.id) as total_recommendations,
               COUNT(DISTINCT CASE WHEN r.status = 'favorite' THEN r.id END) as favorites,
               COUNT(DISTINCT CASE WHEN r.status = 'owned' THEN r.id END) as owned,
               COUNT(DISTINCT usa.id) as selected_artists
        FROM user u
        LEFT JOIN recommendation r ON u.id = r.user_id
        LEFT JOIN user_selected_artist usa ON u.id = usa.user_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
    
    users = cursor.fetchall()
    conn.close()
    
    return jsonify({'users': users})

@app.route('/api/user/<int:user_id>')
def api_user_detail(user_id):
    """Get user details"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get user with stats
    cursor.execute("""
        SELECT u.*,
               COUNT(DISTINCT r.id) as total_recommendations,
               COUNT(DISTINCT CASE WHEN r.status = 'favorite' THEN r.id END) as favorites,
               COUNT(DISTINCT usa.id) as selected_artists
        FROM user u
        LEFT JOIN recommendation r ON u.id = r.user_id
        LEFT JOIN user_selected_artist usa ON u.id = usa.user_id
        WHERE u.id = ?
        GROUP BY u.id
    """, (user_id,))
    user = cursor.fetchone()
    
    conn.close()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({'user': user})


@app.route('/api/user/<int:user_id>/recommendations')
def api_user_recommendations(user_id):
    """Get recommendations for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM recommendation
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))
    
    recommendations = cursor.fetchall()
    conn.close()
    
    return jsonify({'recommendations': recommendations})

@app.route('/api/search')
def api_search():
    """Global search across artists and albums"""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'artists': [], 'albums': []})
    
    # Search artists
    cursor.execute("""
        SELECT a.*, 
               (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) as album_count
        FROM artists a
        WHERE a.name LIKE ?
        ORDER BY a.name
        LIMIT 10
    """, (f"%{query}%",))
    artists = cursor.fetchall()
    
    # Search albums
    cursor.execute("""
        SELECT al.*, ar.name as artist_name
        FROM albums al
        JOIN artists ar ON al.artist_id = ar.id
        WHERE al.title LIKE ? OR ar.name LIKE ?
        ORDER BY ar.name, al.title
        LIMIT 10
    """, (f"%{query}%", f"%{query}%"))
    albums = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'artists': artists,
        'albums': albums
    })

@app.route('/api/stats')
def api_stats():
    """Get various statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Albums by decade
    cursor.execute("""
        SELECT 
            CASE 
                WHEN year LIKE '196%' THEN '1960s'
                WHEN year LIKE '197%' THEN '1970s'
                WHEN year LIKE '198%' THEN '1980s'
                WHEN year LIKE '199%' THEN '1990s'
                WHEN year LIKE '200%' THEN '2000s'
                WHEN year LIKE '201%' THEN '2010s'
                WHEN year LIKE '202%' THEN '2020s'
                ELSE 'Unknown'
            END as decade,
            COUNT(*) as count
        FROM albums
        WHERE year != ''
        GROUP BY decade
        ORDER BY decade
    """)
    by_decade = cursor.fetchall()
    
    # Rating distribution
    cursor.execute("""
        SELECT 
            CASE 
                WHEN rating >= 4.5 THEN '4.5-5.0'
                WHEN rating >= 4.0 THEN '4.0-4.5'
                WHEN rating >= 3.5 THEN '3.5-4.0'
                WHEN rating >= 3.0 THEN '3.0-3.5'
                WHEN rating >= 2.5 THEN '2.5-3.0'
                ELSE '0-2.5'
            END as rating_range,
            COUNT(*) as count
        FROM albums
        WHERE rating IS NOT NULL
        GROUP BY rating_range
        ORDER BY rating_range DESC
    """)
    by_rating = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'by_decade': by_decade,
        'by_rating': by_rating
    })

@app.route('/api/update/artist/<int:artist_id>', methods=['POST'])
def api_update_artist(artist_id):
    """Update artist information"""
    conn = get_connection()
    cursor = conn.cursor()
    
    data = request.json
    
    cursor.execute("""
        UPDATE artists 
        SET name = ?, image_url = ?
        WHERE id = ?
    """, (data.get('name'), data.get('image_url'), artist_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/update/album/<int:album_id>', methods=['POST'])
def api_update_album(album_id):
    """Update album information"""
    conn = get_connection()
    cursor = conn.cursor()
    
    data = request.json
    
    cursor.execute("""
        UPDATE albums 
        SET title = ?, year = ?, cover_url = ?
        WHERE id = ?
    """, (data.get('title'), data.get('year'), data.get('cover_url'), album_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/delete/artist/<int:artist_id>', methods=['DELETE'])
def api_delete_artist(artist_id):
    """Delete an artist and their albums"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Delete albums first
    cursor.execute("DELETE FROM albums WHERE artist_id = ?", (artist_id,))
    # Delete artist
    cursor.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/delete/album/<int:album_id>', methods=['DELETE'])
def api_delete_album(album_id):
    """Delete an album"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM albums WHERE id = ?", (album_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/update/user/<int:user_id>', methods=['POST'])
def api_update_user(user_id):
    """Update user information"""
    conn = get_connection()
    cursor = conn.cursor()
    
    data = request.json
    
    cursor.execute("""
        UPDATE user 
        SET display_name = ?, email = ?
        WHERE id = ?
    """, (data.get('display_name'), data.get('email'), user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/delete/user/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    """Delete a user and all associated data"""
    import time
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Verify foreign keys are enabled
            cursor.execute("PRAGMA foreign_keys;")
            fk_status = cursor.fetchone()
            print(f"Foreign keys status: {fk_status}")
            
            # Get user info before deletion for logging
            cursor.execute("SELECT display_name FROM user WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
            
            # SQLite will handle CASCADE deletes for auth_identity, user_profile_lastfm,
            # user_selected_artist, and recommendation tables due to foreign key constraints
            cursor.execute("DELETE FROM user WHERE id = ?", (user_id,))
            
            rows_deleted = cursor.rowcount
            print(f"Deleted user {user_id} ({user['display_name']}), rows affected: {rows_deleted}")
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': f'Usuario eliminado correctamente'})
            
        except sqlite3.OperationalError as e:
            if conn:
                conn.rollback()
                conn.close()
            
            error_msg = str(e)
            print(f"Attempt {attempt + 1}/{max_retries} - Error deleting user {user_id}: {error_msg}")
            
            # If database is locked and we have retries left, wait and try again
            if "database is locked" in error_msg.lower() and attempt < max_retries - 1:
                print(f"Database is locked. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                # Last attempt failed or different error
                return jsonify({
                    'success': False, 
                    'error': f'La base de datos está bloqueada. Por favor, cierra cualquier aplicación que esté usando la base de datos (como DB Browser, DB Bro, etc.) e intenta de nuevo.'
                }), 500
                
        except Exception as e:
            if conn:
                conn.rollback()
                conn.close()
            print(f"Error deleting user {user_id}: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # Should not reach here, but just in case
    return jsonify({'success': False, 'error': 'Error desconocido al eliminar usuario'}), 500


if __name__ == '__main__':
    print("\n" + "="*70)
    print("🎵 VINYLBE DATABASE EXPLORER")
    print("="*70)
    print(f"\n📂 Database: {DB_PATH}")
    print(f"🌐 Opening at: http://localhost:5001")
    print("\n💡 Press Ctrl+C to stop the server")
    print("="*70 + "\n")
    
    app.run(debug=True, port=5001, host='0.0.0.0')
