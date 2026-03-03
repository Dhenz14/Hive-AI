"""Quick validation: can the pruned base model actually write code?

Run BEFORE committing to 20+ hours of LoRA training.
If the base can't code, no LoRA will fix it (lesson from v3).
"""
import sys, time, os, torch

MODEL_PATH = os.environ.get("MODEL_PATH", "/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5")

# ── Step 1: Monkey-patch experts ──
print("[1/4] Patching MoE expert structure...")
t0 = time.time()

# Import and run only the patching function from train_v3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_v3 import patch_experts_for_quantization
patch_experts_for_quantization()
print(f"   Done in {time.time()-t0:.1f}s")

# ── Step 2: Load model ──
print("[2/4] Loading pruned model with BnB 4-bit...")
t0 = time.time()
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=quant_config,
    device_map={"": 0},
    torch_dtype=torch.bfloat16,
    attn_implementation="eager",
)
model.eval()
load_time = time.time() - t0
print(f"   Loaded in {load_time:.1f}s")

# ── Step 3: Test prompts ──
prompts = [
    {
        "name": "Python function (palindrome)",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Write a Python function that checks if a string is a valid palindrome, ignoring spaces and punctuation. Include type hints."},
        ]
    },
    {
        "name": "Hive blockchain (beem)",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Write Python code to fetch the latest 5 posts from a Hive blockchain account using the beem library."},
        ]
    },
    {
        "name": "Algorithm (binary search)",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Implement a binary search function in Python that returns the index of the target element, or -1 if not found."},
        ]
    },
]

print(f"\n[3/4] Running {len(prompts)} code generation tests...")
print("=" * 70)

all_passed = True
results = []

for i, prompt in enumerate(prompts):
    print(f"\n--- Test {i+1}: {prompt['name']} ---")

    text = tokenizer.apply_chat_template(
        prompt["messages"],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    t0 = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            temperature=0.6,
            top_p=0.95,
            top_k=40,
            do_sample=True,
            repetition_penalty=1.15,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    gen_time = time.time() - t0

    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )
    num_tokens = outputs.shape[1] - inputs["input_ids"].shape[1]
    tok_per_sec = num_tokens / gen_time if gen_time > 0 else 0

    print(f"   {num_tokens} tokens in {gen_time:.1f}s ({tok_per_sec:.1f} tok/s)")
    print(f"   Response ({len(response)} chars):")
    print(response[:1000])
    if len(response) > 1000:
        print(f"   ... [{len(response) - 1000} more chars truncated]")

    # ── Validation checks ──
    has_def = "def " in response
    has_code = has_def or "class " in response or "import " in response
    is_long_enough = len(response) > 100
    unique_words = len(set(response.lower().split()))
    no_repetition = unique_words > 20

    checks = []
    if has_def:
        checks.append("has function definition")
    if has_code:
        checks.append("has code")
    if is_long_enough:
        checks.append(f"length OK ({len(response)} chars)")
    if no_repetition:
        checks.append(f"diverse vocabulary ({unique_words} unique words)")

    passed = has_code and is_long_enough and no_repetition
    status = "PASS" if passed else "FAIL"
    results.append((prompt["name"], status, checks))

    if not passed:
        all_passed = False
        if not has_code:
            print("   FAIL: No code keywords found")
        if not is_long_enough:
            print(f"   FAIL: Too short ({len(response)} chars)")
        if not no_repetition:
            print(f"   FAIL: Repetitive ({unique_words} unique words)")
    else:
        print(f"   PASS: {', '.join(checks)}")

# ── Summary ──
print("\n" + "=" * 70)
print("[4/4] VALIDATION RESULTS")
print("=" * 70)
for name, status, checks in results:
    print(f"  [{status}] {name}: {', '.join(checks)}")
print("=" * 70)

if all_passed:
    print("\nVERDICT: ALL TESTS PASSED")
    print("The pruned base model can generate code.")
    print("Safe to proceed with LoRA training.")
else:
    print("\nVERDICT: TESTS FAILED")
    print("The pruned base model has issues.")
    print("DO NOT start LoRA training until this is fixed.")

sys.exit(0 if all_passed else 1)
