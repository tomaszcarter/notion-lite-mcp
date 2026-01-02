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

    # Detect if parent_id is a data_source_id vs database_id
    is_data_source = await _is_data_source_id(parent_id) if is_database else False

    parent, page_properties = _build_page_params(
        parent_id, title, properties, is_database, is_data_source
    )

    params: dict[str, Any] = {"parent": parent, "properties": page_properties}
    if children:
        params["children"] = children

    return await client.pages.create(**params)


async def _is_data_source_id(id: str) -> bool:
    """Check if an ID is a data_source_id (vs database_id)."""
    client = get_client()
    try:
        await client.data_sources.retrieve(data_source_id=id)
        return True
    except Exception:
        return False


def _build_page_params(
    parent_id: str,
    title: str,
    properties: dict[str, Any] | None,
    is_database: bool,
    is_data_source: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build parent and properties params for page creation.

    Args:
        parent_id: The ID of the parent page/database/data_source
        title: Title for the new page
        properties: Pre-formatted properties (for database entries)
        is_database: True if creating in a database
        is_data_source: True if parent_id is a data_source_id (vs database_id)
    """
    if is_database:
        # Use correct parent key based on ID type
        if is_data_source:
            parent = {"data_source_id": parent_id}
        else:
            parent = {"database_id": parent_id}
        # When properties are provided, assume caller has set up title correctly
        # (server.py uses _format_properties_for_db which handles title)
        page_properties = properties or {}
        if not properties:
            # Only add default title if no properties were provided
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

    # Resolve to data_source_id if needed
    data_source_id = await _resolve_data_source_id(database_id)

    results: list[dict[str, Any]] = []
    cursor = None

    while len(results) < limit:
        params = _build_query_params(filter_obj, sorts, cursor)
        response = await client.data_sources.query(data_source_id=data_source_id, **params)
        results.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return results[:limit]


async def _resolve_data_source_id(database_id: str) -> str:
    """Resolve a database_id to its data_source_id."""
    client = get_client()

    # First try as data_source_id directly
    try:
        await client.data_sources.retrieve(data_source_id=database_id)
        return database_id
    except Exception:
        pass

    # It's a database_id, get the data_source from it
    db = await client.databases.retrieve(database_id=database_id)
    data_sources = db.get("data_sources", [])
    if data_sources:
        return data_sources[0].get("id")

    raise ValueError(f"No data source found for database {database_id}")


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
    """Get database metadata and schema.

    Handles the Notion API's database/data_source distinction:
    - database_id: The container (from URL)
    - data_source_id: Where properties/data live
    """
    client = get_client()

    # First try as data_source_id (for backwards compatibility with cached IDs)
    try:
        return await client.data_sources.retrieve(data_source_id=database_id)
    except Exception:
        pass

    # Try as database_id, then get the data_source
    db = await client.databases.retrieve(database_id=database_id)
    data_sources = db.get("data_sources", [])
    if not data_sources:
        return db  # Return database info even without data sources

    # Get the first data source for schema/properties
    data_source_id = data_sources[0].get("id")
    return await client.data_sources.retrieve(data_source_id=data_source_id)


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
