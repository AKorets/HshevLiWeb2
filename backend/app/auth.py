import hmac

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from .config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(_api_key_header)) -> None:
    """Enforce API key. Returns 503 when key is not configured, 401 on mismatch."""
    if not settings.api_secret_key:
        raise HTTPException(status_code=503, detail="API_SECRET_KEY not configured on server")
    if not api_key or not hmac.compare_digest(settings.api_secret_key, api_key):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing API key")
