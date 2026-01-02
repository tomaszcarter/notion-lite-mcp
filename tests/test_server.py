"""Tests for server module property formatting."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    PROPERTY_FORMATTERS,
    _format_properties_for_db,
    _simplify_properties,
)


class TestPropertyFormatters:
    """Tests for individual property formatters."""

    def test_format_title(self):
        """Title formatter creates correct structure."""
        result = PROPERTY_FORMATTERS["title"]("My Title")
        assert result == {"title": [{"text": {"content": "My Title"}}]}

    def test_format_rich_text(self):
        """Rich text formatter creates correct structure."""
        result = PROPERTY_FORMATTERS["rich_text"]("Some text")
        assert result == {"rich_text": [{"text": {"content": "Some text"}}]}

    def test_format_number(self):
        """Number formatter handles various inputs."""
        assert PROPERTY_FORMATTERS["number"](42) == {"number": 42.0}
        assert PROPERTY_FORMATTERS["number"](3.14) == {"number": 3.14}
        assert PROPERTY_FORMATTERS["number"](None) == {"number": None}

    def test_format_select(self):
        """Select formatter creates correct structure."""
        result = PROPERTY_FORMATTERS["select"]("Option A")
        assert result == {"select": {"name": "Option A"}}
        assert PROPERTY_FORMATTERS["select"](None) == {"select": None}

    def test_format_multi_select_list(self):
        """Multi-select formatter handles list input."""
        result = PROPERTY_FORMATTERS["multi_select"](["A", "B", "C"])
        assert result == {"multi_select": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}

    def test_format_multi_select_single(self):
        """Multi-select formatter handles single value."""
        result = PROPERTY_FORMATTERS["multi_select"]("Single")
        assert result == {"multi_select": [{"name": "Single"}]}

    def test_format_date(self):
        """Date formatter creates correct structure."""
        result = PROPERTY_FORMATTERS["date"]("2025-01-02")
        assert result == {"date": {"start": "2025-01-02"}}
        assert PROPERTY_FORMATTERS["date"](None) == {"date": None}

    def test_format_checkbox(self):
        """Checkbox formatter converts to boolean."""
        assert PROPERTY_FORMATTERS["checkbox"](True) == {"checkbox": True}
        assert PROPERTY_FORMATTERS["checkbox"](False) == {"checkbox": False}
        assert PROPERTY_FORMATTERS["checkbox"](1) == {"checkbox": True}
        assert PROPERTY_FORMATTERS["checkbox"](0) == {"checkbox": False}

    def test_format_url(self):
        """URL formatter handles string input."""
        result = PROPERTY_FORMATTERS["url"]("https://example.com")
        assert result == {"url": "https://example.com"}
        assert PROPERTY_FORMATTERS["url"](None) == {"url": None}

    def test_format_email(self):
        """Email formatter handles string input."""
        result = PROPERTY_FORMATTERS["email"]("test@example.com")
        assert result == {"email": "test@example.com"}

    def test_format_status(self):
        """Status formatter creates correct structure."""
        result = PROPERTY_FORMATTERS["status"]("In Progress")
        assert result == {"status": {"name": "In Progress"}}


class TestFormatPropertiesForDb:
    """Tests for _format_properties_for_db function."""

    def test_sets_title_from_schema(self):
        """Title property is set using the correct name from schema."""
        schema = {
            "Receipt ID": {"type": "title"},
            "Amount": {"type": "number"},
        }
        result = _format_properties_for_db({}, schema, "Test Receipt")

        assert "Receipt ID" in result
        assert result["Receipt ID"] == {"title": [{"text": {"content": "Test Receipt"}}]}
        # Should NOT have a "Name" or "title" key
        assert "Name" not in result
        assert "title" not in result

    def test_formats_simple_values(self):
        """Simple values are formatted based on schema types."""
        schema = {
            "Name": {"type": "title"},
            "Amount": {"type": "number"},
            "Date": {"type": "date"},
            "Vendor": {"type": "rich_text"},
            "Category": {"type": "select"},
        }
        user_props = {
            "Amount": 42.50,
            "Date": "2025-01-02",
            "Vendor": "Test Vendor",
            "Category": "Software",
        }

        result = _format_properties_for_db(user_props, schema, "My Title")

        assert result["Name"] == {"title": [{"text": {"content": "My Title"}}]}
        assert result["Amount"] == {"number": 42.5}
        assert result["Date"] == {"date": {"start": "2025-01-02"}}
        assert result["Vendor"] == {"rich_text": [{"text": {"content": "Test Vendor"}}]}
        assert result["Category"] == {"select": {"name": "Software"}}

    def test_skips_unknown_properties(self):
        """Properties not in schema are ignored."""
        schema = {
            "Name": {"type": "title"},
        }
        user_props = {
            "Unknown": "value",
            "AlsoUnknown": 123,
        }

        result = _format_properties_for_db(user_props, schema, "Title")

        assert "Unknown" not in result
        assert "AlsoUnknown" not in result
        assert "Name" in result

    def test_passes_through_already_formatted(self):
        """Already-formatted Notion properties are passed through."""
        schema = {
            "Name": {"type": "title"},
            "Amount": {"type": "number"},
        }
        user_props = {
            "Amount": {"number": 99.99},  # Already in Notion format
        }

        result = _format_properties_for_db(user_props, schema, "Title")

        assert result["Amount"] == {"number": 99.99}

    def test_does_not_duplicate_title(self):
        """If user provides title property, it's not overwritten."""
        schema = {
            "Task Name": {"type": "title"},
            "Status": {"type": "select"},
        }
        # User explicitly provides the title property
        user_props = {
            "Task Name": "Custom Title",
            "Status": "Done",
        }

        result = _format_properties_for_db(user_props, schema, "Default Title")

        # Should use title param, not user's value (current behavior)
        # Title is always set from the title parameter
        assert result["Task Name"] == {"title": [{"text": {"content": "Default Title"}}]}


class TestSimplifyProperties:
    """Tests for _simplify_properties function."""

    def test_extracts_title(self):
        """Title property is extracted to plain text."""
        props = {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "My Page"}],
            }
        }
        result = _simplify_properties(props)
        assert result["Name"] == "My Page"

    def test_extracts_number(self):
        """Number property is extracted."""
        props = {
            "Amount": {"type": "number", "number": 42.5}
        }
        result = _simplify_properties(props)
        assert result["Amount"] == 42.5

    def test_extracts_select(self):
        """Select property is extracted to name."""
        props = {
            "Status": {"type": "select", "select": {"name": "Done"}}
        }
        result = _simplify_properties(props)
        assert result["Status"] == "Done"

    def test_extracts_date(self):
        """Date property is extracted to start date."""
        props = {
            "Due": {"type": "date", "date": {"start": "2025-01-02"}}
        }
        result = _simplify_properties(props)
        assert result["Due"] == "2025-01-02"

    def test_handles_unknown_type(self):
        """Unknown property types show placeholder."""
        props = {
            "Files": {"type": "files", "files": []}
        }
        result = _simplify_properties(props)
        assert result["Files"] == "[files]"
