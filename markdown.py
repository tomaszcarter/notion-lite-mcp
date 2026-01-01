"""Basic Markdown <-> Notion blocks conversion.

Supports only:
- # ## ### headings
- - bullet lists
- 1. numbered lists
- **bold** and *italic*
- [text](url) links
- > quotes
- Plain paragraphs
"""

import re
from typing import Any, Callable

# Regex patterns
INLINE_PATTERN = re.compile(r"(\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*|\*(.+?)\*)")
NUMBERED_LIST_PATTERN = re.compile(r"^\d+\.\s")

# Common title property names
TITLE_PROPERTY_NAMES = ("title", "Title", "Name", "name")

# Default values
DEFAULT_TITLE = "Untitled"


def _make_text(content: str) -> dict[str, Any]:
    """Create a plain text rich text element."""
    return {"type": "text", "text": {"content": content}}


def _make_link(text: str, url: str) -> dict[str, Any]:
    """Create a link rich text element."""
    return {"type": "text", "text": {"content": text, "link": {"url": url}}}


def _make_bold(content: str) -> dict[str, Any]:
    """Create a bold rich text element."""
    return {"type": "text", "text": {"content": content}, "annotations": {"bold": True}}


def _make_italic(content: str) -> dict[str, Any]:
    """Create an italic rich text element."""
    return {"type": "text", "text": {"content": content}, "annotations": {"italic": True}}


def _make_block(block_type: str, rich_text: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a Notion block of the given type."""
    return {"type": block_type, block_type: {"rich_text": rich_text}}


def parse_rich_text(text: str) -> list[dict[str, Any]]:
    """Parse inline markdown (bold, italic, links) to Notion rich text."""
    rich_text: list[dict[str, Any]] = []
    last_end = 0

    for match in INLINE_PATTERN.finditer(text):
        if match.start() > last_end:
            plain = text[last_end:match.start()]
            if plain:
                rich_text.append(_make_text(plain))

        if match.group(2) and match.group(3):
            rich_text.append(_make_link(match.group(2), match.group(3)))
        elif match.group(4):
            rich_text.append(_make_bold(match.group(4)))
        elif match.group(5):
            rich_text.append(_make_italic(match.group(5)))

        last_end = match.end()

    remaining = text[last_end:]
    if remaining:
        rich_text.append(_make_text(remaining))

    return rich_text if rich_text else [_make_text(text)]


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """Convert basic Markdown to Notion blocks."""
    blocks: list[dict[str, Any]] = []

    for line in markdown.split("\n"):
        if not line.strip():
            continue

        block = _parse_line(line)
        if block:
            blocks.append(block)

    return blocks


def _parse_line(line: str) -> dict[str, Any] | None:
    """Parse a single line of Markdown into a Notion block."""
    if line.startswith("### "):
        return _make_block("heading_3", parse_rich_text(line[4:]))
    if line.startswith("## "):
        return _make_block("heading_2", parse_rich_text(line[3:]))
    if line.startswith("# "):
        return _make_block("heading_1", parse_rich_text(line[2:]))
    if line.startswith("> "):
        return _make_block("quote", parse_rich_text(line[2:]))
    if line.startswith("- "):
        return _make_block("bulleted_list_item", parse_rich_text(line[2:]))
    if NUMBERED_LIST_PATTERN.match(line):
        text = NUMBERED_LIST_PATTERN.sub("", line)
        return _make_block("numbered_list_item", parse_rich_text(text))

    return _make_block("paragraph", parse_rich_text(line))


def rich_text_to_markdown(rich_text: list[dict[str, Any]]) -> str:
    """Convert Notion rich text to Markdown."""
    return "".join(_convert_rich_text_element(rt) for rt in rich_text)


def _convert_rich_text_element(rt: dict[str, Any]) -> str:
    """Convert a single rich text element to Markdown."""
    content = rt.get("text", {}).get("content", "")
    annotations = rt.get("annotations", {})
    link = rt.get("text", {}).get("link")

    if link:
        content = f"[{content}]({link.get('url', '')})"
    if annotations.get("bold"):
        content = f"**{content}**"
    if annotations.get("italic"):
        content = f"*{content}*"

    return content


def blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    """Convert Notion blocks to basic Markdown."""
    lines = [_convert_block(block) for block in blocks]
    return "\n".join(line for line in lines if line is not None)


def _convert_block(block: dict[str, Any]) -> str:
    """Convert a single Notion block to Markdown."""
    block_type = block.get("type", "")
    converters: dict[str, Callable[[dict[str, Any]], str]] = {
        "heading_1": lambda b: f"# {_get_block_text(b, 'heading_1')}",
        "heading_2": lambda b: f"## {_get_block_text(b, 'heading_2')}",
        "heading_3": lambda b: f"### {_get_block_text(b, 'heading_3')}",
        "paragraph": lambda b: _get_block_text(b, "paragraph"),
        "bulleted_list_item": lambda b: f"- {_get_block_text(b, 'bulleted_list_item')}",
        "numbered_list_item": lambda b: f"1. {_get_block_text(b, 'numbered_list_item')}",
        "quote": lambda b: f"> {_get_block_text(b, 'quote')}",
        "divider": lambda b: "---",
        "code": _convert_code_block,
    }

    converter = converters.get(block_type)
    if converter:
        return converter(block)
    return f"[{block_type} block]"


def _get_block_text(block: dict[str, Any], block_type: str) -> str:
    """Extract and convert rich text from a block."""
    return rich_text_to_markdown(block.get(block_type, {}).get("rich_text", []))


def _convert_code_block(block: dict[str, Any]) -> str:
    """Convert a code block to Markdown."""
    code_data = block.get("code", {})
    text = rich_text_to_markdown(code_data.get("rich_text", []))
    lang = code_data.get("language", "")
    return f"```{lang}\n{text}\n```"


def extract_title(page: dict[str, Any]) -> str:
    """Extract page title from Notion page object."""
    properties = page.get("properties", {})

    # Try common title property names first
    for prop_name in TITLE_PROPERTY_NAMES:
        title = _extract_title_from_property(properties.get(prop_name))
        if title:
            return title

    # Fallback: find any title type property
    for prop in properties.values():
        title = _extract_title_from_property(prop)
        if title:
            return title

    return DEFAULT_TITLE


def _extract_title_from_property(prop: dict[str, Any] | None) -> str | None:
    """Extract title text from a property if it's a title type."""
    if not isinstance(prop, dict) or prop.get("type") != "title":
        return None

    title_array = prop.get("title", [])
    if not title_array:
        return None

    return "".join(t.get("plain_text", "") for t in title_array)
