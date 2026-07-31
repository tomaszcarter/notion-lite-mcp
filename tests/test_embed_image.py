"""Tests for the embed_image handler and the file-upload helper.

Covers Issue #194: agents could not embed images into Notion pages — the
wrapper had no file-upload tool, so generated visuals had to be linked or
dragged in by hand. embed_image uploads a local image to Notion (Notion hosts
it — durable, no expiring URL) and appends an image block.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notion_api  # noqa: E402,I001
import server  # noqa: E402,I001


PAGE_ID = "11111111-1111-1111-1111-111111111111"
UPLOAD_ID = "99999999-9999-9999-9999-999999999999"

# Minimal valid 1x1 PNG so mimetypes/guess_type sees a real image extension.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def _patch_cache(monkeypatch):
    """Bypass the cache layer — resolve_id just echoes its input."""

    async def passthrough(value):
        return value

    monkeypatch.setattr(server.cache, "resolve_id", passthrough)


def _write_png(tmp_path, name="diagram.png"):
    path = tmp_path / name
    path.write_bytes(_PNG_BYTES)
    return str(path)


class TestBuildImageBlock:
    def test_block_without_caption(self):
        block = server._build_image_block(UPLOAD_ID, None)
        assert block == {
            "type": "image",
            "image": {"type": "file_upload", "file_upload": {"id": UPLOAD_ID}},
        }

    def test_block_with_caption(self):
        block = server._build_image_block(UPLOAD_ID, "Ad Decimum battle map")
        assert block["image"]["caption"] == [
            {"type": "text", "text": {"content": "Ad Decimum battle map"}}
        ]

    def test_empty_caption_is_omitted(self):
        block = server._build_image_block(UPLOAD_ID, "")
        assert "caption" not in block["image"]


class TestEmbedImageHandler:
    @pytest.mark.asyncio
    async def test_uploads_and_appends_image_block(self, tmp_path):
        path = _write_png(tmp_path)
        upload = AsyncMock(return_value=UPLOAD_ID)
        append = AsyncMock(return_value={})

        with patch.object(notion_api, "upload_file", upload), patch.object(
            notion_api, "append_blocks", append
        ):
            result = await server._handle_embed_image(
                {"page_id": PAGE_ID, "image_path": path, "caption": "cap"}
            )

        # Uploaded with the right filename + content type, and the file bytes.
        upload.assert_awaited_once()
        filename, content_type, data = upload.await_args.args
        assert filename == "diagram.png"
        assert content_type == "image/png"
        assert data == _PNG_BYTES

        # Appended an image block referencing the returned upload id.
        append.assert_awaited_once()
        block_page_id, blocks = append.await_args.args
        assert block_page_id == PAGE_ID
        assert blocks[0]["image"]["file_upload"]["id"] == UPLOAD_ID

        payload = json.loads(result[0].text.split("\n\n", 1)[1])
        assert payload["file_upload_id"] == UPLOAD_ID
        assert payload["filename"] == "diagram.png"

    @pytest.mark.asyncio
    async def test_missing_args_raises(self):
        with pytest.raises(ValueError, match="required"):
            await server._handle_embed_image({"page_id": PAGE_ID})

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            await server._handle_embed_image(
                {"page_id": PAGE_ID, "image_path": str(tmp_path / "nope.png")}
            )

    @pytest.mark.asyncio
    async def test_non_image_file_raises(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("not an image")
        with pytest.raises(ValueError, match="not an image"):
            await server._handle_embed_image(
                {"page_id": PAGE_ID, "image_path": str(path)}
            )

    @pytest.mark.asyncio
    async def test_oversize_image_raises(self, tmp_path):
        path = _write_png(tmp_path)
        with patch.object(
            server.os.path, "getsize", return_value=notion_api.SINGLE_PART_MAX_BYTES + 1
        ), pytest.raises(ValueError, match="single-part upload limit"):
            await server._handle_embed_image({"page_id": PAGE_ID, "image_path": path})


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_create_then_send_returns_id(self):
        client = MagicMock()
        client.file_uploads.create = AsyncMock(return_value={"id": UPLOAD_ID})
        client.file_uploads.send = AsyncMock(return_value={"status": "uploaded"})

        with patch.object(notion_api, "get_client", return_value=client):
            result = await notion_api.upload_file("diagram.png", "image/png", _PNG_BYTES)

        assert result == UPLOAD_ID
        client.file_uploads.create.assert_awaited_once_with(
            mode="single_part", filename="diagram.png", content_type="image/png"
        )
        client.file_uploads.send.assert_awaited_once_with(
            file_upload_id=UPLOAD_ID, file=("diagram.png", _PNG_BYTES, "image/png")
        )


class TestRoleGating:
    def test_embed_image_in_editor_role(self):
        assert "embed_image" in server.ROLE_TOOLS["editor"]

    def test_embed_image_not_in_reader_or_writer(self):
        assert "embed_image" not in server.ROLE_TOOLS["reader"]
        assert "embed_image" not in server.ROLE_TOOLS["writer"]
