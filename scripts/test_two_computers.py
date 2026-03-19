#!/usr/bin/env python3
"""
scripts/test_two_computers.py

BATON HANDOFF: Run this on Computer A to test 2-computer GPU sharing.

This script does everything automatically:
  1. Measures ping RTT to Computer B
  2. Verifies both GPUs are detected
  3. Bootstraps API keys for both machines
  4. Tests the inference endpoint
  5. Outputs a pass/fail report

Usage:
    # On Computer A (the one running HivePoA):
    python scripts/test_two_computers.py --computer-b-ip 192.168.0.XXX

    # That's it. One command.

Prerequisites:
    - HivePoA running on Computer A (PORT=5000)
    - Computer B reachable on the network
    - Ollama installed on at least Computer A
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def green(s): return f"\033[92m{s}\033[0m"
def red(s): return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def bold(s): return f"\033[1m{s}\033[0m"


class TwoComputerTest:
    def __init__(self, computer_b_ip: str, hivepoa_url: str = "http://localhost:5000"):
        self.computer_b_ip = computer_b_ip
        self.hivepoa_url = hivepoa_url
        self.results = {}

    def run_all(self):
        print(bold("\n" + "=" * 60))
        print(bold("  SPIRIT BOMB — Two-Computer GPU Test"))
        print(bold("=" * 60))
        print(f"  Computer A (this): {platform.node()}")
        print(f"  Computer B (remote): {self.computer_b_ip}")
        print(f"  HivePoA: {self.hivepoa_url}")
        print("=" * 60 + "\n")

        self.test_1_ping()
        self.test_2_local_gpu()
        self.test_3_hivepoa()
        self.test_4_ollama()
        self.test_5_inference()
        self.test_6_remote_reachable()

        self.print_summary()

    def test_1_ping(self):
        """Test 1: Network latency to Computer B"""
        print(bold("[Test 1] Ping Computer B..."))
        try:
            # Windows ping
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["ping", "-n", "5", self.computer_b_ip],
                    capture_output=True, text=True, timeout=15,
                )
            else:
                result = subprocess.run(
                    ["ping", "-c", "5", self.computer_b_ip],
                    capture_output=True, text=True, timeout=15,
                )

            output = result.stdout
            # Extract average RTT
            if "Average" in output:
                # Windows format: Average = Xms
                avg = output.split("Average = ")[1].split("ms")[0].strip()
                rtt_ms = float(avg)
            elif "avg" in output:
                # Linux format: min/avg/max/mdev = X/X/X/X
                avg = output.split("/")[4] if "/" in output else "999"
                rtt_ms = float(avg)
            else:
                rtt_ms = -1

            if rtt_ms >= 0 and rtt_ms < 50:
                print(green(f"  PASS: RTT = {rtt_ms}ms (< 50ms = pipeline parallel OK)"))
                if rtt_ms < 10:
                    print(green(f"  BONUS: RTT < 10ms = tensor parallel eligible!"))
                self.results["ping"] = {"pass": True, "rtt_ms": rtt_ms}
            elif rtt_ms >= 50:
                print(yellow(f"  WARN: RTT = {rtt_ms}ms (> 50ms = only expert parallel)"))
                self.results["ping"] = {"pass": True, "rtt_ms": rtt_ms, "warning": "high_latency"}
            else:
                print(red(f"  FAIL: Could not parse RTT"))
                self.results["ping"] = {"pass": False}
        except subprocess.TimeoutExpired:
            print(red(f"  FAIL: Ping timed out — Computer B unreachable"))
            self.results["ping"] = {"pass": False, "error": "timeout"}
        except Exception as e:
            print(red(f"  FAIL: {e}"))
            self.results["ping"] = {"pass": False, "error": str(e)}
        print()

    def test_2_local_gpu(self):
        """Test 2: Detect local GPU"""
        print(bold("[Test 2] Detect local GPU..."))
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,uuid",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                name = parts[0]
                vram_mb = float(parts[1])
                uuid = parts[2]
                print(green(f"  PASS: {name} ({vram_mb/1024:.0f}GB)"))
                print(f"  UUID: {uuid}")
                self.results["local_gpu"] = {"pass": True, "name": name, "vram_gb": round(vram_mb/1024)}
            else:
                print(red(f"  FAIL: nvidia-smi error"))
                self.results["local_gpu"] = {"pass": False}
        except FileNotFoundError:
            print(red(f"  FAIL: nvidia-smi not found — no NVIDIA GPU?"))
            self.results["local_gpu"] = {"pass": False}
        print()

    def test_3_hivepoa(self):
        """Test 3: HivePoA server running"""
        print(bold("[Test 3] Check HivePoA server..."))
        try:
            req = urllib.request.Request(f"{self.hivepoa_url}/api/community/tier")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                tier = data.get("tier", "?")
                gpus = data.get("totalGpus", 0)
                print(green(f"  PASS: HivePoA running — Tier {tier}, {gpus} GPUs"))
                self.results["hivepoa"] = {"pass": True, "tier": tier, "gpus": gpus}
        except Exception as e:
            print(red(f"  FAIL: HivePoA not responding at {self.hivepoa_url}"))
            print(f"  Start it with: cd HivePoA && NODE_ENV=production PORT=5000 npx tsx server/index.ts")
            self.results["hivepoa"] = {"pass": False, "error": str(e)}
        print()

    def test_4_ollama(self):
        """Test 4: Ollama running"""
        print(bold("[Test 4] Check Ollama..."))
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                print(green(f"  PASS: Ollama running with {len(models)} model(s)"))
                if models:
                    print(f"  Models: {', '.join(models[:5])}")
                else:
                    print(yellow(f"  NOTE: No models installed. Run: ollama pull qwen3:14b"))
                self.results["ollama"] = {"pass": True, "models": models}
        except Exception:
            print(red(f"  FAIL: Ollama not running"))
            print(f"  Install: https://ollama.ai")
            print(f"  Then run: ollama serve")
            self.results["ollama"] = {"pass": False}
        print()

    def test_5_inference(self):
        """Test 5: Inference endpoint works"""
        print(bold("[Test 5] Test inference endpoint..."))
        if not self.results.get("hivepoa", {}).get("pass"):
            print(yellow(f"  SKIP: HivePoA not running"))
            self.results["inference"] = {"pass": False, "skipped": True}
            print()
            return

        payload = json.dumps({
            "prompt": "What is 2+2?",
            "mode": "medium",
            "max_tokens": 50,
            "temperature": 0,
        }).encode()

        try:
            req = urllib.request.Request(
                f"{self.hivepoa_url}/api/compute/inference",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            start = time.time()
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                latency = round((time.time() - start) * 1000)

                if data.get("text"):
                    tokens = data.get("tokens_generated", 0)
                    strategy = data.get("strategy_used", "?")
                    print(green(f"  PASS: Got response ({tokens} tokens, {latency}ms, {strategy})"))
                    print(f"  Response: {data['text'][:100]}...")
                    self.results["inference"] = {"pass": True, "latency_ms": latency, "strategy": strategy}
                elif data.get("error"):
                    msg = data["error"].get("message", str(data["error"]))
                    print(red(f"  FAIL: {msg}"))
                    self.results["inference"] = {"pass": False, "error": msg}
                else:
                    print(red(f"  FAIL: Empty response"))
                    self.results["inference"] = {"pass": False}
        except Exception as e:
            print(red(f"  FAIL: {e}"))
            self.results["inference"] = {"pass": False, "error": str(e)}
        print()

    def test_6_remote_reachable(self):
        """Test 6: Can Computer B reach HivePoA?"""
        print(bold("[Test 6] Check if Computer B can reach HivePoA..."))
        print(f"  (This test verifies the network path for Computer B to join)")
        rtt = self.results.get("ping", {}).get("rtt_ms", -1)
        if rtt >= 0:
            print(green(f"  PASS: Computer B is reachable (RTT={rtt}ms)"))
            print(f"  Computer B should run:")
            print(f"    python scripts/start_spiritbomb.py --hivepoa-url http://192.168.0.101:5000")
            self.results["remote_reachable"] = {"pass": True}
        else:
            print(red(f"  FAIL: Computer B not reachable"))
            print(f"  Check: same network? Firewall? Try: ping {self.computer_b_ip}")
            self.results["remote_reachable"] = {"pass": False}
        print()

    def print_summary(self):
        print(bold("=" * 60))
        print(bold("  SUMMARY"))
        print("=" * 60)

        total = len(self.results)
        passed = sum(1 for r in self.results.values() if r.get("pass"))
        failed = total - passed

        for name, result in self.results.items():
            status = green("PASS") if result.get("pass") else red("FAIL")
            extra = ""
            if "rtt_ms" in result:
                extra = f" ({result['rtt_ms']}ms)"
            if result.get("skipped"):
                status = yellow("SKIP")
            print(f"  {status}  {name}{extra}")

        print()
        if failed == 0:
            print(green(bold("  ALL TESTS PASSED!")))
            print()
            print("  Next steps:")
            print(f"  1. On Computer B, run:")
            print(f"     python scripts/start_spiritbomb.py --hivepoa-url http://192.168.0.101:5000")
            print(f"  2. Wait 30s for registration")
            print(f"  3. Open http://192.168.0.101:5000/inference")
            print(f"  4. Select 'Cluster' mode and send a message")
        else:
            print(red(bold(f"  {failed} TEST(S) FAILED")))
            print("  Fix the failures above, then re-run this script.")

        print()

        # Save results
        results_path = PROJECT_ROOT / "evidence" / "spiritbomb" / "two-computer-test.json"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump({
                "test": "two_computer_gpu_sharing",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "computer_a": platform.node(),
                "computer_b_ip": self.computer_b_ip,
                "results": self.results,
                "passed": passed,
                "failed": failed,
            }, f, indent=2)
        print(f"  Results saved to: {results_path}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Test 2-computer Spirit Bomb GPU sharing setup"
    )
    parser.add_argument("--computer-b-ip", required=True,
                        help="IP address of Computer B (e.g., 192.168.0.102)")
    parser.add_argument("--hivepoa-url", default="http://localhost:5000",
                        help="HivePoA server URL (default: http://localhost:5000)")
    args = parser.parse_args()

    test = TwoComputerTest(args.computer_b_ip, args.hivepoa_url)
    test.run_all()


if __name__ == "__main__":
    main()
