"""
SQLite-backed cache with per-entry TTL and API request logging.
Zero external dependencies — uses stdlib sqlite3 only.
"""

import json
import sqlite3
import time
import hashlib
from pathlib import Path
from typing import Any

from config.settings import CACHE_DB_PATH, CACHE_TTL_SECONDS


def _db_path() -> Path:
    path = Path(CACHE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cache_entries (
            key        TEXT NOT NULL,
            ticker     TEXT NOT NULL,
            data_json  TEXT NOT NULL,
            fetched_ts INTEGER NOT NULL,
            ttl        INTEGER NOT NULL,
            PRIMARY KEY (key, ticker)
        );

        CREATE TABLE IF NOT EXISTS api_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            source     TEXT NOT NULL,
            endpoint   TEXT NOT NULL,
            ticker     TEXT,
            fetched_ts INTEGER NOT NULL
        );
    """)
    conn.commit()


# ── Public interface ──────────────────────────────────────────────────────────

def get(key: str, ticker: str) -> Any | None:
    """Return cached value or None if missing / expired."""
    with _connect() as conn:
        _init_schema(conn)
        row = conn.execute(
            "SELECT data_json, fetched_ts, ttl FROM cache_entries WHERE key=? AND ticker=?",
            (key, ticker.upper()),
        ).fetchone()

    if row is None:
        return None
    if time.time() - row["fetched_ts"] > row["ttl"]:
        return None  # expired — caller will overwrite on next set()
    return json.loads(row["data_json"])


def set(key: str, ticker: str, data: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Upsert a cache entry."""
    with _connect() as conn:
        _init_schema(conn)
        conn.execute(
            """
            INSERT INTO cache_entries (key, ticker, data_json, fetched_ts, ttl)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key, ticker) DO UPDATE SET
                data_json  = excluded.data_json,
                fetched_ts = excluded.fetched_ts,
                ttl        = excluded.ttl
            """,
            (key, ticker.upper(), json.dumps(data), int(time.time()), ttl),
        )
        conn.commit()


def invalidate(ticker: str) -> None:
    """Remove all cache entries for a given ticker."""
    with _connect() as conn:
        _init_schema(conn)
        conn.execute(
            "DELETE FROM cache_entries WHERE ticker=?", (ticker.upper(),)
        )
        conn.commit()


def log_request(source: str, endpoint: str, ticker: str | None = None) -> None:
    """Record a live API call for rate-limit tracking."""
    with _connect() as conn:
        _init_schema(conn)
        conn.execute(
            "INSERT INTO api_log (source, endpoint, ticker, fetched_ts) VALUES (?, ?, ?, ?)",
            (source, endpoint, ticker, int(time.time())),
        )
        conn.commit()


def request_count_today(source: str) -> int:
    """Count live API calls for `source` in the last 24 hours."""
    since = int(time.time()) - 86_400
    with _connect() as conn:
        _init_schema(conn)
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM api_log WHERE source=? AND fetched_ts >= ?",
            (source, since),
        ).fetchone()
    return row["cnt"] if row else 0


def make_hash(*parts: str) -> str:
    """Stable short hash for building composite cache keys."""
    combined = "|".join(str(p) for p in parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def list_analyzed_tickers() -> list[dict]:
    """
    Return all tickers that have a saved full evaluation summary, newest first.
    Each entry: {ticker, company_name, verdict, score, ratio, analyzed_at}
    """
    with _connect() as conn:
        _init_schema(conn)
        rows = conn.execute(
            """
            SELECT ticker, data_json, fetched_ts
            FROM cache_entries
            WHERE key = 'eval:summary'
            ORDER BY fetched_ts DESC
            """
        ).fetchall()

    results = []
    for row in rows:
        try:
            data = json.loads(row["data_json"])
            results.append({
                "ticker":       row["ticker"],
                "company_name": data.get("company_name", row["ticker"]),
                "verdict":      data.get("verdict", ""),
                "total":        data.get("total", 0),
                "max_score":    data.get("max_score", 30),
                "ratio":        data.get("ratio", 0.0),
                "analyzed_at":  row["fetched_ts"],
            })
        except Exception:
            continue
    return results
