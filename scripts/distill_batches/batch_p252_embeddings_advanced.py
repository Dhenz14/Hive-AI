"""Advanced embeddings — sentence transformers, fine-tuning, multi-modal embeddings."""

PAIRS = [
    (
        "ai/sentence-embeddings",
        "Show sentence embedding patterns: bi-encoder architecture, training with contrastive loss, and efficient similarity search.",
        '''Sentence embeddings for semantic search:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
import numpy as np


class SentenceEncoder(nn.Module):
    """Bi-encoder for sentence embeddings (sentence-transformers style)."""

    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5", pooling: str = "cls"):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.pooling = pooling

    def encode(self, texts: list[str], batch_size: int = 32, normalize: bool = True) -> np.ndarray:
        """Encode texts to embeddings."""
        all_embeddings = []
        self.eval()

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            encoded = self.tokenizer(
                batch, padding=True, truncation=True,
                max_length=512, return_tensors="pt",
            )

            with torch.no_grad():
                outputs = self.encoder(**encoded)
                embeddings = self._pool(outputs, encoded["attention_mask"])
                if normalize:
                    embeddings = F.normalize(embeddings, dim=1)
                all_embeddings.append(embeddings.cpu().numpy())

        return np.concatenate(all_embeddings, axis=0)

    def _pool(self, outputs, attention_mask: torch.Tensor) -> torch.Tensor:
        hidden = outputs.last_hidden_state

        if self.pooling == "cls":
            return hidden[:, 0]
        elif self.pooling == "mean":
            mask = attention_mask.unsqueeze(-1).float()
            return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        elif self.pooling == "max":
            hidden[attention_mask == 0] = -1e9
            return hidden.max(dim=1).values

    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        return self._pool(outputs, attention_mask)


class ContrastiveTrainer:
    """Fine-tune sentence encoder with contrastive learning."""

    def __init__(self, model: SentenceEncoder, temperature: float = 0.05):
        self.model = model
        self.temperature = temperature

    def info_nce_loss(self, anchor_emb: torch.Tensor, positive_emb: torch.Tensor) -> torch.Tensor:
        """InfoNCE loss: pull anchor-positive together, push anchor-negative apart.

        In-batch negatives: other samples in the batch serve as negatives.
        """
        # Normalize
        anchor_emb = F.normalize(anchor_emb, dim=1)
        positive_emb = F.normalize(positive_emb, dim=1)

        # Similarity matrix
        sim = torch.mm(anchor_emb, positive_emb.t()) / self.temperature

        # Labels: diagonal (positive pairs)
        labels = torch.arange(sim.shape[0], device=sim.device)

        # Cross-entropy: correct positive should have highest similarity
        return F.cross_entropy(sim, labels)

    def hard_negative_loss(self, anchor_emb, positive_emb, negative_emb, margin: float = 0.2):
        """Triplet loss with hard negatives."""
        pos_sim = F.cosine_similarity(anchor_emb, positive_emb)
        neg_sim = F.cosine_similarity(anchor_emb, negative_emb)
        loss = F.relu(neg_sim - pos_sim + margin)
        return loss.mean()

    def train_step(self, anchors: list[str], positives: list[str], optimizer):
        """One training step with in-batch negatives."""
        self.model.train()
        tokenizer = self.model.tokenizer

        anchor_enc = tokenizer(anchors, padding=True, truncation=True, max_length=512, return_tensors="pt")
        pos_enc = tokenizer(positives, padding=True, truncation=True, max_length=512, return_tensors="pt")

        anchor_emb = self.model(anchor_enc["input_ids"], anchor_enc["attention_mask"])
        pos_emb = self.model(pos_enc["input_ids"], pos_enc["attention_mask"])

        loss = self.info_nce_loss(anchor_emb, pos_emb)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        return loss.item()


class EmbeddingIndex:
    """Efficient similarity search with HNSW index."""

    def __init__(self, dim: int):
        self.dim = dim
        self.embeddings: list[np.ndarray] = []
        self.metadata: list[dict] = []

    def add(self, embeddings: np.ndarray, metadata: list[dict]):
        for emb, meta in zip(embeddings, metadata):
            self.embeddings.append(emb)
            self.metadata.append(meta)

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> list[dict]:
        """Brute-force search (use FAISS/Annoy for production)."""
        if not self.embeddings:
            return []

        db = np.stack(self.embeddings)
        query = query_embedding.reshape(1, -1)

        # Cosine similarity (embeddings already normalized)
        similarities = (query @ db.T).squeeze()
        top_indices = np.argsort(similarities)[::-1][:top_k]

        return [
            {**self.metadata[i], "score": float(similarities[i])}
            for i in top_indices
        ]
```

Embedding model comparison:

| Model | Dim | MTEB score | Speed |
|-------|-----|-----------|-------|
| **bge-base-en-v1.5** | 768 | 63.5 | Fast |
| **e5-large-v2** | 1024 | 62.3 | Medium |
| **GTE-large** | 1024 | 63.1 | Medium |
| **Cohere embed-v3** | 1024 | 64.5 | API |
| **Voyage-3** | 1024 | 67.1 | API |

Key patterns:
1. **Bi-encoder** — encode query and documents independently; enables precomputation
2. **In-batch negatives** — other batch samples serve as negatives; efficient contrastive training
3. **Mean pooling** — average token embeddings weighted by attention mask; generally best for similarity
4. **Normalization** — L2 normalize embeddings so cosine similarity = dot product
5. **Temperature** — lower temperature in InfoNCE sharpens similarity distribution'''
    ),
    (
        "ai/embedding-fine-tuning",
        "Show embedding model fine-tuning: domain adaptation, mining hard negatives, and evaluation with information retrieval metrics.",
        '''Embedding fine-tuning for domain-specific search:

```python
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModel, AutoTokenizer
import numpy as np
import random


class TripletDataset(Dataset):
    """Dataset of (query, positive, hard_negative) triplets."""

    def __init__(self, triplets: list[dict], tokenizer, max_length: int = 256):
        self.triplets = triplets
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.triplets)

    def __getitem__(self, idx):
        t = self.triplets[idx]
        return {
            "query": self.tokenizer(t["query"], max_length=self.max_length,
                                     truncation=True, padding="max_length", return_tensors="pt"),
            "positive": self.tokenizer(t["positive"], max_length=self.max_length,
                                        truncation=True, padding="max_length", return_tensors="pt"),
            "negative": self.tokenizer(t["negative"], max_length=self.max_length,
                                        truncation=True, padding="max_length", return_tensors="pt"),
        }


class HardNegativeMiner:
    """Mine hard negatives from existing corpus."""

    def __init__(self, encoder, corpus_embeddings: np.ndarray, corpus_texts: list[str]):
        self.encoder = encoder
        self.corpus_emb = corpus_embeddings
        self.corpus_texts = corpus_texts

    def mine(self, queries: list[str], positives: list[str],
             top_k: int = 10, min_rank: int = 5) -> list[dict]:
        """Find hard negatives: similar to query but NOT the positive.

        Hard negatives are documents that are close to the query in
        embedding space but are not actually relevant.
        """
        query_embs = self.encoder.encode(queries)
        pos_set = set(positives)

        triplets = []
        similarities = query_embs @ self.corpus_emb.T

        for i, (query, positive) in enumerate(zip(queries, positives)):
            # Get top-k similar documents
            top_indices = np.argsort(similarities[i])[::-1]

            # Find hard negatives (rank 5+ that aren't the positive)
            negatives = []
            for idx in top_indices[min_rank:min_rank + top_k]:
                candidate = self.corpus_texts[idx]
                if candidate != positive and candidate not in pos_set:
                    negatives.append(candidate)
                    break

            if negatives:
                triplets.append({
                    "query": query,
                    "positive": positive,
                    "negative": negatives[0],
                })

        return triplets


class EmbeddingEvaluator:
    """Evaluate embeddings with IR metrics."""

    def __init__(self, encoder):
        self.encoder = encoder

    def evaluate(self, queries: list[str], relevant_docs: list[list[str]],
                 corpus: list[str]) -> dict:
        """Compute retrieval metrics."""
        query_embs = self.encoder.encode(queries)
        corpus_embs = self.encoder.encode(corpus)

        metrics = {"mrr@10": [], "ndcg@10": [], "recall@10": [], "recall@100": []}

        for i, (q_emb, rels) in enumerate(zip(query_embs, relevant_docs)):
            similarities = q_emb @ corpus_embs.T
            ranked_indices = np.argsort(similarities)[::-1]
            ranked_docs = [corpus[idx] for idx in ranked_indices]

            rel_set = set(rels)

            # MRR@10: reciprocal rank of first relevant doc
            mrr = 0
            for rank, doc in enumerate(ranked_docs[:10], 1):
                if doc in rel_set:
                    mrr = 1.0 / rank
                    break
            metrics["mrr@10"].append(mrr)

            # NDCG@10
            dcg = sum(
                1.0 / np.log2(rank + 2) for rank, doc in enumerate(ranked_docs[:10])
                if doc in rel_set
            )
            ideal_dcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(rels), 10)))
            metrics["ndcg@10"].append(dcg / max(ideal_dcg, 1e-10))

            # Recall@k
            for k in [10, 100]:
                found = sum(1 for doc in ranked_docs[:k] if doc in rel_set)
                metrics[f"recall@{k}"].append(found / max(len(rels), 1))

        return {k: np.mean(v) for k, v in metrics.items()}


def fine_tune_embeddings(
    model_name: str,
    triplets: list[dict],
    epochs: int = 3,
    lr: float = 2e-5,
    batch_size: int = 16,
    temperature: float = 0.05,
):
    """Fine-tune embedding model on domain-specific data."""
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).cuda()

    dataset = TripletDataset(triplets, tokenizer)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    for epoch in range(epochs):
        total_loss = 0
        for batch in loader:
            # Encode all three
            def encode(tokens):
                ids = tokens["input_ids"].squeeze(1).cuda()
                mask = tokens["attention_mask"].squeeze(1).cuda()
                out = model(input_ids=ids, attention_mask=mask)
                emb = out.last_hidden_state[:, 0]  # CLS pooling
                return F.normalize(emb, dim=1)

            q_emb = encode(batch["query"])
            p_emb = encode(batch["positive"])
            n_emb = encode(batch["negative"])

            # InfoNCE with hard negatives
            pos_sim = (q_emb * p_emb).sum(dim=1) / temperature
            neg_sim = (q_emb * n_emb).sum(dim=1) / temperature

            # In-batch negatives + explicit hard negative
            all_pos = torch.mm(q_emb, p_emb.t()) / temperature
            labels = torch.arange(q_emb.shape[0]).cuda()
            loss = F.cross_entropy(all_pos, labels)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()

        print(f"Epoch {epoch}: Loss={total_loss/len(loader):.4f}")
```

Key patterns:
1. **Hard negative mining** — find documents similar to query but irrelevant; most informative for training
2. **MRR/NDCG metrics** — standard IR metrics; MRR for single answer, NDCG for ranked lists
3. **Temperature scaling** — lower temperature sharpens similarity; 0.05 is common for contrastive
4. **In-batch + hard negatives** — combine random in-batch negatives with mined hard negatives
5. **Domain adaptation** — fine-tune on domain triplets; typically 3-5 epochs with low learning rate'''
    ),
    (
        "ai/multimodal-embeddings",
        "Show multimodal embedding patterns: CLIP-style joint image-text embeddings, cross-modal retrieval, and late interaction models.",
        '''Multimodal embeddings for cross-modal retrieval:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import CLIPModel, CLIPProcessor, CLIPTokenizer
from PIL import Image
import numpy as np


class MultimodalEmbedder:
    """CLIP-based multimodal embeddings for text and images."""

    def __init__(self, model_name: str = "openai/clip-vit-large-patch14"):
        self.model = CLIPModel.from_pretrained(model_name)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.model.eval()

    @torch.no_grad()
    def encode_text(self, texts: list[str], normalize: bool = True) -> np.ndarray:
        inputs = self.processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        embeddings = self.model.get_text_features(**inputs)
        if normalize:
            embeddings = F.normalize(embeddings, dim=1)
        return embeddings.cpu().numpy()

    @torch.no_grad()
    def encode_images(self, images: list[Image.Image], normalize: bool = True) -> np.ndarray:
        inputs = self.processor(images=images, return_tensors="pt")
        embeddings = self.model.get_image_features(**inputs)
        if normalize:
            embeddings = F.normalize(embeddings, dim=1)
        return embeddings.cpu().numpy()

    def cross_modal_search(self, query_text: str, image_embeddings: np.ndarray,
                           top_k: int = 5) -> list[int]:
        """Find images matching text query."""
        text_emb = self.encode_text([query_text])
        similarities = (text_emb @ image_embeddings.T).squeeze()
        return np.argsort(similarities)[::-1][:top_k].tolist()


class LateInteractionModel(nn.Module):
    """ColBERT-style late interaction for fine-grained matching.

    Instead of single vector per document, keep all token embeddings.
    Query-document score = sum of max similarities per query token.
    """

    def __init__(self, encoder_name: str = "bert-base-uncased", dim: int = 128):
        super().__init__()
        from transformers import AutoModel
        self.encoder = AutoModel.from_pretrained(encoder_name)
        self.linear = nn.Linear(self.encoder.config.hidden_size, dim)

    def encode(self, input_ids, attention_mask):
        """Encode to per-token embeddings."""
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        token_embs = self.linear(outputs.last_hidden_state)
        return F.normalize(token_embs, dim=-1)

    def score(self, query_embs: torch.Tensor, doc_embs: torch.Tensor,
              query_mask: torch.Tensor, doc_mask: torch.Tensor) -> torch.Tensor:
        """MaxSim: for each query token, find max similarity to any doc token.

        Score = sum over query tokens of max similarity to document tokens.
        """
        # [B, Q, D] x [B, D, T] -> [B, Q, T]
        sim = torch.bmm(query_embs, doc_embs.transpose(1, 2))

        # Mask padding tokens in document
        doc_mask_expanded = doc_mask.unsqueeze(1).float()
        sim = sim * doc_mask_expanded + (1 - doc_mask_expanded) * (-1e9)

        # Max similarity per query token, then sum
        max_sim = sim.max(dim=2).values  # [B, Q]
        max_sim = max_sim * query_mask.float()

        return max_sim.sum(dim=1)  # [B]
```

Embedding architecture comparison:

| Architecture | Vectors per doc | Search speed | Precision |
|-------------|----------------|-------------|-----------|
| **Bi-encoder** | 1 | Very fast | Good |
| **Cross-encoder** | N/A (pair input) | Slow | Best |
| **ColBERT (late interaction)** | N (per token) | Medium | Very good |
| **CLIP** | 1 (multimodal) | Very fast | Good |

Key patterns:
1. **Joint embedding space** — CLIP maps text and images to same vector space; enables cross-modal search
2. **Late interaction (ColBERT)** — per-token embeddings with MaxSim scoring; better than single-vector
3. **Contrastive pre-training** — CLIP trained on 400M image-text pairs with InfoNCE loss
4. **Cross-modal retrieval** — search images with text queries (or vice versa) in shared embedding space
5. **Token-level matching** — MaxSim captures fine-grained term-level relevance'''
    ),
]
"""
