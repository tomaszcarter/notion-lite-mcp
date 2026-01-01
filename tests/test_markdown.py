"""Tests for markdown conversion functions."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from markdown import (
    blocks_to_markdown,
    extract_title,
    markdown_to_blocks,
    parse_rich_text,
    rich_text_to_markdown,
)


class TestParseRichText:
    """Tests for parse_rich_text function."""

    def test_plain_text(self):
        """Plain text returns single text element."""
        result = parse_rich_text("Hello world")
        assert len(result) == 1
        assert result[0]["text"]["content"] == "Hello world"

    def test_empty_string(self):
        """Empty string returns single empty text element."""
        result = parse_rich_text("")
        assert len(result) == 1
        assert result[0]["text"]["content"] == ""

    def test_bold_text(self):
        """Bold text is parsed with bold annotation."""
        result = parse_rich_text("This is **bold** text")
        assert len(result) == 3
        assert result[0]["text"]["content"] == "This is "
        assert result[1]["text"]["content"] == "bold"
        assert result[1]["annotations"]["bold"] is True
        assert result[2]["text"]["content"] == " text"

    def test_italic_text(self):
        """Italic text is parsed with italic annotation."""
        result = parse_rich_text("This is *italic* text")
        assert len(result) == 3
        assert result[1]["text"]["content"] == "italic"
        assert result[1]["annotations"]["italic"] is True

    def test_link(self):
        """Links are parsed with link property."""
        result = parse_rich_text("Click [here](https://example.com) now")
        assert len(result) == 3
        assert result[1]["text"]["content"] == "here"
        assert result[1]["text"]["link"]["url"] == "https://example.com"

    def test_multiple_formatting(self):
        """Multiple formatting elements in one string."""
        result = parse_rich_text("**bold** and *italic*")
        assert len(result) == 3
        assert result[0]["annotations"]["bold"] is True
        assert result[2]["annotations"]["italic"] is True


class TestRichTextToMarkdown:
    """Tests for rich_text_to_markdown function."""

    def test_plain_text(self):
        """Plain text converts correctly."""
        rich_text = [{"text": {"content": "Hello world"}}]
        assert rich_text_to_markdown(rich_text) == "Hello world"

    def test_empty_list(self):
        """Empty list returns empty string."""
        assert rich_text_to_markdown([]) == ""

    def test_bold_text(self):
        """Bold annotation converts to **."""
        rich_text = [{"text": {"content": "bold"}, "annotations": {"bold": True}}]
        assert rich_text_to_markdown(rich_text) == "**bold**"

    def test_italic_text(self):
        """Italic annotation converts to *."""
        rich_text = [{"text": {"content": "italic"}, "annotations": {"italic": True}}]
        assert rich_text_to_markdown(rich_text) == "*italic*"

    def test_link(self):
        """Link converts to markdown link format."""
        rich_text = [{"text": {"content": "click", "link": {"url": "https://x.com"}}}]
        assert rich_text_to_markdown(rich_text) == "[click](https://x.com)"

    def test_combined_formatting(self):
        """Multiple rich text elements combine correctly."""
        rich_text = [
            {"text": {"content": "Hello "}},
            {"text": {"content": "world"}, "annotations": {"bold": True}},
        ]
        assert rich_text_to_markdown(rich_text) == "Hello **world**"


class TestMarkdownToBlocks:
    """Tests for markdown_to_blocks function."""

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert markdown_to_blocks("") == []

    def test_heading_1(self):
        """H1 heading converts to heading_1 block."""
        blocks = markdown_to_blocks("# Title")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "heading_1"
        assert blocks[0]["heading_1"]["rich_text"][0]["text"]["content"] == "Title"

    def test_heading_2(self):
        """H2 heading converts to heading_2 block."""
        blocks = markdown_to_blocks("## Subtitle")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "heading_2"

    def test_heading_3(self):
        """H3 heading converts to heading_3 block."""
        blocks = markdown_to_blocks("### Section")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "heading_3"

    def test_paragraph(self):
        """Plain text converts to paragraph block."""
        blocks = markdown_to_blocks("Just some text")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "paragraph"

    def test_bullet_list(self):
        """Bullet list items convert to bulleted_list_item blocks."""
        blocks = markdown_to_blocks("- Item one\n- Item two")
        assert len(blocks) == 2
        assert blocks[0]["type"] == "bulleted_list_item"
        assert blocks[1]["type"] == "bulleted_list_item"

    def test_numbered_list(self):
        """Numbered list items convert to numbered_list_item blocks."""
        blocks = markdown_to_blocks("1. First\n2. Second")
        assert len(blocks) == 2
        assert blocks[0]["type"] == "numbered_list_item"
        assert blocks[1]["type"] == "numbered_list_item"

    def test_quote(self):
        """Quote converts to quote block."""
        blocks = markdown_to_blocks("> This is quoted")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "quote"

    def test_mixed_content(self):
        """Mixed content converts to correct block types."""
        md = "# Heading\n\nSome text\n\n- Item"
        blocks = markdown_to_blocks(md)
        assert len(blocks) == 3
        assert blocks[0]["type"] == "heading_1"
        assert blocks[1]["type"] == "paragraph"
        assert blocks[2]["type"] == "bulleted_list_item"

    def test_skips_empty_lines(self):
        """Empty lines are skipped."""
        blocks = markdown_to_blocks("Line 1\n\n\n\nLine 2")
        assert len(blocks) == 2


class TestBlocksToMarkdown:
    """Tests for blocks_to_markdown function."""

    def test_empty_list(self):
        """Empty list returns empty string."""
        assert blocks_to_markdown([]) == ""

    def test_heading_1(self):
        """heading_1 block converts to # heading."""
        blocks = [{"type": "heading_1", "heading_1": {"rich_text": [{"text": {"content": "Title"}}]}}]
        assert blocks_to_markdown(blocks) == "# Title"

    def test_heading_2(self):
        """heading_2 block converts to ## heading."""
        blocks = [{"type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Sub"}}]}}]
        assert blocks_to_markdown(blocks) == "## Sub"

    def test_heading_3(self):
        """heading_3 block converts to ### heading."""
        blocks = [{"type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "Sec"}}]}}]
        assert blocks_to_markdown(blocks) == "### Sec"

    def test_paragraph(self):
        """paragraph block converts to plain text."""
        blocks = [{"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Text"}}]}}]
        assert blocks_to_markdown(blocks) == "Text"

    def test_bulleted_list(self):
        """bulleted_list_item converts to - item."""
        blocks = [{"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "Item"}}]}}]
        assert blocks_to_markdown(blocks) == "- Item"

    def test_numbered_list(self):
        """numbered_list_item converts to 1. item."""
        blocks = [{"type": "numbered_list_item", "numbered_list_item": {"rich_text": [{"text": {"content": "Item"}}]}}]
        assert blocks_to_markdown(blocks) == "1. Item"

    def test_quote(self):
        """quote block converts to > quote."""
        blocks = [{"type": "quote", "quote": {"rich_text": [{"text": {"content": "Quoted"}}]}}]
        assert blocks_to_markdown(blocks) == "> Quoted"

    def test_divider(self):
        """divider block converts to ---."""
        blocks = [{"type": "divider"}]
        assert blocks_to_markdown(blocks) == "---"

    def test_unsupported_block(self):
        """Unsupported blocks show placeholder."""
        blocks = [{"type": "callout"}]
        assert blocks_to_markdown(blocks) == "[callout block]"


class TestExtractTitle:
    """Tests for extract_title function."""

    def test_title_property(self):
        """Extracts from 'title' property."""
        page = {"properties": {"title": {"type": "title", "title": [{"plain_text": "My Page"}]}}}
        assert extract_title(page) == "My Page"

    def test_name_property(self):
        """Extracts from 'Name' property (common in databases)."""
        page = {"properties": {"Name": {"type": "title", "title": [{"plain_text": "Entry"}]}}}
        assert extract_title(page) == "Entry"

    def test_empty_title(self):
        """Returns 'Untitled' when no title found."""
        page = {"properties": {}}
        assert extract_title(page) == "Untitled"

    def test_multiple_text_segments(self):
        """Concatenates multiple text segments."""
        page = {
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": "Part "}, {"plain_text": "One"}],
                }
            }
        }
        assert extract_title(page) == "Part One"

    def test_finds_any_title_type(self):
        """Finds title property by type, not name."""
        page = {"properties": {"CustomName": {"type": "title", "title": [{"plain_text": "Found"}]}}}
        assert extract_title(page) == "Found"
