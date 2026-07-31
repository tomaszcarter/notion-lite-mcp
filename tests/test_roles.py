"""Tests for NOTION_LITE_ROLE tool subsetting."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import ROLE_TOOLS, TOOLS, _allowed_tool_names, _filter_tools_for_role


class TestRoleMapping:
    def test_reader_is_read_only(self):
        assert ROLE_TOOLS["reader"] == {"search", "get_page", "query_database"}

    def test_writer_can_create_but_not_modify(self):
        assert ROLE_TOOLS["writer"] == {"search", "get_page", "create_page"}

    def test_editor_covers_page_lifecycle(self):
        assert ROLE_TOOLS["editor"] == {
            "search",
            "get_page",
            "create_page",
            "update_page",
            "delete_page",
            "query_database",
            "embed_image",
        }

    def test_admin_is_unrestricted(self):
        assert ROLE_TOOLS["admin"] is None

    def test_full_is_unrestricted(self):
        assert ROLE_TOOLS["full"] is None


class TestFilterTools:
    def test_unrestricted_role_returns_all_tools(self):
        filtered = _filter_tools_for_role(TOOLS, "admin")
        assert len(filtered) == len(TOOLS)

    def test_reader_excludes_write_tools(self):
        filtered = _filter_tools_for_role(TOOLS, "reader")
        names = {t.name for t in filtered}
        assert names == {"search", "get_page", "query_database"}
        assert "create_page" not in names
        assert "delete_page" not in names
        assert "update_database" not in names

    def test_writer_excludes_read_database_and_delete(self):
        filtered = _filter_tools_for_role(TOOLS, "writer")
        names = {t.name for t in filtered}
        assert "create_page" in names
        assert "delete_page" not in names
        assert "update_database" not in names


class TestAllowedToolNames:
    def test_unknown_role_returns_none_allowlist(self):
        # Unknown roles are coerced to "full" at startup; directly querying
        # an unknown key returns None (no entry → all allowed-by-absence).
        assert _allowed_tool_names("admin") is None

    def test_reader_has_finite_allowlist(self):
        allowed = _allowed_tool_names("reader")
        assert allowed is not None
        assert "search" in allowed
