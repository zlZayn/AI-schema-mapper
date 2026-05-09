"""Rule cache: skip LLM calls when data and schema haven't changed."""

import hashlib
import json
import os

from src.local.logger import warn


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def fingerprint(unique_values: dict, exclude_columns: set[str] | None = None) -> str:
    """Hash sorted unique values per column, then hash the concatenation.

    Args:
        unique_values: Dict of column_name -> list of unique values.
        exclude_columns: Optional set of column names to exclude from fingerprint.
    """
    exclude = exclude_columns or set()
    parts = []
    for col in sorted(unique_values):
        if col in exclude:
            continue
        col_hash = _md5(json.dumps(sorted(unique_values[col]), ensure_ascii=False))[:8]
        parts.append(f"{col}:{col_hash}")
    return _md5(",".join(parts))


def schema_hash(schema_path: str) -> str:
    """Hash schema content for cache invalidation."""
    with open(schema_path, encoding="utf-8") as f:
        schema_text = f.read()
    return _md5(schema_text)


def load_cache(cache_path: str, current_schema_hash: str, fp: str) -> dict | None:
    """Return cached rules if schema and fingerprint match, else None.

    Returns None on any error (missing file, corrupted JSON, schema mismatch).
    """
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        warn(f"缓存文件损坏，跳过: {e}")
        return None
    if not isinstance(cache, dict):
        return None
    if cache.get("schema_hash") != current_schema_hash:
        return None
    entry = cache.get("entries", {}).get(fp)
    return entry


def save_cache(cache_path: str, current_schema_hash: str, fp: str, rules: dict):
    """Save rules to cache, merging with existing entry.

    Silently handles corrupted cache files by resetting them.
    """
    cache: dict = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}
    if not isinstance(cache, dict):
        cache = {}
    if cache.get("schema_hash") != current_schema_hash:
        cache = {"schema_hash": current_schema_hash, "entries": {}}
    existing = cache.setdefault("entries", {}).get(fp, {})
    existing.update(rules)
    cache["entries"][fp] = existing
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
