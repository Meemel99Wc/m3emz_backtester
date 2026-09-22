"""
m3emz Backtester — Incremental Data Cache (Parquet)
Caches OHLCV data to disk, fetches only new candles on subsequent runs.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CACHE_DIR = Path.home() / ".m3emz" / "cache"
INDEX_FILE = CACHE_DIR / "index.json"


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> dict:
    _ensure_cache_dir()
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_index(index: dict):
    _ensure_cache_dir()
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2, default=str)


def _cache_key(symbol: str, interval: str) -> str:
    return f"{symbol.upper()}_{interval}"


def _cache_path(symbol: str, interval: str) -> Path:
    return CACHE_DIR / f"{_cache_key(symbol, interval)}.parquet"


def get_cached_df(symbol: str, interval: str) -> pd.DataFrame | None:
    """Load cached data if it exists."""
    path = _cache_path(symbol, interval)
    if path.exists():
        try:
            df = pd.read_parquet(path)
            if not df.empty:
                return df
        except Exception:
            pass
    return None


def get_cache_last_timestamp(symbol: str, interval: str) -> int | None:
    """Return the last candle open timestamp in ms, or None if no cache."""
    df = get_cached_df(symbol, interval)
    if df is not None and not df.empty:
        last_ts = df.index[-1]
        if hasattr(last_ts, "timestamp"):
            return int(last_ts.timestamp() * 1000)
    return None


def save_to_cache(symbol: str, interval: str, df: pd.DataFrame):
    """Save/append data to Parquet cache."""
    _ensure_cache_dir()
    path = _cache_path(symbol, interval)
    key = _cache_key(symbol, interval)

    existing = get_cached_df(symbol, interval)
    if existing is not None and not existing.empty:
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
    else:
        combined = df

    combined.to_parquet(path, engine="pyarrow")

    # Update index
    index = _load_index()
    file_size = path.stat().st_size / (1024 * 1024)
    index[key] = {
        "candles": len(combined),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "file_size_mb": round(file_size, 3),
        "first_date": str(combined.index[0]),
        "last_date": str(combined.index[-1]),
    }
    _save_index(index)


def get_cache_info(symbol: str, interval: str) -> dict | None:
    """Get cache metadata for a symbol/interval pair."""
    key = _cache_key(symbol, interval)
    index = _load_index()
    return index.get(key)


def get_all_cache_info() -> dict:
    """Get all cache metadata."""
    return _load_index()


def delete_cache(symbol: str, interval: str):
    """Delete cache for a specific symbol/interval."""
    path = _cache_path(symbol, interval)
    key = _cache_key(symbol, interval)
    if path.exists():
        path.unlink()
    index = _load_index()
    index.pop(key, None)
    _save_index(index)


def clear_all_cache():
    """Delete all cached data."""
    import shutil
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    _ensure_cache_dir()
    _save_index({})
