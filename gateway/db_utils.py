import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vinylbe.db")

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    return conn

def search_artists(query: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        sql = "SELECT * FROM artists WHERE name LIKE ? ORDER BY name LIMIT 50"
        cur.execute(sql, (f"%{query}%",))
        return cur.fetchall()
    finally:
        conn.close()

def search_albums(query: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        sql = """
            SELECT a.*, ar.name as artist_name 
            FROM albums a 
            JOIN artists ar ON a.artist_id = ar.id 
            WHERE a.title LIKE ? OR ar.name LIKE ?
            ORDER BY a.title LIMIT 50
        """
        cur.execute(sql, (f"%{query}%", f"%{query}%"))
        return cur.fetchall()
    finally:
        conn.close()

def get_all_artists(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        sql = "SELECT * FROM artists ORDER BY name LIMIT ? OFFSET ?"
        cur.execute(sql, (limit, offset))
        return cur.fetchall()
    finally:
        conn.close()

def get_all_albums(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        sql = """
            SELECT a.*, ar.name as artist_name 
            FROM albums a 
            JOIN artists ar ON a.artist_id = ar.id 
            ORDER BY a.title LIMIT ? OFFSET ?
        """
        cur.execute(sql, (limit, offset))
        return cur.fetchall()
    finally:
        conn.close()

def update_artist(artist_id: int, data: Dict[str, Any]) -> bool:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Construct update query dynamically
        fields = []
        values = []
        for key, value in data.items():
            if key != 'id':
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
            
        values.append(artist_id)
        sql = f"UPDATE artists SET {', '.join(fields)}, last_updated = ? WHERE id = ?"
        values.insert(-1, datetime.now())
        
        cur.execute(sql, values)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

def update_album(album_id: int, data: Dict[str, Any]) -> bool:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        fields = []
        values = []
        for key, value in data.items():
            if key != 'id' and key != 'artist_name': # artist_name is joined
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
            
        values.append(album_id)
        sql = f"UPDATE albums SET {', '.join(fields)}, last_updated = ? WHERE id = ?"
        values.insert(-1, datetime.now())
        
        cur.execute(sql, values)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
