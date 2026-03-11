"""HiveAI Agent Safety Layer.

Path restrictions and command validation to prevent the agent from
doing anything dangerous. Defense in depth — even if the model tries
something sketchy, execution gets blocked here.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

# Directories the agent is NEVER allowed to touch
BLOCKED_PATHS = [
    # System directories
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/proc", "/sys",
    # Sensitive user dirs
    ".ssh", ".gnupg", ".aws", ".azure",
]

# File patterns that should never be read or written
BLOCKED_PATTERNS = [
    r"\.env$",
    r"\.env\.",
    r"credentials\.json$",
    r"secrets\.ya?ml$",
    r"id_rsa",
    r"id_ed25519",
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"password",
    r"token\.json$",
]


def validate_path(path: str, workspace: str) -> None:
    """Validate that a path is safe to access.

    Raises ValueError if the path is blocked.
    """
    norm = os.path.normpath(os.path.abspath(path))
    norm_lower = norm.lower().replace("\\", "/")
    workspace_norm = os.path.normpath(os.path.abspath(workspace)).lower().replace("\\", "/")

    # Must be within workspace or common safe locations
    safe_roots = [
        workspace_norm,
        os.path.expanduser("~").lower().replace("\\", "/"),
    ]

    in_safe_root = any(norm_lower.startswith(root) for root in safe_roots)
    if not in_safe_root:
        raise ValueError(f"Path outside workspace: {path}")

    # Check blocked directories
    for blocked in BLOCKED_PATHS:
        blocked_norm = blocked.lower().replace("\\", "/")
        if blocked_norm in norm_lower:
            raise ValueError(f"Access to {blocked} is blocked")

    # Check blocked file patterns
    basename = os.path.basename(norm)
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, basename, re.IGNORECASE):
            raise ValueError(f"Access to sensitive file blocked: {basename}")


# ---------------------------------------------------------------------------
# Command safety
# ---------------------------------------------------------------------------

# Commands that are completely blocked
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){",              # fork bomb
    "chmod 777",
    "curl.*| bash",
    "wget.*| bash",
    "curl.*| sh",
    "wget.*| sh",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "format ",
    "diskpart",
    "del /f /s /q",
    "> /dev/sda",
    "net user",
    "net localgroup",
    "reg delete",
    "reg add",
]

# Commands that are allowed (whitelist approach for extra safety)
# If a command starts with any of these, it's allowed
ALLOWED_PREFIXES = [
    "ls", "dir", "cat", "head", "tail", "wc",
    "find", "grep", "rg", "ag", "ack",
    "git ", "git\t",
    "python", "python3", "pip",
    "node", "npm", "npx", "yarn", "bun",
    "cargo", "rustc",
    "go ", "go\t",
    "g++", "gcc", "clang", "make", "cmake",
    "echo", "printf", "date", "whoami", "pwd",
    "touch", "mkdir", "cp", "mv",
    "diff", "sort", "uniq", "cut", "tr",
    "jq", "sed", "awk",
    "curl", "wget",  # allowed standalone, blocked when piped to shell
    "docker", "docker-compose",
    "pytest", "jest", "mocha",
    "file", "stat", "du", "df",
    "env", "printenv", "which", "type",
    "cd ", "pushd", "popd",
]


def validate_command(command: str) -> None:
    """Validate that a shell command is safe to execute.

    Raises ValueError if the command is blocked.
    """
    cmd_lower = command.strip().lower()

    # Check explicit blocklist
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            raise ValueError(f"Blocked command pattern: {blocked}")

    # Check for pipe-to-shell patterns
    if re.search(r"\|\s*(ba)?sh\b", cmd_lower):
        raise ValueError("Piping to shell is blocked")

    # Check for writing to system paths
    if re.search(r">\s*/dev/", cmd_lower):
        raise ValueError("Writing to /dev/ is blocked")

    # Allow any command that starts with an allowed prefix
    # This is permissive by design — the model is local and trusted
    first_word = cmd_lower.split()[0] if cmd_lower.split() else ""

    allowed = any(
        cmd_lower.startswith(prefix) or first_word == prefix.strip()
        for prefix in ALLOWED_PREFIXES
    )

    if not allowed:
        # Still allow it but log a warning — we don't want to be too restrictive
        # since the model is running locally and the user trusts it
        logger.warning("Unrecognized command (allowing): %s", command[:100])
