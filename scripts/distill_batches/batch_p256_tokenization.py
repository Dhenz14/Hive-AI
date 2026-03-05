"""Tokenization and text processing — BPE, SentencePiece, tokenizer training."""

PAIRS = [
    (
        "ai/bpe-tokenization",
        "Show BPE (Byte-Pair Encoding) tokenization: training algorithm, encoding/decoding, and vocabulary management for LLMs.",
        '''BPE tokenization from scratch:

```python
from collections import Counter, defaultdict
from typing import Optional
import re
import json


class BPETokenizer:
    """Byte-Pair Encoding tokenizer (GPT-style).

    Training:
    1. Start with character-level vocabulary
    2. Find most frequent adjacent pair
    3. Merge that pair into a new token
    4. Repeat until vocabulary size reached

    This creates subword tokens: common words become single tokens,
    rare words split into known subwords.
    """

    def __init__(self, vocab_size: int = 32000):
        self.target_vocab_size = vocab_size
        self.merges: list[tuple[str, str]] = []
        self.vocab: dict[str, int] = {}
        self.inverse_vocab: dict[int, str] = {}

    def train(self, texts: list[str]):
        """Train BPE on corpus."""
        # Pre-tokenize: split on whitespace, add word boundary markers
        word_freqs = Counter()
        for text in texts:
            words = re.findall(r"\\S+|\\s+", text)
            for word in words:
                # Represent as tuple of characters
                word_freqs[tuple(word)] += 1

        # Initialize vocabulary with all characters
        chars = set()
        for word in word_freqs:
            chars.update(word)
        self.vocab = {c: i for i, c in enumerate(sorted(chars))}
        next_id = len(self.vocab)

        # Iteratively merge most frequent pairs
        current_words = dict(word_freqs)

        while len(self.vocab) < self.target_vocab_size:
            # Count pair frequencies
            pair_counts = Counter()
            for word, freq in current_words.items():
                for i in range(len(word) - 1):
                    pair_counts[(word[i], word[i + 1])] += freq

            if not pair_counts:
                break

            # Find most frequent pair
            best_pair = pair_counts.most_common(1)[0][0]
            self.merges.append(best_pair)

            # Add merged token to vocabulary
            merged_token = best_pair[0] + best_pair[1]
            self.vocab[merged_token] = next_id
            next_id += 1

            # Apply merge to all words
            new_words = {}
            for word, freq in current_words.items():
                new_word = self._apply_merge(word, best_pair)
                new_words[new_word] = freq
            current_words = new_words

        self.inverse_vocab = {v: k for k, v in self.vocab.items()}

    def _apply_merge(self, word: tuple[str, ...], pair: tuple[str, str]) -> tuple:
        """Apply a single merge operation to a word."""
        new_word = []
        i = 0
        while i < len(word):
            if i < len(word) - 1 and word[i] == pair[0] and word[i + 1] == pair[1]:
                new_word.append(pair[0] + pair[1])
                i += 2
            else:
                new_word.append(word[i])
                i += 1
        return tuple(new_word)

    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs."""
        words = re.findall(r"\\S+|\\s+", text)
        tokens = []

        for word in words:
            word_tokens = list(word)  # Start with characters

            # Apply merges in order
            for pair in self.merges:
                i = 0
                new_tokens = []
                while i < len(word_tokens):
                    if (i < len(word_tokens) - 1 and
                        word_tokens[i] == pair[0] and word_tokens[i + 1] == pair[1]):
                        new_tokens.append(pair[0] + pair[1])
                        i += 2
                    else:
                        new_tokens.append(word_tokens[i])
                        i += 1
                word_tokens = new_tokens

            tokens.extend(self.vocab.get(t, 0) for t in word_tokens)

        return tokens

    def decode(self, ids: list[int]) -> str:
        """Decode token IDs back to text."""
        return "".join(self.inverse_vocab.get(i, "") for i in ids)

    def save(self, path: str):
        data = {
            "vocab": self.vocab,
            "merges": [list(m) for m in self.merges],
        }
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, path: str):
        with open(path) as f:
            data = json.load(f)
        self.vocab = data["vocab"]
        self.merges = [tuple(m) for m in data["merges"]]
        self.inverse_vocab = {v: k for k, v in self.vocab.items()}
```

Tokenizer comparison:

| Tokenizer | Used by | Vocab size | Method |
|-----------|---------|-----------|--------|
| **BPE** | GPT, LLaMA | 32K-128K | Frequency merging |
| **WordPiece** | BERT | 30K | Likelihood merging |
| **Unigram (SentencePiece)** | T5, Gemma | 32K | Probability pruning |
| **Tiktoken** | GPT-4 | 100K | BPE (byte-level) |

Key patterns:
1. **Subword tokenization** — between character and word level; handles unknown words gracefully
2. **Byte-level BPE** — start from bytes (256) not characters; handles any Unicode
3. **Merge priority** — merges applied in training order during encoding; deterministic
4. **Pre-tokenization** — split on whitespace first; prevents cross-word merges
5. **Special tokens** — add [PAD], [BOS], [EOS], [UNK] after BPE training'''
    ),
    (
        "ai/tokenizer-training",
        "Show how to train custom tokenizers with HuggingFace tokenizers library: BPE, WordPiece, and Unigram with normalization and post-processing.",
        '''Training custom tokenizers:

```python
from tokenizers import Tokenizer, models, trainers, pre_tokenizers, processors, normalizers, decoders


def train_bpe_tokenizer(
    files: list[str],
    vocab_size: int = 32000,
    min_frequency: int = 2,
    special_tokens: list[str] = None,
) -> Tokenizer:
    """Train BPE tokenizer with HuggingFace tokenizers (Rust backend)."""
    special_tokens = special_tokens or [
        "<pad>", "<s>", "</s>", "<unk>", "<mask>",
    ]

    tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))

    # Normalization: Unicode NFC + lowercase (optional)
    tokenizer.normalizer = normalizers.Sequence([
        normalizers.NFC(),
        normalizers.Replace(r"\\s+", " "),
        normalizers.Strip(),
    ])

    # Pre-tokenization: split on whitespace and punctuation
    tokenizer.pre_tokenizer = pre_tokenizers.Sequence([
        pre_tokenizers.ByteLevel(add_prefix_space=True),
    ])

    # Trainer
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=min_frequency,
        special_tokens=special_tokens,
        show_progress=True,
    )

    # Train from files
    tokenizer.train(files, trainer)

    # Post-processing: add BOS/EOS tokens
    tokenizer.post_processor = processors.TemplateProcessing(
        single="<s> $A </s>",
        pair="<s> $A </s> <s> $B </s>",
        special_tokens=[("<s>", 1), ("</s>", 2)],
    )

    # Decoder
    tokenizer.decoder = decoders.ByteLevel()

    return tokenizer


def train_unigram_tokenizer(
    files: list[str],
    vocab_size: int = 32000,
) -> Tokenizer:
    """Train SentencePiece-style Unigram tokenizer."""
    tokenizer = Tokenizer(models.Unigram())

    tokenizer.normalizer = normalizers.Sequence([
        normalizers.NFC(),
        normalizers.Replace(r"\\s+", " "),
    ])

    tokenizer.pre_tokenizer = pre_tokenizers.Metaspace(replacement="▁")

    trainer = trainers.UnigramTrainer(
        vocab_size=vocab_size,
        special_tokens=["<pad>", "<s>", "</s>", "<unk>"],
        unk_token="<unk>",
    )

    tokenizer.train(files, trainer)
    tokenizer.decoder = decoders.Metaspace(replacement="▁")

    return tokenizer


def analyze_tokenizer(tokenizer: Tokenizer, test_texts: list[str]):
    """Analyze tokenizer quality metrics."""
    total_chars = 0
    total_tokens = 0
    unk_count = 0
    unk_id = tokenizer.token_to_id("<unk>")

    for text in test_texts:
        encoded = tokenizer.encode(text)
        total_chars += len(text)
        total_tokens += len(encoded.ids)
        unk_count += encoded.ids.count(unk_id) if unk_id is not None else 0

    compression = total_chars / total_tokens
    unk_rate = unk_count / total_tokens if total_tokens > 0 else 0

    return {
        "compression_ratio": compression,
        "avg_token_length": compression,
        "unk_rate": unk_rate,
        "vocab_utilization": len(set(
            id for text in test_texts for id in tokenizer.encode(text).ids
        )) / tokenizer.get_vocab_size(),
    }
```

Key patterns:
1. **Byte-level BPE** — operate on bytes; handles any language without unknown characters
2. **SentencePiece Unigram** — probabilistic model; prunes from large initial vocab to target size
3. **Normalization** — NFC Unicode normalization, whitespace cleanup; consistent tokenization
4. **Pre-tokenization** — split before BPE training; ByteLevel or Metaspace (▁ for spaces)
5. **Compression ratio** — good tokenizer: 3-5 chars per token; measure quality across languages'''
    ),
    (
        "ai/prompt-templating",
        "Show prompt engineering patterns: template systems, few-shot formatting, system prompt design, and structured prompt composition.",
        '''Prompt engineering and templating:

```python
from dataclasses import dataclass, field
from typing import Any, Optional
import json


@dataclass
class Message:
    role: str  # system, user, assistant
    content: str


class PromptTemplate:
    """Composable prompt template with variable substitution."""

    def __init__(self, template: str, required_vars: list[str] = None):
        self.template = template
        self.required_vars = required_vars or []

    def render(self, **kwargs) -> str:
        for var in self.required_vars:
            if var not in kwargs:
                raise ValueError(f"Missing required variable: {var}")
        return self.template.format(**kwargs)


class FewShotBuilder:
    """Build few-shot prompts with example selection."""

    def __init__(self, task_description: str):
        self.task = task_description
        self.examples: list[dict] = []

    def add_example(self, input_text: str, output_text: str, **metadata):
        self.examples.append({
            "input": input_text,
            "output": output_text,
            **metadata,
        })

    def build(self, query: str, n_examples: int = 3,
              format: str = "chat") -> list[Message]:
        """Build few-shot prompt with selected examples."""
        selected = self.examples[:n_examples]  # Simple: first N

        if format == "chat":
            messages = [Message("system", self.task)]
            for ex in selected:
                messages.append(Message("user", ex["input"]))
                messages.append(Message("assistant", ex["output"]))
            messages.append(Message("user", query))
            return messages
        else:
            # Text format
            prompt = f"{self.task}\\n\\n"
            for ex in selected:
                prompt += f"Input: {ex['input']}\\nOutput: {ex['output']}\\n\\n"
            prompt += f"Input: {query}\\nOutput:"
            return [Message("user", prompt)]


class SystemPromptBuilder:
    """Build structured system prompts."""

    def __init__(self):
        self.sections: dict[str, str] = {}

    def set_role(self, role: str):
        self.sections["role"] = f"You are {role}."
        return self

    def set_task(self, task: str):
        self.sections["task"] = f"Your task: {task}"
        return self

    def add_rules(self, rules: list[str]):
        formatted = "\\n".join(f"- {r}" for r in rules)
        self.sections["rules"] = f"Rules:\\n{formatted}"
        return self

    def set_output_format(self, format_desc: str, example: str = None):
        section = f"Output format: {format_desc}"
        if example:
            section += f"\\n\\nExample output:\\n{example}"
        self.sections["format"] = section
        return self

    def add_context(self, context: str):
        self.sections["context"] = f"Context:\\n{context}"
        return self

    def build(self) -> str:
        order = ["role", "task", "context", "rules", "format"]
        parts = [self.sections[k] for k in order if k in self.sections]
        return "\\n\\n".join(parts)


class PromptChain:
    """Chain multiple prompts for multi-step reasoning."""

    def __init__(self, llm_fn):
        self.llm_fn = llm_fn
        self.steps: list[dict] = []

    def add_step(self, name: str, template: PromptTemplate,
                 output_key: str = None):
        self.steps.append({
            "name": name,
            "template": template,
            "output_key": output_key or name,
        })
        return self

    def run(self, initial_vars: dict) -> dict:
        context = dict(initial_vars)
        for step in self.steps:
            prompt = step["template"].render(**context)
            result = self.llm_fn(prompt)
            context[step["output_key"]] = result
        return context
```

Key patterns:
1. **Template composition** — reusable prompt templates with variable substitution
2. **Few-shot formatting** — structured examples before the actual query; chat format preferred
3. **System prompt structure** — role → task → context → rules → output format; clear sections
4. **Prompt chaining** — multi-step: output of step N feeds into step N+1
5. **Output specification** — explicit format instructions with examples reduce parsing errors'''
    ),
]
"""
