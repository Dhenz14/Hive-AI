"""Quick validation: load a LoRA checkpoint and generate text to verify quality.

Usage (run from WSL):
    python scripts/validate_training.py                    # Check latest checkpoint
    python scripts/validate_training.py --step 100         # Check specific checkpoint
    python scripts/validate_training.py --monitor          # Watch training log for bad signs
"""
import argparse
import json
import os
import re
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def monitor_training(log_path: str, check_interval: int = 30):
    """Watch training log and alert on bad signs."""
    print(f"Monitoring {log_path} every {check_interval}s...")
    print("RED FLAGS: loss > 3.0, grad_norm NaN/> 10, loss not decreasing after 20 steps\n")

    losses = []
    last_size = 0

    while True:
        try:
            with open(log_path, "r") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"Log not found: {log_path}")
            time.sleep(check_interval)
            continue

        if len(content) == last_size:
            time.sleep(check_interval)
            continue
        last_size = len(content)

        # Parse loss and grad_norm from log lines
        for line in content.split("\n"):
            # Match: {'loss': '0.7743', 'grad_norm': '0.1015', ...}
            loss_match = re.search(r"'loss':\s*'([0-9.]+)'", line)
            grad_match = re.search(r"'grad_norm':\s*'([0-9.enan+-]+)'", line)
            step_match = re.search(r"Step (\d+)/(\d+)", line)

            if loss_match:
                loss = float(loss_match.group(1))
                grad = grad_match.group(1) if grad_match else "?"
                step = step_match.group(1) if step_match else "?"

                # Only track new entries
                entry = (step, loss, grad)
                if entry not in losses:
                    losses.append(entry)

                    # Status indicator
                    status = "OK"
                    if loss > 5.0:
                        status = "CRITICAL - loss near random!"
                    elif loss > 3.0:
                        status = "WARNING - loss too high"
                    elif "nan" in str(grad).lower():
                        status = "CRITICAL - grad_norm is NaN!"
                    elif grad != "?" and float(grad) > 10:
                        status = "WARNING - grad_norm exploding"

                    # Check for loss stagnation (not decreasing after 20+ logged steps)
                    if len(losses) > 20:
                        recent = [l[1] for l in losses[-10:]]
                        older = [l[1] for l in losses[-20:-10]]
                        if min(recent) >= min(older) * 0.98:
                            status = "WARNING - loss stagnating"

                    icon = "+" if status == "OK" else "!"
                    print(f"  [{icon}] Step {step:>4s} | loss={loss:.4f} | grad={grad:>8s} | {status}")

        time.sleep(check_interval)


def generate_test(checkpoint_dir: str):
    """Load checkpoint and generate sample outputs to verify quality."""
    import torch

    print(f"\nLoading checkpoint from {checkpoint_dir}...")

    # Unsloth can load a LoRA checkpoint directly (base model + adapter in one call)
    from unsloth import FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=checkpoint_dir,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    print("Model loaded + inference mode enabled")

    # Test prompts — mix of easy and hard
    test_prompts = [
        "Write a Python function to find the longest palindromic substring.",
        "Explain how async/await works in Python with a practical example.",
        "Write a binary search tree implementation in Python with insert, search, and delete.",
    ]

    print("\n" + "=" * 60)
    print("GENERATION TEST")
    print("=" * 60)

    for prompt in test_prompts:
        messages = [
            {"role": "system", "content": "You are HiveAI, an expert coding assistant."},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
            )

        response = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        print(f"\nPROMPT: {prompt[:80]}")
        print(f"RESPONSE (first 500 chars):")
        print(response[:500])
        print("-" * 40)

        # Quick quality check
        if len(response.strip()) < 20:
            print("  WARNING: Very short response!")
        if response.count(response[:10]) > 3 and len(response) > 50:
            print("  WARNING: Repetitive output detected!")
        has_code = "def " in response or "class " in response or "```" in response
        if not has_code and "code" in prompt.lower():
            print("  WARNING: No code in response to coding prompt!")

    print("\n" + "=" * 60)
    print("If outputs look coherent with real code, training is on track.")
    print("If outputs are gibberish/repetitive, STOP training immediately.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Validate LoRA training quality")
    parser.add_argument("--monitor", action="store_true",
                        help="Watch training log for bad signs")
    parser.add_argument("--log", default=os.path.join(PROJECT_ROOT, "logs", "train_v6_full_r4.log"),
                        help="Training log path")
    parser.add_argument("--step", type=int, default=0,
                        help="Load specific checkpoint step (0=latest final adapter)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Monitor check interval in seconds")
    args = parser.parse_args()

    if args.monitor:
        monitor_training(args.log, args.interval)
    else:
        # Find checkpoint
        output_dir = os.path.join(PROJECT_ROOT, "loras", "v6")
        if args.step > 0:
            checkpoint_dir = os.path.join(output_dir, f"checkpoint-{args.step}")
        else:
            # Use final adapter or latest checkpoint
            if os.path.exists(os.path.join(output_dir, "adapter_config.json")):
                checkpoint_dir = output_dir
            else:
                checkpoints = sorted(
                    [d for d in os.listdir(output_dir) if d.startswith("checkpoint-")],
                    key=lambda x: int(x.split("-")[1])
                )
                if not checkpoints:
                    print("No checkpoints found yet. Use --monitor to watch training.")
                    sys.exit(1)
                checkpoint_dir = os.path.join(output_dir, checkpoints[-1])

        print(f"Checkpoint: {checkpoint_dir}")
        generate_test(checkpoint_dir)


if __name__ == "__main__":
    main()
