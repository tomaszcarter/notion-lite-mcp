"""Tests for notion_api module."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_api import _build_page_params, _make_title_property


class TestMakeTitleProperty:
    """Tests for _make_title_property function."""

    def test_creates_title_structure(self):
        """Creates correct Notion title structure."""
        result = _make_title_property("My Title")
        assert result == {"title": [{"text": {"content": "My Title"}}]}

    def test_handles_empty_string(self):
        """Empty string creates empty content."""
        result = _make_title_property("")
        assert result == {"title": [{"text": {"content": ""}}]}


class TestBuildPageParams:
    """Tests for _build_page_params function."""

    def test_page_parent_uses_page_id(self):
        """Non-database parent uses page_id."""
        parent, props = _build_page_params(
            parent_id="abc123",
            title="Test",
            properties=None,
            is_database=False,
        )
        assert parent == {"page_id": "abc123"}
        assert "title" in props

    def test_database_parent_uses_database_id(self):
        """Database parent uses database_id."""
        parent, props = _build_page_params(
            parent_id="abc123",
            title="Test",
            properties=None,
            is_database=True,
        )
        assert parent == {"database_id": "abc123"}

    def test_database_with_no_properties_adds_default_title(self):
        """When no properties provided, adds default 'Name' title."""
        parent, props = _build_page_params(
            parent_id="abc123",
            title="Test Title",
            properties=None,
            is_database=True,
        )
        assert "Name" in props
        assert props["Name"] == {"title": [{"text": {"content": "Test Title"}}]}

    def test_database_with_properties_uses_them_directly(self):
        """When properties are provided, uses them as-is without adding default."""
        # This is the key fix - properties from _format_properties_for_db
        # already have the correct title property name
        formatted_props = {
            "Receipt ID": {"title": [{"text": {"content": "My Receipt"}}]},
            "Amount": {"number": 42.5},
        }
        parent, props = _build_page_params(
            parent_id="abc123",
            title="Ignored",  # Should be ignored since properties are provided
            properties=formatted_props,
            is_database=True,
        )
        # Should use provided properties as-is
        assert props == formatted_props
        # Should NOT have added a "Name" property
        assert "Name" not in props

    def test_database_with_empty_dict_adds_default_title(self):
        """Empty dict triggers default title addition."""
        # Note: Empty dict {} is falsy in Python (`not {}` is True)
        # So empty dict is treated same as None - add default title
        parent, props = _build_page_params(
            parent_id="abc123",
            title="Test",
            properties={},
            is_database=True,
        )
        # Empty dict means no properties provided, should add default title
        assert "Name" in props
        assert props["Name"] == {"title": [{"text": {"content": "Test"}}]}

    def test_page_ignores_properties_param(self):
        """Page creation ignores properties param."""
        parent, props = _build_page_params(
            parent_id="abc123",
            title="Test",
            properties={"ignored": "value"},
            is_database=False,
        )
        # Page always uses fixed title structure
        assert props == {"title": {"title": [{"text": {"content": "Test"}}]}}
        assert "ignored" not in props
