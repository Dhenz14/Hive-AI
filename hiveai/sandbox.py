"""
hiveai/sandbox.py

Safe subprocess-based code execution sandbox (Python + JavaScript + C++ + Rust).

Used by:
  - Evaluation harness (run test assertions against LLM responses)
  - Chat (verify code blocks in AI answers)
  - Benchmark (auto-grade LoRA vs base model)
  - Distiller (execution-guided self-refinement for all supported languages)

Security: Runs code in a separate process with timeout enforcement.
All output is captured and capped at 10KB.
"""

import ast
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 10_000  # Cap stdout/stderr at 10KB


def extract_code_blocks(text: str, languages: str = "all") -> list[dict]:
    """
    Extract code blocks from markdown-formatted text.

    Args:
        text: Markdown text containing fenced code blocks
        languages: Which languages to extract —
            "all", "python", "javascript", "cpp", "rust", "go"

    Returns list of dicts: [{code, language, index}, ...]
    Includes blocks tagged as python/py/js/javascript/ts/typescript/
    cpp/c++/rust/rs/go/golang and untagged blocks that parse as valid Python.
    """
    # Match fenced code blocks with optional language tag
    pattern = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)
    blocks = []

    want_python = languages in ("all", "python")
    want_js = languages in ("all", "javascript")
    want_cpp = languages in ("all", "cpp")
    want_rust = languages in ("all", "rust")
    want_go = languages in ("all", "go")

    for match in pattern.finditer(text):
        lang = match.group(1).lower()
        code = match.group(2).strip()
        if not code:
            continue

        # Accept explicitly Python-tagged blocks
        if want_python and lang in ("python", "py", "python3"):
            blocks.append({"code": code, "language": "python", "index": match.start()})
        # Accept JavaScript/TypeScript-tagged blocks
        elif want_js and lang in ("javascript", "js", "typescript", "ts"):
            blocks.append({"code": code, "language": "javascript", "index": match.start()})
        # Accept C/C++-tagged blocks
        elif want_cpp and lang in ("cpp", "c++", "cc", "cxx", "c"):
            blocks.append({"code": code, "language": "cpp", "index": match.start()})
        # Accept Rust-tagged blocks
        elif want_rust and lang in ("rust", "rs"):
            blocks.append({"code": code, "language": "rust", "index": match.start()})
        # Accept Go-tagged blocks
        elif want_go and lang in ("go", "golang"):
            blocks.append({"code": code, "language": "go", "index": match.start()})
        # Accept untagged blocks if they parse as Python
        elif want_python and lang == "":
            try:
                ast.parse(code)
                blocks.append({"code": code, "language": "python", "index": match.start()})
            except SyntaxError:
                pass  # Not Python, skip

    return blocks


def validate_syntax(code: str) -> dict:
    """
    Check if code is valid Python by attempting ast.parse().

    Returns:
        {valid: bool, error: str|None, line: int|None}
    """
    try:
        ast.parse(code)
        return {"valid": True, "error": None, "line": None}
    except SyntaxError as e:
        return {"valid": False, "error": str(e), "line": e.lineno}


def execute_python(code: str, timeout: int = 30) -> dict:
    """
    Execute Python code safely in a subprocess with timeout.

    Args:
        code: Python source code to execute
        timeout: Maximum execution time in seconds (default 30, max 60)

    Returns:
        {success, stdout, stderr, return_code, timed_out, execution_time_ms, error_type}
    """
    timeout = min(max(timeout, 1), 60)  # Clamp 1-60s

    # Validate syntax first (fast fail)
    syntax = validate_syntax(code)
    if not syntax["valid"]:
        return {
            "success": False,
            "stdout": "",
            "stderr": syntax["error"],
            "return_code": 1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": "SyntaxError",
        }

    tmp_path = None
    try:
        # Write to temp file
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name

        # Build subprocess args
        run_kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "env": {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
        }

        # Windows: create new process group for clean timeout handling
        if sys.platform == "win32":
            run_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        t0 = time.time()
        result = subprocess.run([sys.executable, tmp_path], **run_kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:MAX_OUTPUT_BYTES],
            "stderr": result.stderr[:MAX_OUTPUT_BYTES],
            "return_code": result.returncode,
            "timed_out": False,
            "execution_time_ms": elapsed_ms,
            "error_type": _classify_error(result.stderr) if result.returncode != 0 else None,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "return_code": -1,
            "timed_out": True,
            "execution_time_ms": timeout * 1000,
            "error_type": "TimeoutError",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": type(e).__name__,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _classify_error(stderr: str) -> str:
    """Extract the error type from Python traceback stderr."""
    if not stderr:
        return "UnknownError"
    # Look for the last line matching "ErrorType: message"
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if "Error" in line and ":" in line:
            return line.split(":")[0].strip()
    return "RuntimeError"


def execute_javascript(code: str, timeout: int = 30) -> dict:
    """
    Execute JavaScript code in a Node.js subprocess with timeout.

    Requires Node.js to be installed. Returns graceful error if not available.

    Args:
        code: JavaScript source code to execute
        timeout: Maximum execution time in seconds (default 30, max 60)

    Returns:
        {success, stdout, stderr, return_code, timed_out, execution_time_ms, error_type}
    """
    timeout = min(max(timeout, 1), 60)

    node_cmd = shutil.which("node")
    if not node_cmd:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Node.js not found (install Node.js to enable JS execution)",
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": "EnvironmentError",
        }

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name

        run_kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
        }

        if sys.platform == "win32":
            run_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        t0 = time.time()
        result = subprocess.run([node_cmd, tmp_path], **run_kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:MAX_OUTPUT_BYTES],
            "stderr": result.stderr[:MAX_OUTPUT_BYTES],
            "return_code": result.returncode,
            "timed_out": False,
            "execution_time_ms": elapsed_ms,
            "error_type": _classify_error(result.stderr) if result.returncode != 0 else None,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "return_code": -1,
            "timed_out": True,
            "execution_time_ms": timeout * 1000,
            "error_type": "TimeoutError",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": type(e).__name__,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def execute_cpp(code: str, timeout: int = 30) -> dict:
    """
    Compile and execute C++ code in a subprocess with timeout.

    Requires g++ or clang++ to be installed. Compiles with C++20 standard,
    warnings enabled, and AddressSanitizer when available.

    Args:
        code: C++ source code to compile and execute
        timeout: Maximum execution time in seconds (default 30, max 60)

    Returns:
        {success, stdout, stderr, return_code, timed_out, execution_time_ms,
         error_type, compile_stderr}
    """
    timeout = min(max(timeout, 1), 60)

    # Find compiler
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        return {
            "success": False,
            "stdout": "",
            "stderr": "C++ compiler not found (install g++ or clang++ to enable C++ execution)",
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": "EnvironmentError",
            "compile_stderr": "",
        }

    src_path = None
    exe_path = None
    try:
        # Write source file
        with tempfile.NamedTemporaryFile(
            suffix=".cpp", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            src_path = f.name

        exe_path = src_path.replace(".cpp", ".exe" if sys.platform == "win32" else "")

        # Compile
        compile_cmd = [compiler, "-std=c++20", "-Wall", "-Wextra", "-o", exe_path, src_path]
        # Add sanitizers on Linux/macOS (not Windows)
        if sys.platform != "win32":
            compile_cmd.insert(3, "-fsanitize=address,undefined")

        compile_kwargs = {"capture_output": True, "text": True, "timeout": 30}
        if sys.platform == "win32":
            compile_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        compile_result = subprocess.run(compile_cmd, **compile_kwargs)
        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr[:MAX_OUTPUT_BYTES],
                "return_code": compile_result.returncode,
                "timed_out": False,
                "execution_time_ms": 0,
                "error_type": "CompileError",
                "compile_stderr": compile_result.stderr[:MAX_OUTPUT_BYTES],
            }

        # Execute
        run_kwargs = {"capture_output": True, "text": True, "timeout": timeout}
        if sys.platform == "win32":
            run_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        t0 = time.time()
        result = subprocess.run([exe_path], **run_kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:MAX_OUTPUT_BYTES],
            "stderr": result.stderr[:MAX_OUTPUT_BYTES],
            "return_code": result.returncode,
            "timed_out": False,
            "execution_time_ms": elapsed_ms,
            "error_type": "RuntimeError" if result.returncode != 0 else None,
            "compile_stderr": "",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "return_code": -1,
            "timed_out": True,
            "execution_time_ms": timeout * 1000,
            "error_type": "TimeoutError",
            "compile_stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": type(e).__name__,
            "compile_stderr": "",
        }
    finally:
        for path in (src_path, exe_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


def execute_rust(code: str, timeout: int = 30) -> dict:
    """
    Compile and execute Rust code in a subprocess with timeout.

    Requires rustc to be installed. Uses 2021 edition by default.

    Args:
        code: Rust source code to compile and execute
        timeout: Maximum execution time in seconds (default 30, max 60)

    Returns:
        {success, stdout, stderr, return_code, timed_out, execution_time_ms,
         error_type, compile_stderr}
    """
    timeout = min(max(timeout, 1), 60)

    rustc = shutil.which("rustc")
    if not rustc:
        return {
            "success": False,
            "stdout": "",
            "stderr": "rustc not found (install Rust toolchain to enable Rust execution)",
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": "EnvironmentError",
            "compile_stderr": "",
        }

    src_path = None
    exe_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".rs", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            src_path = f.name

        exe_path = src_path.replace(".rs", ".exe" if sys.platform == "win32" else "")

        # Compile
        compile_cmd = [rustc, "--edition", "2021", "-o", exe_path, src_path]

        compile_kwargs = {"capture_output": True, "text": True, "timeout": 30}
        if sys.platform == "win32":
            compile_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        compile_result = subprocess.run(compile_cmd, **compile_kwargs)
        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr[:MAX_OUTPUT_BYTES],
                "return_code": compile_result.returncode,
                "timed_out": False,
                "execution_time_ms": 0,
                "error_type": "CompileError",
                "compile_stderr": compile_result.stderr[:MAX_OUTPUT_BYTES],
            }

        # Execute
        run_kwargs = {"capture_output": True, "text": True, "timeout": timeout}
        if sys.platform == "win32":
            run_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        t0 = time.time()
        result = subprocess.run([exe_path], **run_kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:MAX_OUTPUT_BYTES],
            "stderr": result.stderr[:MAX_OUTPUT_BYTES],
            "return_code": result.returncode,
            "timed_out": False,
            "execution_time_ms": elapsed_ms,
            "error_type": "RuntimeError" if result.returncode != 0 else None,
            "compile_stderr": "",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "return_code": -1,
            "timed_out": True,
            "execution_time_ms": timeout * 1000,
            "error_type": "TimeoutError",
            "compile_stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": type(e).__name__,
            "compile_stderr": "",
        }
    finally:
        for path in (src_path, exe_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


def execute_go(code: str, timeout: int = 30) -> dict:
    """
    Compile and execute Go code in a subprocess with timeout.

    Requires go to be installed. Creates a temp directory with go.mod
    for module support.

    Args:
        code: Go source code to compile and execute
        timeout: Maximum execution time in seconds (default 30, max 60)

    Returns:
        {success, stdout, stderr, return_code, timed_out, execution_time_ms,
         error_type, compile_stderr}
    """
    timeout = min(max(timeout, 1), 60)

    go_cmd = shutil.which("go")
    if not go_cmd:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Go not found (install Go to enable Go execution)",
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": "EnvironmentError",
            "compile_stderr": "",
        }

    tmp_dir = None
    try:
        # Go needs a module context — create temp dir with go.mod
        tmp_dir = tempfile.mkdtemp(prefix="hiveai_go_")
        src_path = os.path.join(tmp_dir, "main.go")
        mod_path = os.path.join(tmp_dir, "go.mod")

        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)
        with open(mod_path, "w", encoding="utf-8") as f:
            f.write("module hiveai_eval\n\ngo 1.21\n")

        run_base = {
            "capture_output": True,
            "text": True,
            "cwd": tmp_dir,
        }
        if sys.platform == "win32":
            run_base["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        # Compile
        compile_result = subprocess.run(
            [go_cmd, "build", "-o", "main.exe" if sys.platform == "win32" else "main", "."],
            timeout=30, **run_base,
        )
        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr[:MAX_OUTPUT_BYTES],
                "return_code": compile_result.returncode,
                "timed_out": False,
                "execution_time_ms": 0,
                "error_type": "CompileError",
                "compile_stderr": compile_result.stderr[:MAX_OUTPUT_BYTES],
            }

        # Execute
        exe_path = os.path.join(tmp_dir, "main.exe" if sys.platform == "win32" else "main")
        t0 = time.time()
        result = subprocess.run(
            [exe_path], timeout=timeout,
            capture_output=True, text=True,
            **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {}),
        )
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:MAX_OUTPUT_BYTES],
            "stderr": result.stderr[:MAX_OUTPUT_BYTES],
            "return_code": result.returncode,
            "timed_out": False,
            "execution_time_ms": elapsed_ms,
            "error_type": "RuntimeError" if result.returncode != 0 else None,
            "compile_stderr": "",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "return_code": -1,
            "timed_out": True,
            "execution_time_ms": timeout * 1000,
            "error_type": "TimeoutError",
            "compile_stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "timed_out": False,
            "execution_time_ms": 0,
            "error_type": type(e).__name__,
            "compile_stderr": "",
        }
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except OSError:
                pass


def verify_response_code(response: str, timeout: int = 30) -> dict:
    """
    Extract and verify all code blocks (Python, JavaScript, C++, Rust) in an LLM response.

    Returns aggregate results:
        {total_blocks, python_blocks, js_blocks, cpp_blocks, rust_blocks,
         valid_syntax, executed, passed, failed, timed_out, results[],
         overall_pass_rate}
    """
    blocks = extract_code_blocks(response)
    results = []
    passed = 0
    failed = 0
    timed_out = 0
    valid_syntax = 0
    python_blocks = 0
    js_blocks = 0
    cpp_blocks = 0
    rust_blocks = 0
    go_blocks = 0

    # Execution functions by language
    executors = {
        "python": execute_python,
        "javascript": execute_javascript,
        "cpp": execute_cpp,
        "rust": execute_rust,
        "go": execute_go,
    }

    for block in blocks:
        lang = block.get("language", "python")
        entry = {
            "index": block["index"],
            "language": lang,
            "code_preview": block["code"][:80].replace("\n", " "),
            "syntax_valid": None,
            "execution": None,
        }

        if lang == "python":
            python_blocks += 1
            syntax = validate_syntax(block["code"])
            entry["syntax_valid"] = syntax["valid"]
            if syntax["valid"]:
                valid_syntax += 1
                result = execute_python(block["code"], timeout)
                entry["execution"] = result
                if result["timed_out"]:
                    timed_out += 1
                elif result["success"]:
                    passed += 1
                else:
                    failed += 1
        elif lang in executors:
            if lang == "javascript":
                js_blocks += 1
            elif lang == "cpp":
                cpp_blocks += 1
            elif lang == "rust":
                rust_blocks += 1
            elif lang == "go":
                go_blocks += 1
            entry["syntax_valid"] = True  # Compilation validates syntax
            valid_syntax += 1
            result = executors[lang](block["code"], timeout)
            entry["execution"] = result
            if result["timed_out"]:
                timed_out += 1
            elif result["success"]:
                passed += 1
            else:
                failed += 1

        results.append(entry)

    executed = passed + failed + timed_out
    return {
        "total_blocks": len(blocks),
        "python_blocks": python_blocks,
        "js_blocks": js_blocks,
        "cpp_blocks": cpp_blocks,
        "rust_blocks": rust_blocks,
        "go_blocks": go_blocks,
        "valid_syntax": valid_syntax,
        "executed": executed,
        "passed": passed,
        "failed": failed,
        "timed_out": timed_out,
        "results": results,
        "overall_pass_rate": passed / max(executed, 1),
    }


def run_test_code(test_code: str, response_text: str, timeout: int = 30) -> dict:
    """
    Run test assertions against code extracted from an LLM response.

    Extracts all Python code blocks from response_text, concatenates them,
    then appends test_code at the end. Executes the combined script.

    Returns:
        {tests_passed: bool, execution: {sandbox result dict},
         blocks_used: int, combined_code_preview: str}
    """
    blocks = extract_code_blocks(response_text)
    if not blocks:
        return {
            "tests_passed": False,
            "execution": {
                "success": False,
                "stdout": "",
                "stderr": "No Python code blocks found in response",
                "return_code": 1,
                "timed_out": False,
                "execution_time_ms": 0,
                "error_type": "NoCodeError",
            },
            "blocks_used": 0,
            "combined_code_preview": "",
        }

    # Concatenate all Python blocks, then append test code
    response_code = "\n\n".join(block["code"] for block in blocks)
    combined = f"{response_code}\n\n# === Test Assertions ===\n{test_code}"

    result = execute_python(combined, timeout)
    tests_passed = result["success"] and "ALL TESTS PASSED" in result["stdout"]

    return {
        "tests_passed": tests_passed,
        "execution": result,
        "blocks_used": len(blocks),
        "combined_code_preview": combined[:200],
    }
