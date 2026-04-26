"""Geo enrichment from IP address using GeoIP2 (MaxMind GeoLite2).

The database file path is controlled by GEOIP_DB_PATH env var.
Falls back gracefully if the database is not available.
"""

from __future__ import annotations
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_reader = None
_load_attempted = False


@dataclass
class GeoResult:
    country_code: str | None = None
    city: str | None = None
    isp: str | None = None


def _get_reader():
    global _reader, _load_attempted
    if _load_attempted:
        return _reader
    _load_attempted = True
    db_path = os.environ.get("GEOIP_DB_PATH")
    if not db_path or not os.path.isfile(db_path):
        logger.warning("GEOIP_DB_PATH not set or file missing — geo lookup disabled")
        return None
    try:
        import geoip2.database  # type: ignore

        _reader = geoip2.database.Reader(db_path)
        logger.info("GeoIP2 database loaded from %s", db_path)
    except ImportError:
        logger.warning("geoip2 package not installed — geo lookup disabled")
    except Exception as exc:
        logger.warning("Failed to load GeoIP2 database: %s", exc)
    return _reader


def lookup(ip: str) -> GeoResult:
    reader = _get_reader()
    if reader is None:
        return GeoResult()
    try:
        response = reader.city(ip)
        return GeoResult(
            country_code=response.country.iso_code,
            city=response.city.name,
            isp=response.traits.autonomous_system_organization,
        )
    except Exception as exc:
        logger.warning("geo_lookup_failed ip_hash=<redacted> error=%s", exc)
        return GeoResult()
