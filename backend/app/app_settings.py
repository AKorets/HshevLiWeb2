import logging
from sqlalchemy import select, text
from .database import get_session_factory
from .models import AppSetting

logger = logging.getLogger(__name__)


async def get_bool(key: str, default: bool) -> bool:
    """Read a boolean app setting from the database. Returns *default* on any error."""
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            row = await session.scalar(
                select(AppSetting.value).where(AppSetting.key == key)
            )
        if row is None:
            return default
        return row.strip().lower() in ("1", "true", "yes")
    except Exception:
        logger.warning("Failed to read app setting %r from DB, using default=%s", key, default)
        return default


async def ensure_default(key: str, default_value: str) -> None:
    """Insert the setting with *default_value* if the key does not yet exist."""
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO app_settings (key, value)"
                    " VALUES (:key, :value)"
                    " ON CONFLICT (key) DO NOTHING"
                ),
                {"key": key, "value": default_value},
            )
            await session.commit()
    except Exception:
        logger.warning("Failed to ensure default for app setting %r", key)
