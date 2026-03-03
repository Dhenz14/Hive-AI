# HAF Transfer Indexer (Python)

A production-quality Hive blockchain indexer built on **HAF (Hive Application Framework)** — the official way to build custom blockchain indexers on Hive.

## What is HAF?

HAF is the **official framework** for building Hive blockchain applications that need to index and query blockchain data. It replaces the old approach of streaming blocks from API nodes with a much more powerful PostgreSQL-based architecture.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     PostgreSQL                           │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐ │
│  │   HAF Core Tables    │  │   Your App Tables         │ │
│  │                      │  │                           │ │
│  │  hive.blocks         │  │  my_indexer.transfers     │ │
│  │  hive.operations     │──│  my_indexer.account_stats │ │
│  │  hive.transactions   │  │  my_indexer.indexer_state │ │
│  │  hive.accounts       │  │                           │ │
│  └──────────┬───────────┘  └───────────────────────────┘ │
│             │                          ▲                  │
└─────────────┼──────────────────────────┼─────────────────┘
              │                          │
         hived writes              Your indexer reads
         every block               HAF tables & builds
         into SQL                  application state
```

### Why HAF instead of API streaming?

| Feature | API Streaming | HAF |
|---------|--------------|-----|
| Speed | ~100 blocks/sec | ~10,000+ blocks/sec |
| Reliability | Network-dependent | Local PostgreSQL |
| Fork handling | Manual (complex) | Automatic (built-in) |
| Query flexibility | Limited to API endpoints | Full SQL power |
| Batch processing | One block at a time | Thousands at once |
| Re-processing | Stream from scratch | Just re-read SQL tables |

## How HAF Contexts Work

HAF's most powerful feature is **application contexts**. A context is a named cursor that:

1. **Tracks your progress**: HAF remembers which block your app has processed up to
2. **Handles forks automatically**: When the blockchain reorganizes, HAF rolls back your context to the fork point — your app just re-processes those blocks
3. **Supports multiple apps**: Many independent indexers can run against the same HAF database, each at their own pace

Key HAF functions:
- `hive.app_create_context('name')` — Register your app
- `hive.app_context_attach('name', start_block)` — Start processing
- `hive.app_next_block('name')` — Get the next block to process (returns NULL when caught up)
- `hive.app_context_detach('name')` — Save progress

## Prerequisites

1. **PostgreSQL** (14+) with the HAF extension installed
2. **hived** (Hive node) running with the `sql_serializer` plugin, writing to your PostgreSQL database
3. **Python** (3.10+)

### Setting up HAF

HAF installation is beyond the scope of this template. See:
- [HAF Repository](https://gitlab.syncad.com/hive/haf)
- [HAF Installation Guide](https://gitlab.syncad.com/hive/haf/-/blob/develop/doc/installation.md)
- [Hive Developer Portal](https://developers.hive.io)

The standard HAF database name is `haf_block_log`.

## Quick Start

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure environment
cp .env.example .env
# Edit .env with your HAF PostgreSQL credentials

# 4. Create database schema and register HAF context
python setup.py

# 5. Start indexing (runs continuously)
python indexer.py

# 6. In another terminal, start the API server
python server.py

# 7. Query your indexed data
curl http://localhost:3003/api/status
curl http://localhost:3003/api/transfers/blocktrades
curl http://localhost:3003/api/stats/blocktrades
curl http://localhost:3003/api/top-senders
```

## Project Structure

```
├── .env.example       # Environment configuration template
├── requirements.txt   # Python dependencies
├── setup.py           # Database schema creation and HAF registration
├── indexer.py         # Main indexing loop (reads HAF, builds state)
├── server.py          # Flask REST API server (queries indexed data)
├── test_indexer.py    # Test suite (pytest, unit + integration)
└── README.md          # This file
```

## Schema Design

### transfers table
Stores every `transfer_operation` from the blockchain:

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Auto-incrementing primary key |
| block_num | INTEGER | Block number |
| trx_in_block | SMALLINT | Transaction index within block |
| op_pos | INTEGER | Operation position within transaction |
| timestamp | TIMESTAMP | Block timestamp |
| sender | TEXT | Sending account |
| receiver | TEXT | Receiving account |
| amount | TEXT | Human-readable amount (e.g., "1.000 HIVE") |
| amount_numeric | NUMERIC(20,3) | Numeric amount for aggregation |
| asset | TEXT | Asset symbol: HIVE, HBD |
| memo | TEXT | Transfer memo |

### account_stats table
Pre-computed aggregate statistics per account:

| Column | Type | Description |
|--------|------|-------------|
| account | TEXT | Hive account name (primary key) |
| total_sent | NUMERIC(20,3) | Total HIVE sent |
| total_received | NUMERIC(20,3) | Total HIVE received |
| hbd_sent | NUMERIC(20,3) | Total HBD sent |
| hbd_received | NUMERIC(20,3) | Total HBD received |
| transfer_count | INTEGER | Total number of transfers |
| unique_partners | INTEGER | Unique counterparties |
| first_transfer_at | TIMESTAMP | First transfer timestamp |
| last_transfer_at | TIMESTAMP | Most recent transfer |

## API Endpoints

### GET /api/transfers/<account>
All transfers involving an account.

Query parameters:
- `limit` (default: 50, max: 1000)
- `offset` (default: 0)
- `asset` — Filter: `HIVE` or `HBD`
- `direction` — Filter: `sent`, `received`, or `all`

### GET /api/stats/<account>
Aggregated transfer statistics.

### GET /api/top-senders
Leaderboard of top senders.

Query parameters:
- `limit` (default: 25, max: 100)
- `asset` — Rank by: `HIVE` or `HBD`

### GET /api/block/<num>
All transfers in a specific block.

### GET /api/status
Indexer health and sync status.

## Performance Tips

1. **Batch size matters**: The `BATCH_SIZE` env var controls how many blocks are processed per database transaction. For initial sync, use 5000-10000. For real-time, 100-1000 is fine.

2. **Index your queries**: The setup script creates indexes on sender, receiver, block_num, and timestamp. Add more indexes based on your actual query patterns.

3. **Pre-aggregate**: The `account_stats` table is updated incrementally by the indexer. This makes account lookups O(1) instead of scanning millions of transfer rows.

4. **Separate indexer and API**: Run the indexer and API server as separate processes. This lets you scale API servers independently.

5. **Use gunicorn in production**: Replace `python server.py` with `gunicorn -w 4 -b 0.0.0.0:3003 server:app` for production deployments.

6. **Connection pooling**: For high-traffic APIs, use pgbouncer or psycopg2's `ThreadedConnectionPool` instead of creating connections per-request.

## Extending This Template

To index different operation types (votes, custom_json, etc.):

1. Find the operation type ID in `hive.operation_types`
2. Add the type ID to the indexer's filter query
3. Create new tables for the operation's data
4. Add parsing logic for the operation's JSON body
5. Create API endpoints for querying the new data

## Running Tests

```bash
# All tests
pytest test_indexer.py -v

# Unit tests only (no database required)
pytest test_indexer.py -v -k "not integration"

# Integration tests only
pytest test_indexer.py -v -m integration
```

Tests include:
- **Unit tests**: Amount parsing, operation JSON parsing (always run)
- **Integration tests**: Database connectivity, schema verification, HAF context checks, API endpoint responses (require live database)

## Production Deployment

```bash
# Use gunicorn for the API server
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:3003 server:app

# Use systemd or supervisor for the indexer
# Example systemd service: /etc/systemd/system/haf-indexer.service
```

## License

MIT
