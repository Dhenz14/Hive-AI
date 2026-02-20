# HiveAI Knowledge Refinery — Desktop App

## Architecture

- **Tauri v2 (Rust)** provides the native window and webview
- **Python backend** runs as a subprocess managed by Tauri (`python -m hiveai.app`)
- **Frontend** is the existing Flask UI served at `http://localhost:5000`
- **Settings** are managed via `.env` file or a future settings UI

When the desktop app launches, it:
1. Spawns the Python/Flask backend as a child process
2. Waits for port 5000 to become available (with a 30-second timeout)
3. Opens a native webview window pointing to `http://localhost:5000`
4. On close, kills the Python backend process

## Prerequisites

- **Rust toolchain** — install via [rustup](https://rustup.rs/)
- **Node.js 18+** — required for the Tauri CLI
- **Python 3.11+** with project dependencies installed (`pip install -r requirements.txt`)
- **Database** — SQLite (recommended, no server needed) or PostgreSQL

## Database

For desktop use, SQLite is recommended (no separate database server needed):

```
DATABASE_URL=sqlite:///hiveai.db
```

This stores all data in a single file. PostgreSQL is also supported for production deployments.

## Getting Started

```bash
cd desktop
npm install
npm run dev
```

## Building for Distribution

```bash
cd desktop
npm run build
```

This produces platform-specific installers in `desktop/src-tauri/target/release/bundle/`.

## Standalone Python Bundle (PyInstaller)

As an alternative to the full Tauri desktop app, you can bundle the Python backend
as a standalone executable that doesn't require Python to be installed.

### Building

```bash
cd desktop
chmod +x build.sh
./build.sh
```

### Output

The build creates `desktop/dist/hiveai/` containing:
- `hiveai` executable (or `hiveai.exe` on Windows)
- All Python dependencies bundled
- Flask templates and static files included

### Running

```bash
cd dist/hiveai
export DATABASE_URL=postgresql://user:pass@localhost:5432/hiveai
./hiveai
```

### Limitations

- Embedding models (~1.5 GB) are downloaded on first run, not bundled
- PostgreSQL is still required externally
- Playwright/crawl4ai browser may need separate installation
- Build size is approximately 500 MB+ due to ML dependencies
