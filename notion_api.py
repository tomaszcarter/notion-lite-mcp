"""Notion API client wrapper."""

import os
from typing import Any

from notion_client import AsyncClient

# Constants
ENV_API_KEY = "NOTION_API_KEY"
DEFAULT_TITLE_PROPERTY = "Name"

_client: AsyncClient | None = None


def get_client() -> AsyncClient:
    """Get or create Notion async client."""
    global _client
    if _client is None:
        api_key = os.environ.get(ENV_API_KEY)
        if not api_key:
            raise ValueError(f"{ENV_API_KEY} environment variable not set")
        _client = AsyncClient(auth=api_key)
    return _client


async def search(query: str, filter_type: str | None = None) -> list[dict[str, Any]]:
    """Search Notion for pages/databases."""
    client = get_client()

    params: dict[str, Any] = {"query": query}
    if filter_type == "page":
        params["filter"] = {"property": "object", "value": "page"}
    elif filter_type == "database":
        # API now uses "data_source" instead of "database"
        params["filter"] = {"property": "object", "value": "data_source"}

    response = await client.search(**params)
    return response.get("results", [])


async def get_page(page_id: str) -> dict[str, Any]:
    """Get page metadata."""
    client = get_client()
    return await client.pages.retrieve(page_id=page_id)


async def get_blocks(block_id: str) -> list[dict[str, Any]]:
    """Get all child blocks of a page/block with pagination."""
    client = get_client()
    return await _paginate(
        lambda cursor: client.blocks.children.list(
            block_id=block_id,
            **({"start_cursor": cursor} if cursor else {}),
        )
    )


async def _paginate(fetch_page) -> list[dict[str, Any]]:
    """Generic pagination helper."""
    results: list[dict[str, Any]] = []
    cursor = None

    while True:
        response = await fetch_page(cursor)
        results.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return results


async def create_page(
    parent_id: str,
    title: str,
    properties: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
    is_database: bool = False,
) -> dict[str, Any]:
    """Create a new page under a page or database."""
    client = get_client()

    parent, page_properties = _build_page_params(parent_id, title, properties, is_database)

    params: dict[str, Any] = {"parent": parent, "properties": page_properties}
    if children:
        params["children"] = children

    return await client.pages.create(**params)


def _build_page_params(
    parent_id: str,
    title: str,
    properties: dict[str, Any] | None,
    is_database: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build parent and properties params for page creation."""
    if is_database:
        parent = {"database_id": parent_id}
        page_properties = properties or {}
        if "title" not in page_properties and DEFAULT_TITLE_PROPERTY not in page_properties:
            page_properties[DEFAULT_TITLE_PROPERTY] = _make_title_property(title)
    else:
        parent = {"page_id": parent_id}
        page_properties = {"title": _make_title_property(title)}

    return parent, page_properties


def _make_title_property(title: str) -> dict[str, Any]:
    """Create a title property value."""
    return {"title": [{"text": {"content": title}}]}


async def update_page(
    page_id: str, properties: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Update page properties."""
    client = get_client()
    params: dict[str, Any] = {"page_id": page_id}
    if properties:
        params["properties"] = properties
    return await client.pages.update(**params)


async def append_blocks(block_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    """Append blocks to a page/block."""
    client = get_client()
    return await client.blocks.children.append(block_id=block_id, children=children)


async def delete_block(block_id: str) -> dict[str, Any]:
    """Archive/delete a block (or page)."""
    client = get_client()
    return await client.blocks.delete(block_id=block_id)


async def query_database(
    database_id: str,
    filter_obj: dict[str, Any] | None = None,
    sorts: list[dict[str, Any]] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query a database with optional filter and sort."""
    client = get_client()
    results: list[dict[str, Any]] = []
    cursor = None

    while len(results) < limit:
        params = _build_query_params(filter_obj, sorts, cursor)
        # Notion API now uses data_sources endpoint for database queries
        response = await client.data_sources.query(data_source_id=database_id, **params)
        results.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return results[:limit]


def _build_query_params(
    filter_obj: dict[str, Any] | None,
    sorts: list[dict[str, Any]] | None,
    cursor: str | None,
) -> dict[str, Any]:
    """Build query parameters for database query."""
    params: dict[str, Any] = {}
    if filter_obj:
        params["filter"] = filter_obj
    if sorts:
        params["sorts"] = sorts
    if cursor:
        params["start_cursor"] = cursor
    return params


async def get_database(database_id: str) -> dict[str, Any]:
    """Get database metadata and schema."""
    client = get_client()
    # Notion API now uses data_sources endpoint
    return await client.data_sources.retrieve(data_source_id=database_id)


async def update_database(
    database_id: str,
    title: str | None = None,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update database title or properties schema."""
    client = get_client()

    params: dict[str, Any] = {}
    if title:
        params["title"] = [{"text": {"content": title}}]
    if properties:
        params["properties"] = properties

    # Notion API now uses data_sources endpoint
    return await client.data_sources.update(data_source_id=database_id, **params)
