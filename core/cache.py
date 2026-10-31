"""Disk caching layer for EmberRoute.

Provides disk-based caching under CACHE_DIR with sidecar metadata JSON files.
Complies with non-negotiable data rules:
- Every cached item tracks source, url, fetched_at_utc, and TTL.
- On FeedError, cached_or_fetch falls back to stale cache with is_stale=True.
- Never silently presents stale data as fresh.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, Union
import warnings

from core.config import get_settings
from core.errors import FeedError, StaleCacheWarning
from core.models import ProvenanceRecord

logger = logging.getLogger(__name__)


def make_provenance_record(
    name: str,
    source: str,
    url: str,
    fetched_at_utc: datetime,
    ttl_s: int,
    is_stale: bool = False,
    note: str = "",
) -> ProvenanceRecord:
    """Factory creating a ProvenanceRecord."""
    return ProvenanceRecord(
        name=name,
        source=source,
        url=url,
        fetched_at_utc=fetched_at_utc,
        ttl_s=ttl_s,
        is_stale=is_stale,
        note=note,
    )


def _get_cache_dir() -> Path:
    """Return cache directory path, ensuring it exists."""
    cache_path = Path(get_settings().CACHE_DIR)
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path


def _hash_key(key: str) -> str:
    """Convert arbitrary key string to SHA-256 hex string."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def put(key: str, payload: bytes, source: str, url: str, note: str = "") -> ProvenanceRecord:
    """Store payload bytes and sidecar metadata on disk.

    Args:
        key: Unique cache key.
        payload: Binary data bytes to store.
        source: Data source name (e.g. 'NASA FIRMS', 'Open-Meteo').
        url: URL endpoint.
        note: Optional audit note.

    Returns:
        ProvenanceRecord for the newly cached entry.
    """
    cache_dir = _get_cache_dir()
    h = _hash_key(key)
    bin_file = cache_dir / f"{h}.bin"
    meta_file = cache_dir / f"{h}.json"

    now_utc = datetime.now(timezone.utc)
    bin_file.write_bytes(payload)

    meta_dict = {
        "name": key,
        "source": source,
        "url": url,
        "fetched_at_utc": now_utc.isoformat(),
        "note": note,
    }
    meta_file.write_text(json.dumps(meta_dict, indent=2), encoding="utf-8")

    logger.info("Cached fresh payload for key '%s' from %s", key, source)
    return make_provenance_record(
        name=key,
        source=source,
        url=url,
        fetched_at_utc=now_utc,
        ttl_s=0,
        is_stale=False,
        note=note,
    )


def get(key: str, ttl_s: int) -> Tuple[Optional[bytes], Optional[ProvenanceRecord]]:
    """Retrieve payload and metadata if fresh within TTL.

    Args:
        key: Cache key.
        ttl_s: Time-to-live in seconds.

    Returns:
        (payload, meta) if found and fresh.
        (None, meta) if expired.
        (None, None) if not found.
    """
    cache_dir = _get_cache_dir()
    h = _hash_key(key)
    bin_file = cache_dir / f"{h}.bin"
    meta_file = cache_dir / f"{h}.json"

    if not bin_file.exists() or not meta_file.exists():
        return None, None

    try:
        meta_dict = json.loads(meta_file.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(meta_dict["fetched_at_utc"])
        now_utc = datetime.now(timezone.utc)
        age_s = (now_utc - fetched_at).total_seconds()
        is_expired = age_s > ttl_s

        meta = make_provenance_record(
            name=meta_dict.get("name", key),
            source=meta_dict.get("source", "disk_cache"),
            url=meta_dict.get("url", ""),
            fetched_at_utc=fetched_at,
            ttl_s=ttl_s,
            is_stale=is_expired,
            note=meta_dict.get("note", ""),
        )

        if is_expired:
            return None, meta

        payload = bin_file.read_bytes()
        return payload, meta
    except Exception as e:
        logger.warning("Error reading cache for key '%s': %s", key, e)
        return None, None


def cached_or_fetch(
    key: str,
    ttl_s: int,
    fetch_fn: Callable[[], Union[bytes, Tuple[bytes, str, str]]],
    allow_stale: bool = True,
) -> Tuple[bytes, ProvenanceRecord]:
    """Retrieve fresh cache or invoke fetch_fn. Fall back to stale cache on FeedError.

    Args:
        key: Unique cache key.
        ttl_s: Validity period in seconds.
        fetch_fn: Callable returning bytes or (bytes, source, url).
        allow_stale: Whether to return expired cache if fetch_fn raises FeedError.

    Returns:
        Tuple of (payload_bytes, ProvenanceRecord).

    Raises:
        FeedError: If fetch fails and no stale cache exists (or allow_stale is False).
    """
    payload, meta = get(key, ttl_s)
    if payload is not None and meta is not None:
        return payload, meta

    # Cache is expired or missing; attempt network fetch
    try:
        result = fetch_fn()
        if isinstance(result, tuple) and len(result) >= 3:
            data, source, url = result[0], result[1], result[2]
        else:
            data = result
            source = "network_fetch"
            url = key

        record = put(key, data, source, url)
        # Update record TTL
        record.ttl_s = ttl_s
        return data, record
    except FeedError as err:
        if allow_stale:
            # Check if any stale data exists on disk
            cache_dir = _get_cache_dir()
            h = _hash_key(key)
            bin_file = cache_dir / f"{h}.bin"
            meta_file = cache_dir / f"{h}.json"

            if bin_file.exists() and meta_file.exists():
                try:
                    meta_dict = json.loads(meta_file.read_text(encoding="utf-8"))
                    fetched_at = datetime.fromisoformat(meta_dict["fetched_at_utc"])
                    stale_data = bin_file.read_bytes()
                    stale_record = make_provenance_record(
                        name=meta_dict.get("name", key),
                        source=meta_dict.get("source", "disk_cache"),
                        url=meta_dict.get("url", ""),
                        fetched_at_utc=fetched_at,
                        ttl_s=ttl_s,
                        is_stale=True,
                        note="Stale cache fallback due to feed error",
                    )
                    warn_msg = f"Live fetch failed for {key}: {err}. Returning stale cache from {fetched_at} UTC."
                    warnings.warn(warn_msg, StaleCacheWarning)
                    logger.warning(warn_msg)
                    return stale_data, stale_record
                except Exception as read_err:
                    logger.error("Failed reading stale cache for %s: %s", key, read_err)

        # No stale cache available or allow_stale=False -> re-raise
        raise err

