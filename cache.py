"""SQLite cache for fast page/database lookups by name."""

from pathlib import Path
from typing import Any

import aiosqlite
import yaml

# Constants
CACHE_DIR = Path.home() / ".notion-lite"
CACHE_DB = CACHE_DIR / "cache.db"
UUID_LENGTH = 32
HEX_CHARS = set("0123456789abcdef")

# SQL
SQL_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS pages (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        path TEXT
    )
"""
SQL_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_name ON pages(name)"
SQL_UPSERT = "INSERT OR REPLACE INTO pages (id, name, type, path) VALUES (?, ?, ?, ?)"
SQL_SELECT_BY_NAME = "SELECT * FROM pages WHERE LOWER(name) = LOWER(?)"
SQL_SELECT_BY_ID = "SELECT * FROM pages WHERE id = ?"
SQL_SEARCH = "SELECT * FROM pages WHERE name LIKE ? OR path LIKE ?"


async def init_cache() -> None:
    """Initialize cache database and seed from config."""
    CACHE_DIR.mkdir(exist_ok=True)

    async with aiosqlite.connect(CACHE_DB) as db:
        await db.execute(SQL_CREATE_TABLE)
        await db.execute(SQL_CREATE_INDEX)
        await db.commit()

    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        await seed_from_config(config_path)


async def seed_from_config(config_path: Path) -> None:
    """Seed cache from config.yaml."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    cache_seed = config.get("cache_seed", [])
    if not cache_seed:
        return

    async with aiosqlite.connect(CACHE_DB) as db:
        for entry in cache_seed:
            await _upsert_entry(db, entry)
        await db.commit()


async def _upsert_entry(db: aiosqlite.Connection, entry: dict[str, Any]) -> None:
    """Insert or update a single cache entry."""
    page_id = normalize_id(entry.get("id", ""))
    name = entry.get("name", "")
    if not page_id or not name:
        return

    page_type = entry.get("type", "page")
    path = entry.get("path", "")
    await db.execute(SQL_UPSERT, (page_id, name, page_type, path))


def normalize_id(page_id: str) -> str:
    """Remove dashes from UUID."""
    return page_id.replace("-", "")


def format_id(page_id: str) -> str:
    """Add dashes to 32-char hex string to form UUID."""
    clean = normalize_id(page_id)
    if len(clean) != UUID_LENGTH:
        return page_id
    return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"


def is_valid_uuid(value: str) -> bool:
    """Check if value is a valid 32-char hex UUID (without dashes)."""
    return len(value) == UUID_LENGTH and all(c in HEX_CHARS for c in value.lower())


async def get_by_name(name: str) -> dict[str, Any] | None:
    """Get cached page/database by name (case-insensitive)."""
    return await _fetch_one(SQL_SELECT_BY_NAME, (name,))


async def get_by_id(page_id: str) -> dict[str, Any] | None:
    """Get cached page/database by ID."""
    normalized = normalize_id(page_id)
    return await _fetch_one(SQL_SELECT_BY_ID, (normalized,))


async def _fetch_one(sql: str, params: tuple) -> dict[str, Any] | None:
    """Execute query and return first row as dict, or None."""
    async with aiosqlite.connect(CACHE_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def resolve_id(name_or_id: str) -> str:
    """Resolve a name or ID to a formatted UUID."""
    clean = normalize_id(name_or_id)
    if is_valid_uuid(clean):
        return format_id(clean)

    cached = await get_by_name(name_or_id)
    if cached:
        return format_id(cached["id"])

    return name_or_id


async def cache_page(
    page_id: str, name: str, page_type: str = "page", path: str = ""
) -> None:
    """Add or update a page in the cache."""
    normalized = normalize_id(page_id)
    async with aiosqlite.connect(CACHE_DB) as db:
        await db.execute(SQL_UPSERT, (normalized, name, page_type, path))
        await db.commit()


async def search_cache(query: str) -> list[dict[str, Any]]:
    """Search cache for pages matching query by name or path."""
    pattern = f"%{query}%"
    async with aiosqlite.connect(CACHE_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(SQL_SEARCH, (pattern, pattern)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
