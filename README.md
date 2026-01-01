# Notion Lite MCP

Minimal Notion MCP for email processing. ~1.5k tokens instead of ~38k.

## Why?

The official Notion MCP at `mcp.notion.com` uses ~38k tokens of context just for tool definitions. Most of that is the Notion-flavored Markdown specification embedded in tool descriptions.

For email processing, we only need basic operations with simple Markdown. This MCP does that in ~1.5k tokens.

## Tools

### 1. search
```
Find pages/databases by name. Checks local cache first.
Params: query (string), type (optional: "page"|"database")
```

### 2. get_page
```
Get page content as Markdown.
Params: id (string - UUID or cached name like "COLLECT")
```

### 3. create_page
```
Create page. Content is basic Markdown: # headings, - lists, **bold**, *italic*, [links](url), > quotes.
Params: parent (string), title (string), content (string), properties (object, for database entries)
```

### 4. update_page
```
Update page properties or append content.
Params: id (string), properties (object), append (string - markdown to add)
```

### 5. delete_page
```
Archive page.
Params: id (string)
```

### 6. move_page
```
Move page to new parent.
Params: id (string), parent (string)
```

### 7. query_database
```
Query database with filters.
Params: id (string), filter (object), limit (int, default 100)
```

### 8. update_database
```
Update database schema.
Params: id (string), title (string), properties (object)
```

## Cache

SQLite at `~/.notion-lite/cache.db` for fast lookups of known pages:

```sql
CREATE TABLE pages (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    path TEXT
);
```

Pre-seed with your commonly-used pages so you can reference them by name instead of UUID.

## Markdown Support

Only:
- `# ## ###` headings
- `- ` bullet lists
- `1. ` numbered lists
- `**bold**` and `*italic*`
- `[text](url)` links
- `> ` quotes
- Plain paragraphs

That's it. No tables, callouts, toggles, colors, or anything fancy.

## API Endpoints Used

- `POST /v1/search`
- `GET /v1/pages/{id}`
- `POST /v1/pages`
- `PATCH /v1/pages/{id}`
- `GET /v1/blocks/{id}/children`
- `PATCH /v1/blocks/{id}/children`
- `DELETE /v1/blocks/{id}`
- `POST /v1/databases/{id}/query`
- `PATCH /v1/databases/{id}`

Ref: https://developers.notion.com/reference

## Project Structure

```
notion-lite/
├── server.py           # Entry point, tool handlers
├── cache.py            # SQLite cache
├── notion_client.py    # API calls
├── markdown.py         # Basic MD <-> blocks
├── config.yaml         # Cache seed
└── requirements.txt    # mcp, notion-client, aiosqlite
```

## Config

```yaml
# config.yaml
cache_seed:
  - name: COLLECT
    id: 28e0b827f2338013846de7a6257a4480
  - name: Receipt Tracker
    id: 8b431394-c095-4259-95c5-fc1a127a873a
  # add your commonly-used pages here
```

## Installation

```bash
cd ~/.claude-mcps/notion-lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your page IDs
export NOTION_API_KEY=secret_xxx
```

## Claude Code Integration

```json
{
  "mcpServers": {
    "notion-lite": {
      "command": "~/.claude-mcps/notion-lite/venv/bin/python",
      "args": ["~/.claude-mcps/notion-lite/server.py"],
      "env": { "NOTION_API_KEY": "secret_xxx" }
    }
  }
}
```

## Usage Examples

```python
# Create an insight page
create_page(
    parent="COLLECT",
    title="AI Trends Q1 2025",
    content="## Summary\n- Point one\n- Point two"
)

# Create a receipt entry (database row)
create_page(
    parent="Receipt Tracker",
    properties={
        "Vendor": "Stripe",
        "Amount": 9.99,
        "date:Date:start": "2025-01-01"
    }
)

# Move a page
move_page(id="abc123", parent="TECH")

# Search
search(query="AI Trends", type="page")
```

## What's Missing (Intentionally)

- create_database
- comments
- users/teams
- duplicate_page
- rich formatting (callouts, toggles, colors, tables, columns, synced blocks, equations, embeds)

Add them when you need them. You probably won't.

## License

MIT
