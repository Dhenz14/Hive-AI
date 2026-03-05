"""Data augmentation and synthetic data — text augmentation, image augmentation, data mixing."""

PAIRS = [
    (
        "ai/text-augmentation",
        "Show text data augmentation for NLP: back-translation, synonym replacement, contextual augmentation with LLMs, and EDA techniques.",
        '''Text augmentation for NLP training data:

```python
import random
import re
from typing import Optional
from anthropic import Anthropic


class TextAugmenter:
    """Text augmentation techniques for NLP data expansion."""

    def __init__(self, llm_model: str = "claude-haiku-4-5-20251001"):
        self.client = Anthropic()
        self.model = llm_model

    # === Easy Data Augmentation (EDA) ===

    def synonym_replacement(self, text: str, n: int = 2) -> str:
        """Replace n random words with synonyms."""
        words = text.split()
        if len(words) < 3:
            return text

        # Simple synonym map (use WordNet in production)
        synonyms = {
            "good": ["great", "excellent", "fine"],
            "bad": ["poor", "terrible", "awful"],
            "big": ["large", "huge", "enormous"],
            "small": ["tiny", "little", "compact"],
            "fast": ["quick", "rapid", "swift"],
            "slow": ["sluggish", "gradual", "leisurely"],
        }

        for _ in range(n):
            idx = random.randint(0, len(words) - 1)
            word_lower = words[idx].lower()
            if word_lower in synonyms:
                words[idx] = random.choice(synonyms[word_lower])

        return " ".join(words)

    def random_insertion(self, text: str, n: int = 1) -> str:
        """Insert n random words at random positions."""
        words = text.split()
        filler_words = ["also", "moreover", "indeed", "certainly", "actually"]
        for _ in range(n):
            pos = random.randint(0, len(words))
            words.insert(pos, random.choice(filler_words))
        return " ".join(words)

    def random_swap(self, text: str, n: int = 1) -> str:
        """Swap n pairs of adjacent words."""
        words = text.split()
        for _ in range(n):
            if len(words) >= 2:
                idx = random.randint(0, len(words) - 2)
                words[idx], words[idx + 1] = words[idx + 1], words[idx]
        return " ".join(words)

    def random_deletion(self, text: str, p: float = 0.1) -> str:
        """Delete each word with probability p."""
        words = text.split()
        if len(words) <= 1:
            return text
        remaining = [w for w in words if random.random() > p]
        return " ".join(remaining) if remaining else words[0]

    # === LLM-based Augmentation ===

    def paraphrase(self, text: str) -> str:
        """Use LLM to paraphrase while preserving meaning."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Paraphrase this text in a different way while preserving the exact meaning. Only output the paraphrase, nothing else.\\n\\nText: {text}",
            }],
        )
        return response.content[0].text.strip()

    def style_transfer(self, text: str, style: str) -> str:
        """Rewrite text in a different style."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Rewrite this text in a {style} style while keeping the same core meaning. Only output the rewrite.\\n\\nText: {text}",
            }],
        )
        return response.content[0].text.strip()

    def generate_similar(self, text: str, label: str, n: int = 3) -> list[str]:
        """Generate n new examples similar to the input with same label."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"Generate {n} new text examples that would have the label '{label}', similar in style and content to the example below but with different wording and details. Output as JSON array.\\n\\nExample: {text}",
            }],
        )
        import json
        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return [text]

    def augment_batch(self, texts: list[str], labels: list[str],
                       multiplier: int = 3) -> tuple[list[str], list[str]]:
        """Augment a batch of labeled texts."""
        aug_texts, aug_labels = list(texts), list(labels)

        for text, label in zip(texts, labels):
            methods = [
                self.synonym_replacement,
                self.random_swap,
                lambda t: self.random_deletion(t, 0.1),
            ]
            for _ in range(multiplier - 1):
                method = random.choice(methods)
                aug_texts.append(method(text))
                aug_labels.append(label)

        return aug_texts, aug_labels
```

Augmentation comparison:

| Method | Quality | Speed | Cost |
|--------|---------|-------|------|
| **Synonym replacement** | Low | Fast | Free |
| **Random swap/delete** | Low | Fast | Free |
| **Back-translation** | Medium | Medium | API cost |
| **LLM paraphrase** | High | Slow | API cost |
| **LLM generation** | Highest | Slow | API cost |

Key patterns:
1. **EDA techniques** — synonym replacement, random insertion/swap/deletion; simple but effective
2. **LLM paraphrase** — high-quality augmentation; preserves meaning while varying surface form
3. **Style transfer** — generate formal/informal/technical variants of same content
4. **Label-conditioned generation** — generate new examples with specific labels for balancing
5. **Multiplier** — typical 3-5x augmentation; diminishing returns beyond that'''
    ),
    (
        "ai/image-augmentation",
        "Show image augmentation for computer vision: geometric transforms, color augmentation, CutMix/MixUp, and augmentation policies.",
        '''Image augmentation for computer vision:

```python
import torch
import torch.nn.functional as F
import torchvision.transforms.v2 as T
import numpy as np
from typing import Optional


class StandardAugmentation:
    """Standard augmentation pipeline for image classification."""

    @staticmethod
    def train_transform(img_size: int = 224):
        return T.Compose([
            T.RandomResizedCrop(img_size, scale=(0.08, 1.0)),
            T.RandomHorizontalFlip(p=0.5),
            T.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.1),
            T.RandomGrayscale(p=0.2),
            T.GaussianBlur(kernel_size=23, sigma=(0.1, 2.0)),
            T.ToImage(),
            T.ToDtype(torch.float32, scale=True),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    @staticmethod
    def val_transform(img_size: int = 224):
        return T.Compose([
            T.Resize(int(img_size * 1.14)),
            T.CenterCrop(img_size),
            T.ToImage(),
            T.ToDtype(torch.float32, scale=True),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])


def cutmix(images: torch.Tensor, labels: torch.Tensor,
           alpha: float = 1.0) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    """CutMix: cut and paste patches between training images.

    Regularizes by forcing model to learn from partial information.
    Better than Cutout (which just masks with zeros).
    """
    batch_size = images.shape[0]
    indices = torch.randperm(batch_size)

    # Sample lambda from Beta distribution
    lam = np.random.beta(alpha, alpha)

    # Generate random bounding box
    H, W = images.shape[2], images.shape[3]
    cut_ratio = np.sqrt(1 - lam)
    cut_h = int(H * cut_ratio)
    cut_w = int(W * cut_ratio)

    cx = np.random.randint(W)
    cy = np.random.randint(H)

    x1 = np.clip(cx - cut_w // 2, 0, W)
    y1 = np.clip(cy - cut_h // 2, 0, H)
    x2 = np.clip(cx + cut_w // 2, 0, W)
    y2 = np.clip(cy + cut_h // 2, 0, H)

    # Paste patch from shuffled images
    mixed_images = images.clone()
    mixed_images[:, :, y1:y2, x1:x2] = images[indices, :, y1:y2, x1:x2]

    # Adjust lambda to actual area ratio
    lam = 1 - (x2 - x1) * (y2 - y1) / (H * W)

    return mixed_images, labels, labels[indices], lam


def mixup(images: torch.Tensor, labels: torch.Tensor,
          alpha: float = 0.2) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    """MixUp: linear interpolation between pairs of images and labels.

    Creates virtual training examples between class boundaries.
    """
    batch_size = images.shape[0]
    indices = torch.randperm(batch_size)
    lam = np.random.beta(alpha, alpha)

    mixed_images = lam * images + (1 - lam) * images[indices]
    return mixed_images, labels, labels[indices], lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    """Mixed loss for MixUp/CutMix training."""
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


class RandAugment:
    """RandAugment: random selection from augmentation pool.

    Simple yet effective: randomly apply N transforms with magnitude M.
    No search needed (unlike AutoAugment).
    """

    def __init__(self, n_ops: int = 2, magnitude: int = 9):
        self.n_ops = n_ops
        self.magnitude = magnitude
        self.ops = [
            "rotate", "shear_x", "shear_y", "translate_x", "translate_y",
            "brightness", "contrast", "saturation", "sharpness",
            "posterize", "solarize", "equalize", "auto_contrast",
        ]

    def __call__(self, img):
        """Apply N random augmentations."""
        selected = np.random.choice(self.ops, self.n_ops, replace=False)
        for op_name in selected:
            # Apply with probability 0.5
            if np.random.random() > 0.5:
                img = self._apply_op(img, op_name, self.magnitude)
        return img

    def _apply_op(self, img, op_name: str, magnitude: int):
        """Apply a single augmentation operation."""
        # Magnitude-dependent parameters (simplified)
        m = magnitude / 10.0  # Normalize to [0, 1]

        ops_map = {
            "rotate": lambda: T.RandomRotation(degrees=int(30 * m)),
            "brightness": lambda: T.ColorJitter(brightness=m),
            "contrast": lambda: T.ColorJitter(contrast=m),
            "sharpness": lambda: T.RandomAdjustSharpness(sharpness_factor=1 + m),
        }

        if op_name in ops_map:
            transform = ops_map[op_name]()
            return transform(img)
        return img
```

Key patterns:
1. **CutMix** — paste patches between images; forces model to identify objects from partial views
2. **MixUp** — linear interpolation of images and labels; smooths decision boundaries
3. **RandAugment** — randomly apply N transforms at magnitude M; simple, no search needed
4. **Mixed criterion** — `lam * loss(y_a) + (1-lam) * loss(y_b)` for CutMix/MixUp training
5. **Train vs val transforms** — aggressive augmentation only during training; clean resize+crop for eval'''
    ),
    (
        "ai/data-mixing",
        "Show training data mixing strategies: curriculum learning, data weighting, domain mixing ratios, and quality filtering for LLM pre-training.",
        '''Data mixing for LLM pre-training:

```python
import numpy as np
from dataclasses import dataclass, field
from typing import Iterator
import torch
from torch.utils.data import IterableDataset


@dataclass
class DataSource:
    name: str
    path: str
    weight: float  # Sampling weight
    quality_threshold: float = 0.5
    max_tokens: int | None = None  # Token budget
    tokens_seen: int = 0


class DataMixer(IterableDataset):
    """Mix multiple data sources with configurable ratios.

    Controls the mixture of web data, code, books, papers, etc.
    during LLM pre-training.
    """

    def __init__(self, sources: list[DataSource], seed: int = 42):
        self.sources = sources
        self.rng = np.random.RandomState(seed)

        # Normalize weights
        total = sum(s.weight for s in sources)
        self.probabilities = [s.weight / total for s in sources]

    def __iter__(self) -> Iterator:
        """Yield samples from sources according to mixing weights."""
        source_iters = {s.name: self._iter_source(s) for s in self.sources}

        while True:
            # Sample source according to weights
            source = self.rng.choice(self.sources, p=self.probabilities)

            # Check token budget
            if source.max_tokens and source.tokens_seen >= source.max_tokens:
                # Redistribute weight
                self._redistribute_weight(source)
                continue

            try:
                sample = next(source_iters[source.name])
                source.tokens_seen += sample.get("n_tokens", 1)
                yield sample
            except StopIteration:
                # Source exhausted, redistribute weight
                self._redistribute_weight(source)

    def _iter_source(self, source: DataSource):
        """Iterate over a data source with quality filtering."""
        # Placeholder: in practice, read from sharded files
        import json
        with open(source.path) as f:
            for line in f:
                sample = json.loads(line)
                # Quality filtering
                if sample.get("quality_score", 1.0) >= source.quality_threshold:
                    yield sample

    def _redistribute_weight(self, exhausted: DataSource):
        """Redistribute weight from exhausted source to others."""
        exhausted.weight = 0
        total = sum(s.weight for s in self.sources)
        if total > 0:
            self.probabilities = [s.weight / total for s in self.sources]


# === Chinchilla-Optimal Mixing ===

CHINCHILLA_MIX = {
    "web_filtered": 0.45,   # Common Crawl (quality filtered)
    "code": 0.20,           # GitHub/StackOverflow
    "books": 0.15,          # Books corpus
    "academic": 0.10,       # ArXiv, papers
    "wikipedia": 0.05,      # Wikipedia
    "conversations": 0.05,  # Dialog data
}


class CurriculumScheduler:
    """Adjust data mixing ratios during training.

    Start with easy/clean data, gradually introduce harder/noisier data.
    """

    def __init__(self, sources: list[DataSource], total_steps: int):
        self.sources = sources
        self.total_steps = total_steps
        self.initial_weights = {s.name: s.weight for s in sources}

    def get_weights(self, step: int) -> dict[str, float]:
        """Adjust weights based on training progress."""
        progress = step / self.total_steps

        weights = {}
        for source in self.sources:
            base_weight = self.initial_weights[source.name]

            # Curriculum: increase code/academic weight over time
            if source.name in ("code", "academic"):
                weights[source.name] = base_weight * (0.5 + 0.5 * progress)
            elif source.name == "web_filtered":
                weights[source.name] = base_weight * (1.5 - 0.5 * progress)
            else:
                weights[source.name] = base_weight

        # Normalize
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}


class QualityFilter:
    """Filter training data by quality signals."""

    def __init__(self, min_length: int = 50, max_length: int = 100000):
        self.min_length = min_length
        self.max_length = max_length

    def filter(self, text: str) -> tuple[bool, float]:
        """Return (keep, quality_score) for a document."""
        # Length check
        if len(text) < self.min_length or len(text) > self.max_length:
            return False, 0.0

        # Repetition check
        lines = text.split("\\n")
        unique_lines = set(lines)
        if len(unique_lines) / max(len(lines), 1) < 0.5:
            return False, 0.1

        # Character ratio (detect garbled text)
        alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
        if alpha_ratio < 0.4:
            return False, 0.2

        # Compute quality score (simplified)
        quality = min(1.0, (
            0.3 * alpha_ratio +
            0.3 * (len(unique_lines) / max(len(lines), 1)) +
            0.2 * min(len(text) / 1000, 1.0) +
            0.2 * (1.0 if not self._has_boilerplate(text) else 0.3)
        ))

        return quality >= 0.5, quality

    def _has_boilerplate(self, text: str) -> bool:
        boilerplate = ["cookie policy", "terms of service", "subscribe to our",
                       "click here", "all rights reserved"]
        text_lower = text.lower()
        return any(bp in text_lower for bp in boilerplate)
```

Key patterns:
1. **Weighted mixing** — sample from sources by weight; controls domain representation
2. **Quality filtering** — length, repetition, character ratio checks; remove low-quality documents
3. **Curriculum learning** — start with clean data, gradually add harder/noisier data
4. **Token budgets** — cap tokens per source to prevent overrepresentation
5. **Chinchilla ratios** — empirically optimal mix: ~45% web, ~20% code, ~15% books'''
    ),
]
