"""Recommendation systems — collaborative filtering, content-based, and hybrid approaches."""

PAIRS = [
    (
        "ai/collaborative-filtering",
        "Show collaborative filtering patterns: user-based, item-based, matrix factorization, and implicit feedback.",
        '''Collaborative filtering for recommendations:

```python
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity


# === Matrix Factorization (SVD-style) ===

class MatrixFactorization(nn.Module):
    """Learn latent user and item embeddings that reconstruct ratings.

    Rating prediction: r_hat(u, i) = mu + b_u + b_i + p_u @ q_i
    """

    def __init__(self, num_users: int, num_items: int, embedding_dim: int = 64):
        super().__init__()
        self.user_embeddings = nn.Embedding(num_users, embedding_dim)
        self.item_embeddings = nn.Embedding(num_items, embedding_dim)
        self.user_bias = nn.Embedding(num_users, 1)
        self.item_bias = nn.Embedding(num_items, 1)
        self.global_bias = nn.Parameter(torch.zeros(1))

        # Initialize with small values
        nn.init.normal_(self.user_embeddings.weight, std=0.01)
        nn.init.normal_(self.item_embeddings.weight, std=0.01)
        nn.init.zeros_(self.user_bias.weight)
        nn.init.zeros_(self.item_bias.weight)

    def forward(self, user_ids: torch.Tensor, item_ids: torch.Tensor) -> torch.Tensor:
        user_emb = self.user_embeddings(user_ids)
        item_emb = self.item_embeddings(item_ids)

        # Dot product + biases
        dot = (user_emb * item_emb).sum(dim=-1)
        prediction = (
            self.global_bias
            + self.user_bias(user_ids).squeeze(-1)
            + self.item_bias(item_ids).squeeze(-1)
            + dot
        )
        return prediction

    def recommend(self, user_id: int, top_k: int = 10,
                  exclude_items: set[int] | None = None) -> list[tuple[int, float]]:
        """Get top-K recommendations for a user."""
        user_emb = self.user_embeddings(torch.tensor([user_id]))
        all_items = torch.arange(self.item_embeddings.num_embeddings)
        all_item_emb = self.item_embeddings(all_items)

        scores = (user_emb * all_item_emb).sum(dim=-1)
        scores += self.user_bias(torch.tensor([user_id])).squeeze()
        scores += self.item_bias(all_items).squeeze()
        scores += self.global_bias

        if exclude_items:
            for item_id in exclude_items:
                scores[item_id] = float("-inf")

        top_scores, top_indices = scores.topk(top_k)
        return list(zip(top_indices.tolist(), top_scores.tolist()))


# === Implicit Feedback (BPR Loss) ===

class BPRLoss(nn.Module):
    """Bayesian Personalized Ranking for implicit feedback.

    Instead of predicting ratings, learn to rank:
    items the user interacted with > items they didn't.
    """

    def forward(self, pos_scores: torch.Tensor, neg_scores: torch.Tensor) -> torch.Tensor:
        return -F.logsigmoid(pos_scores - neg_scores).mean()


def train_implicit_mf(model: MatrixFactorization, interactions: list[tuple[int, int]],
                       num_items: int, epochs: int = 20, lr: float = 0.01):
    """Train with BPR on implicit feedback (clicks, views, purchases)."""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    bpr_loss = BPRLoss()
    user_items = {}
    for u, i in interactions:
        user_items.setdefault(u, set()).add(i)

    for epoch in range(epochs):
        total_loss = 0
        np.random.shuffle(interactions)

        for user_id, pos_item_id in interactions:
            # Negative sampling: random item the user hasn't interacted with
            neg_item_id = np.random.randint(0, num_items)
            while neg_item_id in user_items.get(user_id, set()):
                neg_item_id = np.random.randint(0, num_items)

            users = torch.tensor([user_id])
            pos_items = torch.tensor([pos_item_id])
            neg_items = torch.tensor([neg_item_id])

            pos_score = model(users, pos_items)
            neg_score = model(users, neg_items)

            loss = bpr_loss(pos_score, neg_score)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        print(f"Epoch {epoch}: loss={total_loss/len(interactions):.4f}")


# === Two-Tower Model (scalable retrieval) ===

class TwoTowerModel(nn.Module):
    """Separate user and item towers for scalable retrieval.

    At serving time:
    1. Precompute all item embeddings (offline)
    2. Compute user embedding (online)
    3. ANN search for nearest items (fast)
    """

    def __init__(self, user_feature_dim: int, item_feature_dim: int,
                 embedding_dim: int = 128):
        super().__init__()
        self.user_tower = nn.Sequential(
            nn.Linear(user_feature_dim, 256),
            nn.ReLU(),
            nn.BatchNorm1d(256),
            nn.Linear(256, embedding_dim),
        )
        self.item_tower = nn.Sequential(
            nn.Linear(item_feature_dim, 256),
            nn.ReLU(),
            nn.BatchNorm1d(256),
            nn.Linear(256, embedding_dim),
        )
        self.temperature = nn.Parameter(torch.tensor(0.07))

    def forward(self, user_features: torch.Tensor,
                item_features: torch.Tensor) -> torch.Tensor:
        user_emb = F.normalize(self.user_tower(user_features), dim=-1)
        item_emb = F.normalize(self.item_tower(item_features), dim=-1)

        # In-batch sampled softmax
        logits = torch.mm(user_emb, item_emb.t()) / self.temperature.exp()
        return logits

    def get_user_embedding(self, user_features: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.user_tower(user_features), dim=-1)

    def get_item_embedding(self, item_features: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.item_tower(item_features), dim=-1)
```

Key patterns:
1. **Matrix factorization** — decompose user-item matrix into low-rank embeddings; dot product predicts ratings
2. **BPR loss** — for implicit feedback: positive items should score higher than random negatives
3. **Two-tower** — separate user/item encoders enable precomputing item embeddings for fast ANN retrieval
4. **Negative sampling** — randomly sample items the user hasn't seen as negative examples; ratio 1:4 common
5. **In-batch negatives** — use other users' positive items as negatives within the batch; efficient training'''
    ),
    (
        "ai/ranking-reranking",
        "Show recommendation ranking patterns: two-stage retrieval+ranking, learning to rank, and cross-encoder reranking.",
        '''Two-stage recommendation: retrieval then ranking:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from dataclasses import dataclass


# === Stage 1: Candidate Retrieval (fast, recall-focused) ===

class CandidateRetriever:
    """Fast candidate retrieval using ANN search.

    Retrieve top-1000 candidates from millions of items in < 10ms.
    Uses precomputed item embeddings + HNSW index.
    """

    def __init__(self, item_embeddings: np.ndarray):
        import faiss

        dim = item_embeddings.shape[1]
        self.index = faiss.IndexHNSWFlat(dim, 32)  # HNSW graph
        self.index.hnsw.efConstruction = 200
        self.index.add(item_embeddings.astype(np.float32))

        # Set search-time parameters
        self.index.hnsw.efSearch = 128

    def retrieve(self, user_embedding: np.ndarray, top_k: int = 1000) -> tuple:
        """Retrieve top-K candidates by embedding similarity."""
        scores, indices = self.index.search(
            user_embedding.reshape(1, -1).astype(np.float32), top_k
        )
        return indices[0], scores[0]


# === Stage 2: Ranking Model (accurate, precision-focused) ===

class RankingModel(nn.Module):
    """Cross-feature ranking model for candidate scoring.

    Takes user features + item features + context features
    and predicts engagement probability.

    Much more expressive than dot-product retrieval,
    but too expensive to run on all items.
    """

    def __init__(self, user_dim: int = 64, item_dim: int = 64,
                 context_dim: int = 32, hidden_dim: int = 256):
        super().__init__()
        input_dim = user_dim + item_dim + context_dim

        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.BatchNorm1d(hidden_dim),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.BatchNorm1d(hidden_dim),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
        )

        # Multi-task heads
        self.click_head = nn.Linear(hidden_dim // 2, 1)   # P(click)
        self.purchase_head = nn.Linear(hidden_dim // 2, 1) # P(purchase)
        self.dwell_head = nn.Linear(hidden_dim // 2, 1)    # Expected dwell time

    def forward(self, user_features: torch.Tensor, item_features: torch.Tensor,
                context_features: torch.Tensor) -> dict[str, torch.Tensor]:
        combined = torch.cat([user_features, item_features, context_features], dim=-1)
        hidden = self.network(combined)

        return {
            "click_prob": torch.sigmoid(self.click_head(hidden)).squeeze(-1),
            "purchase_prob": torch.sigmoid(self.purchase_head(hidden)).squeeze(-1),
            "dwell_time": F.softplus(self.dwell_head(hidden)).squeeze(-1),
        }

    def compute_score(self, predictions: dict) -> torch.Tensor:
        """Combine multi-task predictions into single ranking score."""
        return (
            0.3 * predictions["click_prob"]
            + 0.5 * predictions["purchase_prob"]
            + 0.2 * torch.log1p(predictions["dwell_time"]) / 5
        )


# === ListWise Learning to Rank (ListNet) ===

class ListNetLoss(nn.Module):
    """ListNet: listwise learning to rank.

    Treats ranking as a distribution matching problem.
    """

    def forward(self, predicted_scores: torch.Tensor,
                relevance_labels: torch.Tensor) -> torch.Tensor:
        # Convert scores to probability distributions
        pred_probs = F.softmax(predicted_scores, dim=-1)
        true_probs = F.softmax(relevance_labels.float(), dim=-1)

        # KL divergence between true and predicted ranking distributions
        return F.kl_div(pred_probs.log(), true_probs, reduction="batchmean")


# === Diversity and Exploration ===

def diversify_recommendations(
    items: list[dict],
    scores: list[float],
    category_key: str = "category",
    diversity_weight: float = 0.3,
    top_k: int = 20,
) -> list[dict]:
    """MMR-style diversification: balance relevance and diversity.

    Maximal Marginal Relevance ensures the final list isn't
    all the same type of item.
    """
    selected = []
    remaining = list(range(len(items)))

    while len(selected) < top_k and remaining:
        best_idx = None
        best_score = float("-inf")

        for idx in remaining:
            relevance = scores[idx]

            # Diversity: penalty for similarity to already-selected items
            diversity_penalty = 0
            if selected:
                same_category = sum(
                    1 for s in selected
                    if items[s].get(category_key) == items[idx].get(category_key)
                )
                diversity_penalty = same_category / len(selected)

            mmr_score = (1 - diversity_weight) * relevance - diversity_weight * diversity_penalty

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        selected.append(best_idx)
        remaining.remove(best_idx)

    return [items[i] for i in selected]


# === Full Pipeline ===

class RecommendationPipeline:
    """Production recommendation pipeline."""

    def __init__(self, retriever: CandidateRetriever, ranker: RankingModel):
        self.retriever = retriever
        self.ranker = ranker

    def recommend(self, user_embedding: np.ndarray, user_features: torch.Tensor,
                  context: torch.Tensor, items_db: list[dict],
                  top_k: int = 20) -> list[dict]:
        # Stage 1: Retrieve 1000 candidates (< 10ms)
        candidate_ids, retrieval_scores = self.retriever.retrieve(user_embedding, 1000)

        # Stage 2: Rank candidates with full model (< 50ms)
        candidate_features = torch.stack([
            torch.tensor(items_db[i]["features"]) for i in candidate_ids
        ])
        user_batch = user_features.unsqueeze(0).expand(len(candidate_ids), -1)
        context_batch = context.unsqueeze(0).expand(len(candidate_ids), -1)

        with torch.no_grad():
            predictions = self.ranker(user_batch, candidate_features, context_batch)
            scores = self.ranker.compute_score(predictions)

        # Stage 3: Diversify and return top-K
        candidates = [items_db[i] for i in candidate_ids]
        return diversify_recommendations(candidates, scores.tolist(), top_k=top_k)
```

Two-stage pipeline:
```
All Items (millions) → ANN Retrieval (~1000) → Ranking Model (~100) → Diversification (~20) → User
      ↓                      ↓                       ↓                       ↓
  Precomputed           < 10ms                   < 50ms                  < 5ms
  embeddings          (dot product)        (cross-features)          (MMR penalty)
```

Key patterns:
1. **Two-stage** — fast retrieval (ANN, dot product) narrows candidates; expensive ranker scores the shortlist
2. **Multi-task ranking** — predict click, purchase, dwell time simultaneously; combine with business weights
3. **ListNet** — listwise loss treats ranking as distribution matching (better than pointwise/pairwise)
4. **MMR diversification** — penalize items similar to already-selected ones; prevents monotonous feeds
5. **ANN index (HNSW)** — approximate nearest neighbor search over millions of items in < 10ms'''
    ),
]
"""
