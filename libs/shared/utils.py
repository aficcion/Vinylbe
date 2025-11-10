import httpx
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def create_http_client(timeout: float = 15.0, headers: Optional[dict] = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers=headers or {})


def log_event(service: str, level: str, message: str, data: Optional[dict] = None):
    timestamp = datetime.utcnow().isoformat()
    log_msg = f"[{timestamp}] [{service}] [{level}] {message}"
    
    if level == "ERROR":
        logger.error(log_msg, extra={"data": data})
    elif level == "WARNING":
        logger.warning(log_msg, extra={"data": data})
    elif level == "INFO":
        logger.info(log_msg, extra={"data": data})
    else:
        logger.debug(log_msg, extra={"data": data})
    
    return {
        "service": service,
        "level": level,
        "message": message,
        "timestamp": timestamp,
        "data": data,
    }
