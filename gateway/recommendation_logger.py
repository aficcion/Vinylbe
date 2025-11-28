"""
Recommendation Generation Logger
Logs all recommendations generated from artist search with detailed metadata.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Create logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Log file paths
RECOMMENDATIONS_LOG = LOGS_DIR / "recommendations_generation.jsonl"
DAILY_SUMMARY_LOG = LOGS_DIR / "daily_summary.json"


def log_recommendation_generation(
    user_id: int,
    artist_name: str,
    source: str,  # 'canonical' or 'spotify'
    recommendations: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Log a recommendation generation event.
    
    Args:
        user_id: ID of the user requesting recommendations
        artist_name: Name of the artist being searched
        source: Source of recommendations ('canonical' or 'spotify')
        recommendations: List of recommendation objects
        metadata: Additional metadata (e.g., cache hits, errors)
    """
    timestamp = datetime.utcnow().isoformat()
    
    log_entry = {
        "timestamp": timestamp,
        "user_id": user_id,
        "artist_name": artist_name,
        "source": source,
        "recommendations_count": len(recommendations),
        "recommendations": [
            {
                "album_name": rec.get("album_name"),
                "artist_name": rec.get("artist_name"),
                "year": rec.get("year"),
                "rating": rec.get("rating"),
                "is_partial": rec.get("is_partial", 0),
                "spotify_id": rec.get("spotify_id"),
                "discogs_master_id": rec.get("discogs_master_id"),
                "source": rec.get("source")
            }
            for rec in recommendations
        ],
        "metadata": metadata or {}
    }
    
    # Append to JSONL file (one JSON object per line)
    with open(RECOMMENDATIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    # Update daily summary
    _update_daily_summary(source, len(recommendations))
    
    return log_entry


def log_search_session(
    user_id: int,
    session_data: Dict[str, Any]
):
    """
    Log a complete search session (multiple artists).
    
    Args:
        user_id: ID of the user
        session_data: Complete session data including all artists processed
    """
    timestamp = datetime.utcnow().isoformat()
    
    session_entry = {
        "timestamp": timestamp,
        "user_id": user_id,
        "session_type": "artist_search",
        "total_artists": session_data.get("total_artists", 0),
        "total_recommendations": session_data.get("total_recommendations", 0),
        "canonical_count": session_data.get("canonical_count", 0),
        "spotify_fallback_count": session_data.get("spotify_fallback_count", 0),
        "failed_artists": session_data.get("failed_artists", []),
        "duration_seconds": session_data.get("duration_seconds", 0),
        "artists_processed": session_data.get("artists_processed", [])
    }
    
    # Log to sessions file
    sessions_log = LOGS_DIR / "search_sessions.jsonl"
    with open(sessions_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(session_entry, ensure_ascii=False) + "\n")
    
    return session_entry


def _update_daily_summary(source: str, count: int):
    """Update daily summary statistics."""
    today = datetime.utcnow().date().isoformat()
    
    # Load existing summary
    summary = {}
    if DAILY_SUMMARY_LOG.exists():
        with open(DAILY_SUMMARY_LOG, "r", encoding="utf-8") as f:
            summary = json.load(f)
    
    # Initialize today's entry if needed
    if today not in summary:
        summary[today] = {
            "date": today,
            "canonical_recommendations": 0,
            "spotify_recommendations": 0,
            "total_recommendations": 0,
            "unique_artists": set()
        }
    
    # Update counts
    if source == "canonical":
        summary[today]["canonical_recommendations"] += count
    elif source == "spotify":
        summary[today]["spotify_recommendations"] += count
    
    summary[today]["total_recommendations"] += count
    
    # Convert sets to lists for JSON serialization
    for date_key in summary:
        if isinstance(summary[date_key].get("unique_artists"), set):
            summary[date_key]["unique_artists"] = list(summary[date_key]["unique_artists"])
    
    # Save summary
    with open(DAILY_SUMMARY_LOG, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


def get_recent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Get the most recent log entries."""
    if not RECOMMENDATIONS_LOG.exists():
        return []
    
    logs = []
    with open(RECOMMENDATIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))
    
    # Return most recent entries
    return logs[-limit:]


def get_logs_by_timerange(start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Get logs within a specific time range."""
    if not RECOMMENDATIONS_LOG.exists():
        return []
    
    logs = []
    with open(RECOMMENDATIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if start_time <= entry_time <= end_time:
                    logs.append(entry)
    
    return logs


def get_stats_summary(days: int = 7) -> Dict[str, Any]:
    """Get summary statistics for the last N days."""
    if not DAILY_SUMMARY_LOG.exists():
        return {"error": "No summary data available"}
    
    with open(DAILY_SUMMARY_LOG, "r", encoding="utf-8") as f:
        summary = json.load(f)
    
    # Get recent days
    from datetime import timedelta
    today = datetime.utcnow().date()
    recent_dates = [(today - timedelta(days=i)).isoformat() for i in range(days)]
    
    stats = {
        "period_days": days,
        "total_canonical": 0,
        "total_spotify": 0,
        "total_recommendations": 0,
        "daily_breakdown": []
    }
    
    for date in recent_dates:
        if date in summary:
            day_data = summary[date]
            stats["total_canonical"] += day_data.get("canonical_recommendations", 0)
            stats["total_spotify"] += day_data.get("spotify_recommendations", 0)
            stats["total_recommendations"] += day_data.get("total_recommendations", 0)
            stats["daily_breakdown"].append(day_data)
    
    return stats
