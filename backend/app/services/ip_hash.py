"""IP address hashing for privacy-preserving storage.

Raw IPs are never stored. The hash uses SHA-256 with a per-environment salt
from the GA_IP_HASH_SALT environment variable. Never rotates (by design)
to preserve cross-window joins.
"""

import hashlib
import os


_salt: bytes | None = None


def _get_salt() -> bytes:
    global _salt
    if _salt is None:
        raw = os.environ.get("GA_IP_HASH_SALT", "")
        if not raw:
            raise RuntimeError("GA_IP_HASH_SALT environment variable not set")
        _salt = raw.encode()
    return _salt


def hash_ip(ip: str) -> bytes:
    """Return salted SHA-256 of the IP as raw bytes (32 bytes)."""
    return hashlib.sha256(_get_salt() + ip.encode()).digest()
