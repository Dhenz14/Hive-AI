"""HiveAI Agent Runner.

The core agentic loop:
1. Send messages to LLM (with tool definitions in system prompt)
2. Parse <tool_call> blocks from response
3. Execute tools via registry
4. Inject <tool_result> as assistant/tool turns
5. Re-prompt until model responds without tool calls (or max iterations)

Streams tokens to the client via SSE, with special events for tool
calls and results so the UI can render collapsible cards.
"""

import json
import re
import logging
import time

from .tools import execute_tool, get_tool_definitions_text, TOOL_DEFINITIONS
from ..llm.client import stream_llm_call

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10
TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _extract_tool_calls(text: str) -> list[dict]:
    """Extract all <tool_call> blocks from model output.

    Returns list of {"name": str, "arguments": dict}.
    """
    calls = []
    for match in TOOL_CALL_PATTERN.finditer(text):
        try:
            parsed = json.loads(match.group(1))
            name = parsed.get("name")
            arguments = parsed.get("arguments", {})
            if name:
                calls.append({"name": name, "arguments": arguments})
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse tool_call JSON: %s", e)
            calls.append({"name": "_parse_error", "arguments": {"raw": match.group(1), "error": str(e)}})
    return calls


def _strip_tool_calls(text: str) -> str:
    """Remove <tool_call> blocks from text, leaving the surrounding content."""
    return TOOL_CALL_PATTERN.sub("", text).strip()


def _build_agent_system_prompt(base_system: str) -> str:
    """Append tool definitions to the base system prompt."""
    tool_text = get_tool_definitions_text()
    return f"{base_system}\n\n{tool_text}"


def run_agent_stream(messages: list[dict], workspace: str, base_system: str = ""):
    """Run the agentic loop, yielding SSE events.

    Yields dicts:
      {"token": str}          — streaming text token
      {"tool_call": dict}     — tool being called (name + arguments)
      {"tool_result": dict}   — tool execution result
      {"iteration": int}      — loop counter for UI progress
      {"done": True, ...}     — final response

    Args:
        messages: The conversation so far (system + history + user message).
                  The system message will be augmented with tool definitions.
        workspace: Root directory for file operations.
        base_system: Original system prompt (tool defs get appended).
    """
    # Augment system prompt with tool definitions
    if messages and messages[0]["role"] == "system":
        messages[0]["content"] = _build_agent_system_prompt(messages[0]["content"])
    else:
        messages.insert(0, {
            "role": "system",
            "content": _build_agent_system_prompt(base_system),
        })

    iteration = 0
    total_response_parts = []

    while iteration < MAX_ITERATIONS:
        iteration += 1
        yield {"iteration": iteration, "max_iterations": MAX_ITERATIONS}
        logger.info("Agent iteration %d/%d", iteration, MAX_ITERATIONS)

        # Stream LLM response
        full_response = []
        for chunk in stream_llm_call("", messages=messages):
            if "token" in chunk:
                full_response.append(chunk["token"])
                yield {"token": chunk["token"]}
            elif "error" in chunk:
                yield {"error": chunk.get("error", "LLM error"), "done": True}
                return
            elif chunk.get("done"):
                pass  # We handle done ourselves

        response_text = "".join(full_response)

        # Check for tool calls
        tool_calls = _extract_tool_calls(response_text)

        if not tool_calls:
            # No tool calls — model is done. Return final response.
            total_response_parts.append(response_text)
            yield {"done": True, "full_response": "\n".join(total_response_parts)}
            return

        # Process each tool call
        clean_text = _strip_tool_calls(response_text)
        if clean_text:
            total_response_parts.append(clean_text)

        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": response_text})

        for tc in tool_calls:
            name = tc["name"]
            arguments = tc["arguments"]

            # Handle parse errors
            if name == "_parse_error":
                error_result = {"error": f"Could not parse tool call: {arguments.get('error', 'unknown')}"}
                yield {"tool_call": tc}
                yield {"tool_result": error_result}
                messages.append({
                    "role": "user",
                    "content": f"<tool_result>\n{json.dumps(error_result)}\n</tool_result>",
                })
                continue

            # Emit tool_call event for UI
            yield {"tool_call": {"name": name, "arguments": arguments}}

            # Execute
            start = time.time()
            result = execute_tool(name, arguments, workspace)
            elapsed = time.time() - start
            result["_elapsed_ms"] = round(elapsed * 1000)

            # Emit tool_result event for UI
            yield {"tool_result": {"name": name, "result": result}}

            # Add tool result to conversation
            messages.append({
                "role": "user",
                "content": f"<tool_result>\n{json.dumps(result, default=str)}\n</tool_result>",
            })

            logger.info("Tool %s completed in %dms", name, result["_elapsed_ms"])

    # Hit max iterations
    total_response_parts.append(f"\n[Agent stopped after {MAX_ITERATIONS} iterations]")
    yield {"done": True, "full_response": "\n".join(total_response_parts)}


def run_agent_sync(messages: list[dict], workspace: str, base_system: str = "") -> str:
    """Non-streaming version — runs full loop and returns final text.

    Useful for testing and non-interactive use cases.
    """
    final = ""
    for event in run_agent_stream(messages, workspace, base_system):
        if event.get("done"):
            final = event.get("full_response", "")
    return final
