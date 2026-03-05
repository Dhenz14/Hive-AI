"""Contrastive and metric learning — SimCLR, triplet loss, hard negative mining."""

PAIRS = [
    (
        "ai/simclr-contrastive",
        "Show SimCLR contrastive learning: data augmentation, NT-Xent loss, projection head, and linear evaluation protocol.",
        '''SimCLR contrastive learning framework:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms, models
from torch.utils.data import DataLoader


class SimCLR(nn.Module):
    """Simple Contrastive Learning of Representations.

    Two augmented views of the same image should have similar
    embeddings, while different images should have different ones.
    """

    def __init__(self, backbone: str = "resnet50", projection_dim: int = 128,
                 hidden_dim: int = 2048):
        super().__init__()
        # Encoder (frozen after pretraining, fine-tuned for downstream)
        resnet = getattr(models, backbone)(weights=None)
        self.encoder = nn.Sequential(*list(resnet.children())[:-1])  # Remove FC
        self.feature_dim = resnet.fc.in_features

        # Projection head (MLP, discarded after pretraining)
        self.projector = nn.Sequential(
            nn.Linear(self.feature_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, projection_dim),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        features = self.encoder(x).squeeze(-1).squeeze(-1)  # [B, feature_dim]
        projections = self.projector(features)  # [B, projection_dim]
        return features, F.normalize(projections, dim=-1)


def nt_xent_loss(z_i: torch.Tensor, z_j: torch.Tensor,
                 temperature: float = 0.5) -> torch.Tensor:
    """Normalized Temperature-scaled Cross-Entropy (NT-Xent) loss.

    Positive pair: (z_i[k], z_j[k]) — two views of same image
    Negative pairs: all other combinations in the batch
    """
    batch_size = z_i.shape[0]
    z = torch.cat([z_i, z_j], dim=0)  # [2B, D]

    # Similarity matrix
    sim = torch.mm(z, z.t()) / temperature  # [2B, 2B]

    # Mask out self-similarity (diagonal)
    mask = torch.eye(2 * batch_size, device=z.device, dtype=torch.bool)
    sim = sim.masked_fill(mask, float("-inf"))

    # Positive pairs: (i, i+B) and (i+B, i)
    pos_i = torch.arange(batch_size, device=z.device)
    pos_j = pos_i + batch_size
    labels = torch.cat([pos_j, pos_i])  # [2B]

    return F.cross_entropy(sim, labels)


# === Data augmentation pipeline ===

def get_simclr_augmentations(image_size: int = 224) -> transforms.Compose:
    """Strong augmentations for contrastive learning."""
    return transforms.Compose([
        transforms.RandomResizedCrop(image_size, scale=(0.2, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomApply([
            transforms.ColorJitter(0.8, 0.8, 0.8, 0.2)
        ], p=0.8),
        transforms.RandomGrayscale(p=0.2),
        transforms.RandomApply([
            transforms.GaussianBlur(kernel_size=23, sigma=(0.1, 2.0))
        ], p=0.5),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


class ContrastiveDataset:
    """Dataset that returns two augmented views of each image."""

    def __init__(self, base_dataset, transform):
        self.dataset = base_dataset
        self.transform = transform

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        image, _ = self.dataset[idx]  # Ignore label during pretraining
        view1 = self.transform(image)
        view2 = self.transform(image)
        return view1, view2


# === Training loop ===

def train_simclr(model: SimCLR, dataloader: DataLoader,
                 epochs: int = 100, lr: float = 3e-4, temperature: float = 0.5):
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    for epoch in range(epochs):
        total_loss = 0
        for view1, view2 in dataloader:
            view1, view2 = view1.cuda(), view2.cuda()

            _, z1 = model(view1)
            _, z2 = model(view2)

            loss = nt_xent_loss(z1, z2, temperature)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        scheduler.step()
        print(f"Epoch {epoch}: loss={total_loss/len(dataloader):.4f}")


# === Linear evaluation protocol ===

class LinearEvaluator(nn.Module):
    """Evaluate encoder quality: freeze encoder, train linear classifier."""

    def __init__(self, encoder: nn.Module, feature_dim: int, num_classes: int):
        super().__init__()
        self.encoder = encoder
        for param in self.encoder.parameters():
            param.requires_grad = False  # Freeze encoder
        self.classifier = nn.Linear(feature_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            features = self.encoder(x).squeeze(-1).squeeze(-1)
        return self.classifier(features)
```

Key patterns:
1. **NT-Xent loss** — treat all other images in batch as negatives; larger batch = more negatives = better representations
2. **Projection head** — MLP projects features to contrastive space; discarded after pretraining (features are better)
3. **Strong augmentations** — random crop + color jitter + blur creates diverse views; model learns invariance
4. **Temperature** — lower T (0.1) makes loss focus on hard negatives; higher T (1.0) is more uniform
5. **Linear evaluation** — freeze encoder, train linear classifier; measures representation quality without fine-tuning'''
    ),
    (
        "ai/triplet-metric-learning",
        "Show metric learning patterns: triplet loss, hard negative mining, Matryoshka embeddings, and retrieval evaluation.",
        '''Metric learning for embeddings and retrieval:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from dataclasses import dataclass


# === Triplet Loss with Mining ===

class TripletLoss(nn.Module):
    """Triplet loss: anchor closer to positive than negative by margin.

    L = max(0, d(anchor, positive) - d(anchor, negative) + margin)
    """

    def __init__(self, margin: float = 0.3):
        super().__init__()
        self.margin = margin

    def forward(self, anchor: torch.Tensor, positive: torch.Tensor,
                negative: torch.Tensor) -> torch.Tensor:
        pos_dist = F.pairwise_distance(anchor, positive)
        neg_dist = F.pairwise_distance(anchor, negative)
        loss = F.relu(pos_dist - neg_dist + self.margin)
        return loss.mean()


class OnlineTripletMiner:
    """Mine hard/semi-hard triplets from batch.

    Hard negative: closest negative to anchor
    Semi-hard: farther than positive but within margin
    """

    def __init__(self, margin: float = 0.3, strategy: str = "semi-hard"):
        self.margin = margin
        self.strategy = strategy

    def mine(self, embeddings: torch.Tensor, labels: torch.Tensor) -> tuple:
        dist_matrix = torch.cdist(embeddings, embeddings, p=2)  # [B, B]
        batch_size = embeddings.shape[0]

        anchors, positives, negatives = [], [], []

        for i in range(batch_size):
            # Positive: same label, different index
            pos_mask = (labels == labels[i]) & (torch.arange(batch_size, device=labels.device) != i)
            # Negative: different label
            neg_mask = labels != labels[i]

            if not pos_mask.any() or not neg_mask.any():
                continue

            pos_dists = dist_matrix[i][pos_mask]
            neg_dists = dist_matrix[i][neg_mask]

            # Hardest positive (farthest)
            hardest_pos_idx = pos_mask.nonzero()[pos_dists.argmax()]

            if self.strategy == "hard":
                # Hardest negative (closest)
                hardest_neg_idx = neg_mask.nonzero()[neg_dists.argmin()]
            elif self.strategy == "semi-hard":
                # Semi-hard: farther than positive but within margin
                pos_dist = pos_dists.max()
                semi_hard_mask = (neg_dists > pos_dist) & (neg_dists < pos_dist + self.margin)
                if semi_hard_mask.any():
                    semi_hard_dists = neg_dists[semi_hard_mask]
                    hardest_neg_idx = neg_mask.nonzero()[semi_hard_mask.nonzero()[semi_hard_dists.argmin()]]
                else:
                    hardest_neg_idx = neg_mask.nonzero()[neg_dists.argmin()]

            anchors.append(i)
            positives.append(hardest_pos_idx.item())
            negatives.append(hardest_neg_idx.item())

        return (
            embeddings[anchors],
            embeddings[positives],
            embeddings[negatives],
        )


# === Matryoshka Representation Learning (MRL) ===

class MatryoshkaEmbedding(nn.Module):
    """Train embeddings that work at multiple dimensions.

    Full embedding: 768 dims (highest quality)
    Truncated: 256, 128, 64, 32 dims (progressively lower quality, faster search)
    Like Russian nesting dolls — each prefix is a valid embedding.
    """

    def __init__(self, backbone: nn.Module, feature_dim: int,
                 matryoshka_dims: list[int] = [32, 64, 128, 256, 768]):
        super().__init__()
        self.backbone = backbone
        self.matryoshka_dims = sorted(matryoshka_dims)
        self.projection = nn.Linear(feature_dim, max(matryoshka_dims))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone(x)
        return F.normalize(self.projection(features), dim=-1)

    def training_loss(self, batch: dict, temperature: float = 0.05) -> torch.Tensor:
        """Compute contrastive loss at each Matryoshka dimension."""
        query_emb = self(batch["query"])
        doc_emb = self(batch["document"])

        total_loss = torch.tensor(0.0, device=query_emb.device)

        for dim in self.matryoshka_dims:
            # Truncate to this dimension
            q = F.normalize(query_emb[:, :dim], dim=-1)
            d = F.normalize(doc_emb[:, :dim], dim=-1)

            # InfoNCE loss at this dimension
            sim = torch.mm(q, d.t()) / temperature
            labels = torch.arange(sim.shape[0], device=sim.device)
            loss = F.cross_entropy(sim, labels)

            # Weight: higher dimensions contribute more
            weight = dim / max(self.matryoshka_dims)
            total_loss += weight * loss

        return total_loss / len(self.matryoshka_dims)

    def encode(self, x: torch.Tensor, dim: int | None = None) -> torch.Tensor:
        """Encode with optional dimension truncation."""
        emb = self(x)
        if dim is not None and dim < emb.shape[-1]:
            emb = F.normalize(emb[:, :dim], dim=-1)
        return emb


# === Retrieval Evaluation ===

def evaluate_retrieval(
    query_embeddings: np.ndarray,
    doc_embeddings: np.ndarray,
    relevance: list[set[int]],  # relevance[i] = set of relevant doc indices for query i
    k_values: list[int] = [1, 5, 10, 20],
) -> dict[str, float]:
    """Evaluate retrieval quality with standard IR metrics."""
    # Compute similarity matrix
    sims = query_embeddings @ doc_embeddings.T  # [Q, D]

    metrics = {}

    for k in k_values:
        recalls = []
        precisions = []
        aps = []

        for i in range(len(query_embeddings)):
            top_k_indices = np.argsort(-sims[i])[:k]
            relevant = relevance[i]

            hits = len(set(top_k_indices) & relevant)
            recalls.append(hits / len(relevant) if relevant else 0)
            precisions.append(hits / k)

            # Average Precision
            ap = 0
            num_relevant = 0
            for rank, idx in enumerate(top_k_indices):
                if idx in relevant:
                    num_relevant += 1
                    ap += num_relevant / (rank + 1)
            aps.append(ap / min(len(relevant), k) if relevant else 0)

        metrics[f"recall@{k}"] = np.mean(recalls)
        metrics[f"precision@{k}"] = np.mean(precisions)
        metrics[f"map@{k}"] = np.mean(aps)

    # NDCG@10
    ndcgs = []
    for i in range(len(query_embeddings)):
        top_indices = np.argsort(-sims[i])[:10]
        dcg = sum(
            (1.0 if idx in relevance[i] else 0.0) / np.log2(rank + 2)
            for rank, idx in enumerate(top_indices)
        )
        ideal_dcg = sum(1.0 / np.log2(rank + 2) for rank in range(min(len(relevance[i]), 10)))
        ndcgs.append(dcg / ideal_dcg if ideal_dcg > 0 else 0)
    metrics["ndcg@10"] = np.mean(ndcgs)

    return metrics
```

Metric learning comparison:

| Loss | Pairs needed | Training stability | Quality |
|------|-------------|-------------------|---------|
| **Contrastive (SimCLR)** | In-batch negatives | Good (large batch) | Excellent |
| **Triplet** | Anchor-pos-neg | Needs mining | Good |
| **InfoNCE** | In-batch | Best | Excellent |
| **Multiple Negatives Ranking** | Pos pairs only | Stable | Great |
| **Matryoshka** | Same as base | Stable | Flexible dims |

Key patterns:
1. **Hard negative mining** — select negatives that are close to the anchor; easy negatives waste gradient
2. **Semi-hard negatives** — negatives farther than positive but within margin; more stable than hardest negatives
3. **Matryoshka** — train at multiple truncation dimensions; use shorter embeddings for fast retrieval, full for reranking
4. **In-batch negatives** — use all other examples in the batch as negatives; O(B²) pairs from B examples
5. **NDCG** — discounted cumulative gain accounts for rank position; standard metric for retrieval quality'''
    ),
]
