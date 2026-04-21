"""Tests for get_page handler and underlying retry/metadata helpers.

Covers the regression from Issue #15: get_page previously returned placeholder
blocks without surfacing parent_id or archived state. Any agent reading a
Notion page to reason about its content was affected.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from notion_client.errors import APIResponseError, RequestTimeoutError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notion_api  # noqa: E402,I001
import server  # noqa: E402,I001


PAGE_ID = "11111111-1111-1111-1111-111111111111"


def _make_page(
    *,
    title: str = "My Page",
    parent_id: str | None = "22222222-2222-2222-2222-222222222222",
    archived: bool = False,
    in_trash: bool = False,
) -> dict:
    parent: dict = {"type": "page_id", "page_id": parent_id} if parent_id else {"type": "workspace"}
    return {
        "id": PAGE_ID,
        "url": f"https://notion.so/{PAGE_ID}",
        "archived": archived,
        "in_trash": in_trash,
        "parent": parent,
        "properties": {
            "title": {
                "type": "title",
                "title": [{"plain_text": title}],
            }
        },
    }


def _paragraph_block(text: str) -> dict:
    return {
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}, "annotations": {}}]},
    }


def _make_api_error(code: str, status: int = 500) -> APIResponseError:
    # APIResponseError's __init__ signature varies across notion-client versions;
    # construct via __new__ and set attributes directly for test isolation.
    err = APIResponseError.__new__(APIResponseError)
    err.code = code
    err.status = status
    err.body = {"code": code, "message": code}
    Exception.__init__(err, code)
    return err


@pytest.fixture(autouse=True)
def _patch_cache(monkeypatch):
    """Bypass the cache layer — resolve_id just echoes its input."""
    async def passthrough(value):
        return value
    monkeypatch.setattr(server.cache, "resolve_id", passthrough)


class TestGetPageLivePage:
    """Live page: returns title, parent_id, and content from blocks."""

    @pytest.mark.asyncio
    async def test_returns_full_metadata_and_content(self):
        page = _make_page(title="My Page")
        blocks = [_paragraph_block("Hello world")]

        with patch.object(notion_api, "get_page", AsyncMock(return_value=page)), \
             patch.object(notion_api, "get_blocks", AsyncMock(return_value=blocks)):
            result = await server._handle_get_page({"id": PAGE_ID})

        payload = json.loads(result[0].text)
        assert payload["id"] == PAGE_ID
        assert payload["title"] == "My Page"
        assert payload["parent_id"] == "22222222-2222-2222-2222-222222222222"
        assert payload["archived"] is False
        assert payload["content"] == "Hello world"
        assert "block_fetch_error" not in payload


class TestGetPageArchived:
    """Archived pages surface an archived flag instead of fake content."""

    @pytest.mark.asyncio
    async def test_archived_flag_set(self):
        page = _make_page(archived=True)
        # get_blocks should NOT be called for archived pages.
        blocks_mock = AsyncMock(side_effect=AssertionError("get_blocks called on archived page"))

        with patch.object(notion_api, "get_page", AsyncMock(return_value=page)), \
             patch.object(notion_api, "get_blocks", blocks_mock):
            result = await server._handle_get_page({"id": PAGE_ID})

        payload = json.loads(result[0].text)
        assert payload["archived"] is True
        assert payload["content"] == ""
        # Metadata should still be populated.
        assert payload["title"] == "My Page"
        assert payload["parent_id"] == "22222222-2222-2222-2222-222222222222"

    @pytest.mark.asyncio
    async def test_in_trash_is_treated_as_archived(self):
        page = _make_page(in_trash=True)
        with patch.object(notion_api, "get_page", AsyncMock(return_value=page)), \
             patch.object(notion_api, "get_blocks", AsyncMock()):
            result = await server._handle_get_page({"id": PAGE_ID})

        payload = json.loads(result[0].text)
        assert payload["archived"] is True


class TestGetPageNotFound:
    """Non-existent IDs surface the error instead of placeholder content."""

    @pytest.mark.asyncio
    async def test_object_not_found_propagates(self):
        err = _make_api_error("object_not_found", status=404)

        with patch.object(notion_api, "get_page", AsyncMock(side_effect=err)), \
             pytest.raises(APIResponseError):
            await server._handle_get_page({"id": PAGE_ID})


class TestGetPageTransientBlockFailure:
    """Transient block-fetch failures retry; permanent ones surface cleanly."""

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        page = _make_page()
        blocks = [_paragraph_block("Recovered")]

        # list() fails twice with a transient error, then succeeds.
        call_count = {"n": 0}

        async def flaky_list(**_kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RequestTimeoutError("timeout")
            return {"results": blocks, "has_more": False}

        mock_client = MagicMock()
        mock_client.blocks.children.list = flaky_list

        with patch.object(notion_api, "get_page", AsyncMock(return_value=page)), \
             patch.object(notion_api, "get_client", return_value=mock_client), \
             patch.object(notion_api.asyncio, "sleep", AsyncMock()):
            result = await server._handle_get_page({"id": PAGE_ID})

        payload = json.loads(result[0].text)
        assert payload["content"] == "Recovered"
        assert call_count["n"] == 3

    @pytest.mark.asyncio
    async def test_permanent_block_error_returns_partial_with_flag(self):
        """When blocks can't be read, metadata is still returned and the error is flagged."""
        page = _make_page()
        err = _make_api_error("validation_error", status=400)

        with patch.object(notion_api, "get_page", AsyncMock(return_value=page)), \
             patch.object(notion_api, "get_blocks", AsyncMock(side_effect=err)):
            result = await server._handle_get_page({"id": PAGE_ID})

        payload = json.loads(result[0].text)
        assert payload["title"] == "My Page"
        assert payload["parent_id"] == "22222222-2222-2222-2222-222222222222"
        assert payload["archived"] is False
        assert payload["content"] == ""
        assert "block_fetch_error" in payload
        assert "validation_error" in payload["block_fetch_error"]


class TestIsTransient:
    """Unit tests for the retry classifier."""

    def test_request_timeout_is_transient(self):
        assert notion_api._is_transient(RequestTimeoutError("x")) is True

    def test_rate_limited_is_transient(self):
        assert notion_api._is_transient(_make_api_error("rate_limited", 429)) is True

    def test_object_not_found_is_not_transient(self):
        assert notion_api._is_transient(_make_api_error("object_not_found", 404)) is False

    def test_validation_error_is_not_transient(self):
        assert notion_api._is_transient(_make_api_error("validation_error", 400)) is False

    def test_generic_exception_is_not_transient(self):
        assert notion_api._is_transient(RuntimeError("boom")) is False


class TestExtractParentId:
    """Unit tests for parent extraction."""

    def test_page_parent(self):
        page = {"parent": {"type": "page_id", "page_id": "abc"}}
        assert notion_api.extract_parent_id(page) == "abc"

    def test_database_parent(self):
        page = {"parent": {"type": "database_id", "database_id": "db1"}}
        assert notion_api.extract_parent_id(page) == "db1"

    def test_workspace_parent_returns_none(self):
        page = {"parent": {"type": "workspace", "workspace": True}}
        assert notion_api.extract_parent_id(page) is None

    def test_missing_parent_returns_none(self):
        assert notion_api.extract_parent_id({}) is None
