"""HiveAI Agent Tool Registry.

5 MVP tools that give the model Cursor-like capabilities:
- read_file: Read file contents (with optional line range)
- write_file: Create or overwrite a file
- grep: Search file contents with regex
- list_files: List directory contents with optional glob
- bash: Execute shell commands (sandboxed)
"""

import os
import re
import glob as globmod
import subprocess
import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format for system prompt injection)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns the file text with line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "start_line": {"type": "integer", "description": "Optional start line (1-indexed)"},
                "end_line": {"type": "integer", "description": "Optional end line (1-indexed, inclusive)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "grep",
        "description": "Search for a regex pattern in files. Returns matching lines with file paths and line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "File or directory to search in (default: current dir)"},
                "glob": {"type": "string", "description": "File glob filter, e.g. '*.py' (optional)"},
                "max_results": {"type": "integer", "description": "Max matching lines to return (default: 50)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories. Supports glob patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to list (default: current dir)"},
                "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py' (optional)"},
                "max_results": {"type": "integer", "description": "Max entries to return (default: 100)"},
            },
            "required": [],
        },
    },
    {
        "name": "bash",
        "description": "Execute a shell command and return stdout/stderr. Use for git, build tools, tests, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30, max: 120)"},
            },
            "required": ["command"],
        },
    },
]


def get_tool_definitions_text():
    """Return tool definitions formatted for system prompt injection."""
    lines = ["# Available Tools\n"]
    lines.append("You have access to tools. To use a tool, respond with a tool_call block:\n")
    lines.append("<tool_call>")
    lines.append('{"name": "tool_name", "arguments": {"arg1": "value1"}}')
    lines.append("</tool_call>\n")
    lines.append("You may call multiple tools in sequence. After each tool call, you will receive")
    lines.append("a <tool_result> with the output. Use the results to inform your next step.\n")
    lines.append("When you have finished the task, respond normally without any tool_call blocks.\n")

    for tool in TOOL_DEFINITIONS:
        params = tool["parameters"]["properties"]
        required = tool["parameters"].get("required", [])
        param_strs = []
        for pname, pdef in params.items():
            req = " (required)" if pname in required else ""
            param_strs.append(f"  - {pname}: {pdef['description']}{req}")
        lines.append(f"## {tool['name']}")
        lines.append(f"{tool['description']}")
        if param_strs:
            lines.append("Parameters:")
            lines.extend(param_strs)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _resolve_path(path: str, workspace: str) -> str:
    """Resolve a path relative to the workspace, with safety checks."""
    from .safety import validate_path
    if not os.path.isabs(path):
        path = os.path.join(workspace, path)
    path = os.path.normpath(path)
    validate_path(path, workspace)
    return path


def tool_read_file(args: dict, workspace: str) -> dict:
    """Read file contents with optional line range."""
    path = _resolve_path(args["path"], workspace)
    start = args.get("start_line")
    end = args.get("end_line")

    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}

    try:
        size = os.path.getsize(path)
        if size > 1_000_000:  # 1MB limit
            return {"error": f"File too large ({size:,} bytes). Use grep to search or specify line range."}

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if start or end:
            s = max(1, start or 1) - 1
            e = min(len(lines), end or len(lines))
            selected = lines[s:e]
            numbered = [f"{i+s+1:>4} | {line.rstrip()}" for i, line in enumerate(selected)]
        else:
            numbered = [f"{i+1:>4} | {line.rstrip()}" for i, line in enumerate(lines)]

        # Cap output
        if len(numbered) > 500:
            numbered = numbered[:500]
            numbered.append(f"... truncated ({len(lines)} total lines)")

        return {"content": "\n".join(numbered), "lines": len(lines), "path": path}
    except Exception as e:
        return {"error": str(e)}


def tool_write_file(args: dict, workspace: str) -> dict:
    """Write content to a file."""
    path = _resolve_path(args["path"], workspace)
    content = args.get("content", "")

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return {"success": True, "path": path, "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


def tool_grep(args: dict, workspace: str) -> dict:
    """Search for pattern in files."""
    pattern = args["pattern"]
    search_path = _resolve_path(args.get("path", "."), workspace)
    file_glob = args.get("glob", "*")
    max_results = min(args.get("max_results", 50), 200)

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}

    results = []
    files_searched = 0

    if os.path.isfile(search_path):
        files_to_search = [search_path]
    else:
        glob_pattern = os.path.join(search_path, "**", file_glob)
        files_to_search = globmod.glob(glob_pattern, recursive=True)

    for fpath in files_to_search:
        if not os.path.isfile(fpath):
            continue
        files_searched += 1
        if files_searched > 1000:
            break
        try:
            size = os.path.getsize(fpath)
            if size > 1_000_000:
                continue
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if regex.search(line):
                        rel = os.path.relpath(fpath, workspace)
                        results.append(f"{rel}:{i}: {line.rstrip()}")
                        if len(results) >= max_results:
                            break
        except (OSError, UnicodeDecodeError):
            continue
        if len(results) >= max_results:
            break

    return {
        "matches": results,
        "count": len(results),
        "files_searched": files_searched,
        "truncated": len(results) >= max_results,
    }


def tool_list_files(args: dict, workspace: str) -> dict:
    """List files and directories."""
    path = _resolve_path(args.get("path", "."), workspace)
    pattern = args.get("pattern")
    max_results = min(args.get("max_results", 100), 500)

    if pattern:
        glob_pattern = os.path.join(path, pattern)
        entries = globmod.glob(glob_pattern, recursive=True)
        entries = [os.path.relpath(e, workspace) for e in entries[:max_results]]
    else:
        if not os.path.isdir(path):
            return {"error": f"Not a directory: {path}"}
        try:
            raw = os.listdir(path)
            entries = []
            for name in sorted(raw)[:max_results]:
                full = os.path.join(path, name)
                suffix = "/" if os.path.isdir(full) else ""
                entries.append(name + suffix)
        except OSError as e:
            return {"error": str(e)}

    return {"entries": entries, "count": len(entries)}


def tool_bash(args: dict, workspace: str) -> dict:
    """Execute a shell command."""
    from .safety import validate_command

    command = args["command"]
    timeout = min(args.get("timeout", 30), 120)

    validate_command(command)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace,
        )
        stdout = result.stdout[:10_000] if result.stdout else ""
        stderr = result.stderr[:5_000] if result.stderr else ""
        return {
            "stdout": stdout,
            "stderr": stderr,
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "grep": tool_grep,
    "list_files": tool_list_files,
    "bash": tool_bash,
}


def execute_tool(name: str, arguments: dict, workspace: str) -> dict:
    """Execute a tool by name and return the result."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}. Available: {list(TOOL_REGISTRY.keys())}"}

    logger.info("Agent tool call: %s(%s)", name, json.dumps(arguments, default=str)[:200])
    try:
        return TOOL_REGISTRY[name](arguments, workspace)
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return {"error": f"Tool execution failed: {e}"}
