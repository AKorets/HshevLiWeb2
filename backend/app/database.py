from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def _normalise_url(url: str) -> tuple[str, bool]:
    """Convert postgres:// or postgresql:// to postgresql+asyncpg://.

    Returns (url, needs_ssl) — asyncpg does not accept sslmode as a query
    parameter so we strip it and signal the caller to pass ssl via connect_args.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    parts = urlsplit(url)
    qs = parse_qs(parts.query)
    needs_ssl = "sslmode" in qs
    qs.pop("sslmode", None)
    return urlunsplit(parts._replace(query=urlencode(qs, doseq=True))), needs_ssl


def init_db(database_url: str) -> None:
    global _engine, _session_factory
    url, needs_ssl = _normalise_url(database_url)
    connect_args: dict = {}
    if needs_ssl:
        connect_args["ssl"] = "require"
    _engine = create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker:
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _session_factory
