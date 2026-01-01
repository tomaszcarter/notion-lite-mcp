#!/usr/bin/env python3
"""
Notion Lite MCP Server
Minimal Notion MCP for email processing. ~1.5k tokens instead of ~38k.
"""

import asyncio
import json
from typing import Any, Callable, Coroutine

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

import cache
import markdown
import notion_api

# Constants
SERVER_NAME = "notion-lite"
SERVER_VERSION = "1.0.0"
MAX_SEARCH_RESULTS = 10
DEFAULT_QUERY_LIMIT = 100

server = Server(SERVER_NAME)
_cache_initialized = False


# Tool definitions
TOOLS = [
    types.Tool(
        name="search",
        description="Find pages/databases by name. Checks local cache first.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "type": {"type": "string", "enum": ["page", "database"], "description": "Filter by type"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_page",
        description="Get page content as Markdown.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Page ID (UUID) or cached name (e.g., 'COLLECT')"}
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="create_page",
        description="Create page. Content is basic Markdown: # headings, - lists, **bold**, *italic*, [links](url), > quotes.",
        inputSchema={
            "type": "object",
            "properties": {
                "parent": {"type": "string", "description": "Parent page/database ID or cached name"},
                "title": {"type": "string", "description": "Page title"},
                "content": {"type": "string", "description": "Page content as basic Markdown"},
                "properties": {"type": "object", "description": "Database properties (for database entries)"},
            },
            "required": ["parent", "title"],
        },
    ),
    types.Tool(
        name="update_page",
        description="Update page properties or append content.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Page ID or cached name"},
                "properties": {"type": "object", "description": "Properties to update"},
                "append": {"type": "string", "description": "Markdown content to append"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="delete_page",
        description="Archive page.",
        inputSchema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Page ID or cached name"}},
            "required": ["id"],
        },
    ),
    types.Tool(
        name="query_database",
        description="Query database with filters.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Database ID or cached name"},
                "filter": {"type": "object", "description": "Notion filter object"},
                "limit": {"type": "integer", "description": "Max results (default 100)"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="update_database",
        description="Update database schema.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Database ID or cached name"},
                "title": {"type": "string", "description": "New database title"},
                "properties": {"type": "object", "description": "Properties schema to update"},
            },
            "required": ["id"],
        },
    ),
]


async def _ensure_cache() -> None:
    """Initialize cache on first use."""
    global _cache_initialized
    if not _cache_initialized:
        await cache.init_cache()
        _cache_initialized = True


def _json_response(data: Any) -> list[types.TextContent]:
    """Create a JSON text response."""
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _text_response(text: str) -> list[types.TextContent]:
    """Create a plain text response."""
    return [types.TextContent(type="text", text=text)]


# Tool handlers
async def _handle_search(args: dict[str, Any]) -> list[types.TextContent]:
    """Search for pages/databases."""
    query = args.get("query", "")
    filter_type = args.get("type")

    if not query:
        raise ValueError("query is required")

    # Check cache first
    cached = await cache.search_cache(query)
    if cached:
        if filter_type:
            cached = [r for r in cached if r.get("type") == filter_type]
        if cached:
            return _json_response({
                "source": "cache",
                "results": [
                    {"id": cache.format_id(r["id"]), "name": r["name"], "type": r["type"], "path": r.get("path", "")}
                    for r in cached
                ],
            })

    # Fall back to API
    api_results = await notion_api.search(query, filter_type)
    results = [_format_search_result(item) for item in api_results[:MAX_SEARCH_RESULTS]]
    return _json_response({"source": "api", "results": results})


def _format_search_result(item: dict[str, Any]) -> dict[str, Any]:
    """Format a single search result."""
    item_type = item.get("object", "page")
    if item_type == "page":
        title = markdown.extract_title(item)
    else:
        title_arr = item.get("title", [{}])
        title = title_arr[0].get("plain_text", "Untitled") if title_arr else "Untitled"

    return {"id": item.get("id", ""), "name": title, "type": item_type, "url": item.get("url", "")}


async def _handle_get_page(args: dict[str, Any]) -> list[types.TextContent]:
    """Get page content."""
    page_id = args.get("id", "")
    if not page_id:
        raise ValueError("id is required")

    resolved_id = await cache.resolve_id(page_id)
    page = await notion_api.get_page(resolved_id)
    blocks = await notion_api.get_blocks(resolved_id)

    return _json_response({
        "id": resolved_id,
        "title": markdown.extract_title(page),
        "url": page.get("url", ""),
        "content": markdown.blocks_to_markdown(blocks),
    })


async def _handle_create_page(args: dict[str, Any]) -> list[types.TextContent]:
    """Create a new page."""
    parent = args.get("parent", "")
    title = args.get("title", "")
    content = args.get("content", "")
    properties = args.get("properties")

    if not parent or not title:
        raise ValueError("parent and title are required")

    parent_id = await cache.resolve_id(parent)
    is_database = await _is_database(parent, parent_id)

    children = markdown.markdown_to_blocks(content) if content else None
    db_properties = _build_db_properties(properties, title) if is_database else None

    page = await notion_api.create_page(
        parent_id=parent_id,
        title=title,
        properties=db_properties,
        children=children,
        is_database=is_database,
    )

    await cache.cache_page(page.get("id", ""), title, "page")

    result = {"id": page.get("id", ""), "url": page.get("url", ""), "title": title}
    return _text_response(f"Created page: {title}\n\n" + json.dumps(result, indent=2))


async def _is_database(name: str, resolved_id: str) -> bool:
    """Check if a parent is a database."""
    cached = await cache.get_by_name(name)
    if cached and cached.get("type") == "database":
        return True

    try:
        await notion_api.get_database(resolved_id)
        return True
    except Exception:
        return False


def _build_db_properties(properties: dict[str, Any] | None, title: str) -> dict[str, Any]:
    """Build properties dict for database entry."""
    props = properties or {}
    if "Name" not in props and "title" not in props:
        props["Name"] = {"title": [{"text": {"content": title}}]}
    return props


async def _handle_update_page(args: dict[str, Any]) -> list[types.TextContent]:
    """Update page properties or append content."""
    page_id = args.get("id", "")
    properties = args.get("properties")
    append_content = args.get("append")

    if not page_id:
        raise ValueError("id is required")

    resolved_id = await cache.resolve_id(page_id)

    if properties:
        await notion_api.update_page(resolved_id, properties)

    if append_content:
        blocks = markdown.markdown_to_blocks(append_content)
        await notion_api.append_blocks(resolved_id, blocks)

    return _text_response(f"Updated page {resolved_id}")


async def _handle_delete_page(args: dict[str, Any]) -> list[types.TextContent]:
    """Archive a page."""
    page_id = args.get("id", "")
    if not page_id:
        raise ValueError("id is required")

    resolved_id = await cache.resolve_id(page_id)
    await notion_api.delete_block(resolved_id)
    return _text_response(f"Archived page {resolved_id}")


async def _handle_query_database(args: dict[str, Any]) -> list[types.TextContent]:
    """Query a database."""
    db_id = args.get("id", "")
    filter_obj = args.get("filter")
    limit = args.get("limit", DEFAULT_QUERY_LIMIT)

    if not db_id:
        raise ValueError("id is required")

    resolved_id = await cache.resolve_id(db_id)
    results = await notion_api.query_database(resolved_id, filter_obj, limit=limit)

    formatted = [
        {"id": item.get("id", ""), "url": item.get("url", ""), "properties": _simplify_properties(item.get("properties", {}))}
        for item in results
    ]
    return _json_response({"count": len(formatted), "results": formatted})


async def _handle_update_database(args: dict[str, Any]) -> list[types.TextContent]:
    """Update database schema."""
    db_id = args.get("id", "")
    title = args.get("title")
    properties = args.get("properties")

    if not db_id:
        raise ValueError("id is required")

    resolved_id = await cache.resolve_id(db_id)
    await notion_api.update_database(resolved_id, title, properties)
    return _text_response(f"Updated database {resolved_id}")


# Property simplification
PROPERTY_EXTRACTORS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "title": lambda p: "".join(t.get("plain_text", "") for t in p.get("title", [])),
    "rich_text": lambda p: "".join(t.get("plain_text", "") for t in p.get("rich_text", [])),
    "number": lambda p: p.get("number"),
    "select": lambda p: p.get("select", {}).get("name") if p.get("select") else None,
    "multi_select": lambda p: [s.get("name") for s in p.get("multi_select", [])],
    "date": lambda p: p.get("date", {}).get("start") if p.get("date") else None,
    "checkbox": lambda p: p.get("checkbox"),
    "url": lambda p: p.get("url"),
    "email": lambda p: p.get("email"),
    "phone_number": lambda p: p.get("phone_number"),
    "status": lambda p: p.get("status", {}).get("name") if p.get("status") else None,
}


def _simplify_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Convert Notion properties to simple key-value pairs."""
    result = {}
    for name, prop in properties.items():
        prop_type = prop.get("type", "")
        extractor = PROPERTY_EXTRACTORS.get(prop_type)
        result[name] = extractor(prop) if extractor else f"[{prop_type}]"
    return result


# Tool dispatch
TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Coroutine[Any, Any, list[types.TextContent]]]] = {
    "search": _handle_search,
    "get_page": _handle_get_page,
    "create_page": _handle_create_page,
    "update_page": _handle_update_page,
    "delete_page": _handle_delete_page,
    "query_database": _handle_query_database,
    "update_database": _handle_update_database,
}


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Notion tools."""
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Dispatch tool calls to handlers."""
    await _ensure_cache()

    if not arguments:
        raise ValueError("No arguments provided")

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")

    return await handler(arguments)


async def main():
    """Start the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
