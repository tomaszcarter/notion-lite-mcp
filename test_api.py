#!/usr/bin/env python3
"""Quick API integration test."""

import asyncio
import os
from pathlib import Path

# Load .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key] = value

import notion_api as nc


async def test_search():
    """Test search API."""
    print("Testing search('COLLECT')...")
    results = await nc.search("COLLECT")
    print(f"  Found {len(results)} results")
    for r in results[:3]:
        obj_type = r.get("object")
        page_id = r.get("id")
        print(f"  - {obj_type}: {page_id[:12]}...")
    return len(results) > 0


async def test_get_page():
    """Test get_page API."""
    # Use COLLECT page ID from config
    page_id = "28e0b827-f233-8013-846d-e7a6257a4480"
    print(f"\nTesting get_page({page_id[:12]}...)...")
    try:
        page = await nc.get_page(page_id)
        print(f"  Got page: {page.get('object')}")
        print(f"  URL: {page.get('url', 'N/A')}")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


async def test_get_blocks():
    """Test get_blocks API."""
    page_id = "28e0b827-f233-8013-846d-e7a6257a4480"
    print(f"\nTesting get_blocks({page_id[:12]}...)...")
    try:
        blocks = await nc.get_blocks(page_id)
        print(f"  Found {len(blocks)} blocks")
        for b in blocks[:3]:
            print(f"  - {b.get('type')}")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


async def main():
    print("=" * 50)
    print("Notion Lite API Integration Tests")
    print("=" * 50)

    results = []
    results.append(("search", await test_search()))
    results.append(("get_page", await test_get_page()))
    results.append(("get_blocks", await test_get_blocks()))

    print("\n" + "=" * 50)
    print("Results:")
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print("=" * 50)
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
