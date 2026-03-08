#!/usr/bin/env python3
"""
MCP Server for Knowledge Harvester — exposes harvested content as tools
callable by AI coding agents via Model Context Protocol.

Implements a simple JSON-RPC 2.0 HTTP server compatible with MCP.

Usage:
    python scripts/knowledge_harvester.py --mcp
    python scripts/knowledge_harvester_mcp.py  # standalone
"""

import json
import logging
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from knowledge_harvester import (
    DOC_SOURCES, _fetch_page, _extract_examples, _check_robots, USER_AGENT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MCP] %(message)s")
log = logging.getLogger("mcp")

MCP_PORT = 8779
SERVER_INFO = {
    "name": "hiveai-knowledge-harvester",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "harvest_docs",
        "description": "Fetch a documentation URL and extract structured code examples with explanations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": list(DOC_SOURCES.keys()),
                             "description": "Programming language (rust, go, cpp, hive)"},
                "url": {"type": "string", "description": "URL to scrape. If omitted, uses the default base URL for the language."},
            },
            "required": ["language"],
        },
    },
    {
        "name": "list_sources",
        "description": "List all configured documentation sources with their base URLs and selectors.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _handle_harvest_docs(args: dict) -> dict:
    """Execute harvest_docs tool."""
    lang = args.get("language", "")
    if lang not in DOC_SOURCES:
        return {"error": f"Unknown language: {lang}. Available: {list(DOC_SOURCES.keys())}"}

    cfg = DOC_SOURCES[lang]
    url = args.get("url") or cfg["base_url"]

    rp = _check_robots(url)
    if not rp.can_fetch(USER_AGENT, url):
        return {"error": f"robots.txt disallows scraping {url}"}

    soup = _fetch_page(url)
    if soup is None:
        return {"error": f"Failed to fetch {url}"}

    examples = _extract_examples(soup, url, cfg, lang)
    results = []
    for ex in examples:
        results.append({
            "heading": ex.heading,
            "code": ex.code,
            "explanation": ex.explanation,
            "language": ex.language,
            "url": ex.url,
        })

    return {"language": cfg["lang_name"], "url": url, "examples": results, "count": len(results)}


def _handle_list_sources(_args: dict) -> dict:
    """Execute list_sources tool."""
    sources = []
    for key, cfg in DOC_SOURCES.items():
        sources.append({
            "id": key,
            "name": cfg["lang_name"],
            "base_url": cfg["base_url"],
            "code_selector": cfg.get("code_selector", "pre"),
        })
    return {"sources": sources}


TOOL_HANDLERS = {
    "harvest_docs": _handle_harvest_docs,
    "list_sources": _handle_list_sources,
}


def _jsonrpc_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MCPHandler(BaseHTTPRequestHandler):
    """Handle MCP JSON-RPC requests."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(_jsonrpc_error(None, -32700, "Parse error"), 400)
            return

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            self._send_json(_jsonrpc_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }))
        elif method == "tools/list":
            self._send_json(_jsonrpc_response(req_id, {"tools": TOOLS}))
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            handler = TOOL_HANDLERS.get(tool_name)
            if not handler:
                self._send_json(_jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}"))
                return
            try:
                result = handler(tool_args)
                content = [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]
                self._send_json(_jsonrpc_response(req_id, {"content": content}))
            except Exception as e:
                self._send_json(_jsonrpc_error(req_id, -32000, str(e)))
        else:
            self._send_json(_jsonrpc_error(req_id, -32601, f"Unknown method: {method}"))

    def _send_json(self, data: dict, status: int = 200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        log.info(fmt, *args)


def start_mcp_server(port: int = MCP_PORT):
    """Start the MCP HTTP server."""
    server = HTTPServer(("127.0.0.1", port), MCPHandler)
    log.info("MCP server listening on http://127.0.0.1:%d", port)
    log.info("Tools: %s", [t["name"] for t in TOOLS])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down MCP server")
        server.server_close()


if __name__ == "__main__":
    start_mcp_server()
