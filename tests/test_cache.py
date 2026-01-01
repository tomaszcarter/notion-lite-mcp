"""Tests for SQLite cache module."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cache import (
    cache_page,
    format_id,
    get_by_id,
    get_by_name,
    init_cache,
    normalize_id,
    resolve_id,
    search_cache,
)


class TestNormalizeId:
    """Tests for normalize_id function."""

    def test_removes_dashes(self):
        """Dashes are removed from UUID."""
        uuid = "8b431394-c095-4259-95c5-fc1a127a873a"
        assert normalize_id(uuid) == "8b431394c095425995c5fc1a127a873a"

    def test_already_clean(self):
        """Already clean ID is unchanged."""
        clean = "8b431394c095425995c5fc1a127a873a"
        assert normalize_id(clean) == clean

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert normalize_id("") == ""


class TestFormatId:
    """Tests for format_id function."""

    def test_adds_dashes(self):
        """Dashes are added to 32-char hex string."""
        clean = "8b431394c095425995c5fc1a127a873a"
        assert format_id(clean) == "8b431394-c095-4259-95c5-fc1a127a873a"

    def test_already_formatted(self):
        """Already formatted UUID is reformatted correctly."""
        uuid = "8b431394-c095-4259-95c5-fc1a127a873a"
        result = format_id(normalize_id(uuid))
        assert "-" in result
        assert len(result) == 36

    def test_short_string_unchanged(self):
        """Non-32-char strings are returned unchanged."""
        short = "abc123"
        assert format_id(short) == short

    def test_long_string_unchanged(self):
        """Strings longer than 32 chars are returned unchanged."""
        long = "a" * 40
        assert format_id(long) == long


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / ".notion-lite"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def mock_cache_paths(temp_cache_dir):
    """Mock cache paths to use temp directory and skip config seeding."""
    with patch("cache.CACHE_DIR", temp_cache_dir):
        with patch("cache.CACHE_DB", temp_cache_dir / "cache.db"):
            with patch("cache.seed_from_config"):
                yield temp_cache_dir


class TestInitCache:
    """Tests for init_cache function."""

    @pytest.mark.asyncio
    async def test_creates_database(self, mock_cache_paths):
        """Database is created on init."""
        await init_cache()
        db_path = mock_cache_paths / "cache.db"
        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_idempotent(self, mock_cache_paths):
        """Multiple init calls don't fail."""
        await init_cache()
        await init_cache()
        db_path = mock_cache_paths / "cache.db"
        assert db_path.exists()


class TestCachePage:
    """Tests for cache_page function."""

    @pytest.mark.asyncio
    async def test_adds_page(self, mock_cache_paths):
        """Page is added to cache."""
        await init_cache()
        await cache_page("abc123", "Test Page", "page", "Test/Path")

        result = await get_by_name("Test Page")
        assert result is not None
        assert result["name"] == "Test Page"
        assert result["type"] == "page"

    @pytest.mark.asyncio
    async def test_updates_existing(self, mock_cache_paths):
        """Existing page is updated."""
        await init_cache()
        await cache_page("abc123", "Original", "page")
        await cache_page("abc123", "Updated", "database")

        result = await get_by_id("abc123")
        assert result["name"] == "Updated"
        assert result["type"] == "database"


class TestGetByName:
    """Tests for get_by_name function."""

    @pytest.mark.asyncio
    async def test_finds_exact_match(self, mock_cache_paths):
        """Finds page by exact name."""
        await init_cache()
        await cache_page("123", "COLLECT", "page")

        result = await get_by_name("COLLECT")
        assert result is not None
        assert result["name"] == "COLLECT"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, mock_cache_paths):
        """Search is case-insensitive."""
        await init_cache()
        await cache_page("123", "COLLECT", "page")

        result = await get_by_name("collect")
        assert result is not None

        result = await get_by_name("Collect")
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cache_paths):
        """Returns None when page not found."""
        await init_cache()
        result = await get_by_name("NonExistent")
        assert result is None


class TestGetById:
    """Tests for get_by_id function."""

    @pytest.mark.asyncio
    async def test_finds_by_id(self, mock_cache_paths):
        """Finds page by ID."""
        await init_cache()
        await cache_page("abc123def456", "Test", "page")

        result = await get_by_id("abc123def456")
        assert result is not None
        assert result["name"] == "Test"

    @pytest.mark.asyncio
    async def test_normalizes_id(self, mock_cache_paths):
        """ID is normalized before lookup."""
        await init_cache()
        await cache_page("abc123def456", "Test", "page")

        # With dashes should still find it
        result = await get_by_id("abc1-23de-f456")
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cache_paths):
        """Returns None when ID not found."""
        await init_cache()
        result = await get_by_id("nonexistent")
        assert result is None


class TestResolveId:
    """Tests for resolve_id function."""

    @pytest.mark.asyncio
    async def test_resolves_name_to_id(self, mock_cache_paths):
        """Resolves cached name to formatted ID."""
        await init_cache()
        # Use a proper 32-char hex string
        await cache_page("8b431394c095425995c5fc1a127a873a", "COLLECT", "page")

        result = await resolve_id("COLLECT")
        assert "-" in result  # Should be formatted

    @pytest.mark.asyncio
    async def test_formats_raw_id(self, mock_cache_paths):
        """Raw 32-char hex ID is formatted."""
        await init_cache()
        # Use a proper 32-char hex string
        result = await resolve_id("8b431394c095425995c5fc1a127a873a")
        assert "-" in result

    @pytest.mark.asyncio
    async def test_returns_input_when_not_resolved(self, mock_cache_paths):
        """Returns input unchanged when not found and not a valid ID."""
        await init_cache()
        result = await resolve_id("some-random-string")
        assert result == "some-random-string"


class TestSearchCache:
    """Tests for search_cache function."""

    @pytest.mark.asyncio
    async def test_finds_by_name_substring(self, mock_cache_paths):
        """Finds pages by name substring."""
        await init_cache()
        await cache_page("1", "Receipt Tracker", "database")
        await cache_page("2", "Podcast Queue", "database")

        results = await search_cache("Receipt")
        assert len(results) == 1
        assert results[0]["name"] == "Receipt Tracker"

    @pytest.mark.asyncio
    async def test_finds_by_path_substring(self, mock_cache_paths):
        """Finds pages by path substring."""
        await init_cache()
        await cache_page("1", "Receipts", "database", "FRUGAL/Receipts")
        await cache_page("2", "Podcasts", "database", "WISE/Podcasts")

        results = await search_cache("FRUGAL")
        assert len(results) == 1
        assert results[0]["name"] == "Receipts"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self, mock_cache_paths):
        """Returns empty list when no matches."""
        await init_cache()
        await cache_page("1", "Test", "page")

        results = await search_cache("NonExistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_multiple_matches(self, mock_cache_paths):
        """Returns all matching pages."""
        await init_cache()
        await cache_page("1", "Tech Notes", "page")
        await cache_page("2", "Tech Insights", "page")
        await cache_page("3", "Finance", "page")

        results = await search_cache("Tech")
        assert len(results) == 2
