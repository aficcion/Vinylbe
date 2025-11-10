from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Track(BaseModel):
    id: str
    name: str
    artists: List[str]
    album_id: str
    album_name: str
    album_artists: List[str]
    popularity: int = 0
    preview_url: Optional[str] = None


class Artist(BaseModel):
    id: str
    name: str
    genres: List[str] = []
    popularity: int = 0
    followers: int = 0


class Album(BaseModel):
    id: str
    name: str
    artists: List[str]
    release_date: Optional[str] = None
    total_tracks: int = 0
    upc: Optional[str] = None
    image_url: Optional[str] = None


class DiscogsRelease(BaseModel):
    release_id: int
    title: str
    artist: str
    year: Optional[int] = None
    format: str = "Vinyl"
    country: Optional[str] = None
    label: Optional[str] = None
    catno: Optional[str] = None
    thumb: Optional[str] = None


class DiscogsStats(BaseModel):
    release_id: int
    lowest_price: Optional[float] = None
    currency: str = "EUR"
    num_for_sale: int = 0
    sell_list_url: str


class ScoredTrack(BaseModel):
    track: Track
    position: int
    time_range: str
    score: float


class ScoredArtist(BaseModel):
    artist: Artist
    position: int
    score: float


class AlbumRecommendation(BaseModel):
    album: Album
    score: float
    track_count: int
    artist_boost: bool = False
    discogs_release: Optional[DiscogsRelease] = None
    discogs_stats: Optional[DiscogsStats] = None


class ServiceHealth(BaseModel):
    service_name: str
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    response_time_ms: Optional[float] = None
    error: Optional[str] = None


class LogEvent(BaseModel):
    service: str
    level: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Optional[dict] = None
