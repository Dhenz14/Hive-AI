"""
hiveai/lora/adapter_manager.py

Runtime adapter management for llama-server multi-LoRA.

llama-server exposes:
  GET  /lora-adapters       -- list loaded adapters
  POST /lora-adapters       -- set active adapters with scales

This module provides a Python API for hot-swapping adapters
without restarting the server.
"""
import logging
import requests
from hiveai.config import LLAMA_SERVER_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds for HTTP calls


def get_loaded_adapters() -> list:
    """Query llama-server for currently loaded adapters."""
    try:
        resp = requests.get(
            f"{LLAMA_SERVER_BASE_URL}/lora-adapters", timeout=_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"lora-adapters returned {resp.status_code}")
    except requests.ConnectionError:
        logger.debug("llama-server not reachable for adapter query")
    except Exception as e:
        logger.warning(f"Could not query llama-server adapters: {e}")
    return []


def set_adapters(adapters: list) -> bool:
    """
    Hot-swap adapters on llama-server.

    Args:
        adapters: list of {"id": 0, "path": "/path/to/adapter.gguf", "scale": 1.0}
                  Empty list = base model only (all adapters disabled)

    Returns True on success.
    """
    try:
        resp = requests.post(
            f"{LLAMA_SERVER_BASE_URL}/lora-adapters",
            json=adapters,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            names = [a.get("path", "?").rsplit("/", 1)[-1] for a in adapters]
            logger.info(f"Adapters hot-swapped: {names or ['base model only']}")
            return True
        logger.error(f"Adapter swap failed: HTTP {resp.status_code} — {resp.text[:200]}")
        return False
    except requests.ConnectionError:
        logger.error("llama-server not reachable for adapter swap")
        return False
    except Exception as e:
        logger.error(f"Adapter swap failed: {e}")
        return False


def add_adapter(path: str, scale: float = 1.0) -> bool:
    """Add an adapter to the currently loaded set."""
    current = get_loaded_adapters()
    next_id = max((a.get("id", 0) for a in current), default=-1) + 1
    current.append({"id": next_id, "path": path, "scale": scale})
    return set_adapters(current)


def remove_adapter(path: str) -> bool:
    """Remove an adapter by path."""
    current = get_loaded_adapters()
    filtered = [a for a in current if a.get("path") != path]
    if len(filtered) == len(current):
        logger.warning(f"Adapter not found: {path}")
        return False
    return set_adapters(filtered)


def use_base_model_only() -> bool:
    """Disable all adapters, use base model."""
    return set_adapters([])


def get_server_status() -> dict:
    """Quick health check on llama-server."""
    try:
        resp = requests.get(f"{LLAMA_SERVER_BASE_URL}/health", timeout=5)
        return {
            "online": resp.status_code == 200,
            "status_code": resp.status_code,
        }
    except requests.ConnectionError:
        return {"online": False, "status_code": None}
    except Exception as e:
        return {"online": False, "error": str(e)}
