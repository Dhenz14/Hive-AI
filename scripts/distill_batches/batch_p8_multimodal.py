"""
Batch P8 — Multimodal AI Systems
Covers: VLMs/CLIP, multimodal fusion, diffusion models, audio/speech AI, document understanding.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "multimodal/vision-language-models-clip-contrastive-training",
        "Explain vision-language model architectures including CLIP contrastive pre-training, visual encoders like ViT and SigLIP, text-image alignment mechanisms, and zero-shot classification, then implement a complete CLIP-style contrastive training loop in PyTorch with image and text encoders, learned projection heads, temperature-scaled InfoNCE loss, and evaluation utilities.",
        r"""# Vision-Language Models: CLIP Architecture and Contrastive Pre-Training

## Introduction to Vision-Language Models

**Vision-Language Models (VLMs)** represent a paradigm shift in how we build AI systems that understand both images and text simultaneously. Before VLMs, computer vision and natural language processing were treated as isolated disciplines with separate datasets, training regimes, and evaluation benchmarks. CLIP (Contrastive Language-Image Pre-training), introduced by OpenAI in 2021, demonstrated that **jointly training** visual and textual encoders on massive image-text pairs produces representations that generalize remarkably well to downstream tasks — often without any task-specific fine-tuning.

The core motivation behind CLIP is straightforward: rather than training a vision model on a fixed set of categories (e.g., ImageNet's 1000 classes), we train it to associate images with their **natural language descriptions**. This is powerful because natural language provides an essentially infinite label space, therefore the model can recognize concepts it has never been explicitly trained on by simply matching images to novel text prompts at inference time. This capability is called **zero-shot transfer**.

**Common mistake**: Assuming VLMs "understand" images the way humans do. In reality, they learn statistical correlations between visual patterns and textual tokens. This distinction matters because it explains failure modes like typographic attacks (text overlaid on images can override visual content) and compositionality failures (confusing "a cat on a dog" with "a dog on a cat").

## Visual Encoders: ViT, SigLIP, and Beyond

### Vision Transformer (ViT)

The **Vision Transformer** treats an image as a sequence of patches. An image of size 224x224 is divided into 16x16 patches, producing 196 tokens (each patch is 16x16 pixels). Each patch is linearly embedded into a vector, prepended with a learnable `[CLS]` token, and processed through standard transformer encoder layers. The `[CLS]` token's final representation serves as the global image embedding.

**Best practice**: Use patch sizes of 14 or 16 for a good trade-off between granularity and computational cost. Smaller patches (e.g., 8x8) produce 4x more tokens, which quadratically increases self-attention cost. However, smaller patches capture finer details and typically yield better accuracy when compute permits.

### SigLIP: Sigmoid Loss for Language-Image Pre-training

SigLIP replaces the softmax-based InfoNCE loss with a **sigmoid loss** that operates on individual image-text pairs independently. This is significant because it removes the need for the all-pairs similarity matrix computation, enabling training on larger batch sizes more efficiently. The sigmoid formulation treats each pair as a binary classification: "does this image match this text?" Therefore, it scales better than CLIP's contrastive loss as batch size grows.

**Pitfall**: SigLIP requires careful calibration of the bias term in the sigmoid. Without proper initialization, the model can collapse to predicting all pairs as negative (or positive), because the loss surface has trivial minima at extreme bias values.

### Text-Image Alignment

Both CLIP and SigLIP project image and text representations into a **shared embedding space** using learned linear projection heads. The key constraint is that matched image-text pairs should have high cosine similarity while unmatched pairs should have low similarity. The temperature parameter controls the sharpness of this distribution — lower temperature makes the model more discriminative but risks training instability.

## Contrastive Pre-Training Mechanics

### InfoNCE Loss

The InfoNCE loss (also called NT-Xent or normalized temperature-scaled cross-entropy) treats contrastive learning as a classification problem. Given a batch of N image-text pairs, for each image, the matching text is the positive and the remaining N-1 texts are negatives. The loss is symmetric: we compute it for both image-to-text and text-to-image directions.

**Key insight**: The effective number of negatives is the batch size minus one. Therefore, CLIP used extremely large batch sizes (32,768) because more negatives provide a harder contrastive signal, forcing the model to learn finer-grained distinctions. This is a critical trade-off: larger batches improve representation quality but require more GPU memory and careful learning rate scaling.

### Zero-Shot Classification

At inference time, zero-shot classification works by:
1. Encoding the input image through the visual encoder
2. Creating text prompts for each candidate class (e.g., "a photo of a {class}")
3. Computing cosine similarity between the image embedding and each text embedding
4. Selecting the class with highest similarity

**Best practice**: Use prompt engineering (e.g., "a photo of a {class}, a type of pet") and prompt ensembling (averaging embeddings from multiple templates) to improve zero-shot accuracy by 3-5 percentage points.

## Complete CLIP-Style Training Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from typing import Tuple, Optional, List, Dict
import math

# ---- Patch Embedding for Vision Transformer ----

class PatchEmbedding(nn.Module):
    # Converts image into sequence of patch embeddings

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        in_channels: int = 3,
        embed_dim: int = 768,
    ) -> None:
        super().__init__()
        self.num_patches = (img_size // patch_size) ** 2
        self.proj = nn.Conv2d(
            in_channels, embed_dim,
            kernel_size=patch_size, stride=patch_size
        )
        self.cls_token = nn.Parameter(torch.randn(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(
            torch.randn(1, self.num_patches + 1, embed_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, H, W) -> (B, num_patches+1, embed_dim)
        B = x.shape[0]
        x = self.proj(x)  # (B, embed_dim, H', W')
        x = x.flatten(2).transpose(1, 2)  # (B, num_patches, embed_dim)
        cls_tokens = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls_tokens, x], dim=1)
        x = x + self.pos_embed
        return x


class TransformerBlock(nn.Module):
    # Standard transformer encoder block with pre-norm

    def __init__(self, embed_dim: int, num_heads: int, mlp_ratio: float = 4.0) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(embed_dim)
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(embed_dim)
        hidden_dim = int(embed_dim * mlp_ratio)
        self.mlp = nn.Sequential(
            nn.Linear(embed_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, embed_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Pre-norm residual connections
        normed = self.norm1(x)
        attn_out, _ = self.attn(normed, normed, normed)
        x = x + attn_out
        x = x + self.mlp(self.norm2(x))
        return x


class VisionEncoder(nn.Module):
    # ViT-based image encoder for CLIP

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        embed_dim: int = 768,
        depth: int = 12,
        num_heads: int = 12,
    ) -> None:
        super().__init__()
        self.patch_embed = PatchEmbedding(img_size, patch_size, 3, embed_dim)
        self.blocks = nn.ModuleList([
            TransformerBlock(embed_dim, num_heads) for _ in range(depth)
        ])
        self.norm = nn.LayerNorm(embed_dim)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        # images: (B, 3, H, W) -> (B, embed_dim)
        x = self.patch_embed(images)
        for block in self.blocks:
            x = block(x)
        x = self.norm(x)
        return x[:, 0]  # CLS token as image representation
```

```python
# ---- Text Encoder and CLIP Model ----

class TextEncoder(nn.Module):
    # Transformer-based text encoder for CLIP
    # Uses causal masking and takes final token as representation

    def __init__(
        self,
        vocab_size: int = 49408,
        max_len: int = 77,
        embed_dim: int = 512,
        depth: int = 12,
        num_heads: int = 8,
    ) -> None:
        super().__init__()
        self.token_embed = nn.Embedding(vocab_size, embed_dim)
        self.pos_embed = nn.Parameter(torch.randn(1, max_len, embed_dim))
        self.blocks = nn.ModuleList([
            TransformerBlock(embed_dim, num_heads) for _ in range(depth)
        ])
        self.norm = nn.LayerNorm(embed_dim)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        # input_ids: (B, seq_len) -> (B, embed_dim)
        x = self.token_embed(input_ids) + self.pos_embed[:, :input_ids.shape[1]]
        for block in self.blocks:
            x = block(x)
        x = self.norm(x)
        # Use EOS token (last non-padding token) as text representation
        # Simplified: use last position
        return x[:, -1]


class CLIPModel(nn.Module):
    # Full CLIP model with vision encoder, text encoder, and projection heads

    def __init__(
        self,
        vision_embed_dim: int = 768,
        text_embed_dim: int = 512,
        projection_dim: int = 256,
        img_size: int = 224,
        vocab_size: int = 49408,
        vision_depth: int = 12,
        text_depth: int = 12,
    ) -> None:
        super().__init__()
        self.vision_encoder = VisionEncoder(
            img_size=img_size, embed_dim=vision_embed_dim, depth=vision_depth
        )
        self.text_encoder = TextEncoder(
            vocab_size=vocab_size, embed_dim=text_embed_dim, depth=text_depth
        )
        # Learned projection heads map to shared space
        self.vision_proj = nn.Linear(vision_embed_dim, projection_dim, bias=False)
        self.text_proj = nn.Linear(text_embed_dim, projection_dim, bias=False)
        # Learnable temperature parameter (log scale for stability)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1 / 0.07)))

    def encode_image(self, images: torch.Tensor) -> torch.Tensor:
        features = self.vision_encoder(images)
        projected = self.vision_proj(features)
        return F.normalize(projected, dim=-1)

    def encode_text(self, input_ids: torch.Tensor) -> torch.Tensor:
        features = self.text_encoder(input_ids)
        projected = self.text_proj(features)
        return F.normalize(projected, dim=-1)

    def forward(
        self, images: torch.Tensor, input_ids: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        image_embeds = self.encode_image(images)
        text_embeds = self.encode_text(input_ids)
        # Clamp temperature to prevent instability
        logit_scale = self.logit_scale.exp().clamp(max=100.0)
        # Compute similarity matrix
        logits_per_image = logit_scale * image_embeds @ text_embeds.T
        logits_per_text = logits_per_image.T
        return logits_per_image, logits_per_text, logit_scale
```

```python
# ---- Contrastive Loss and Training Loop ----

def clip_contrastive_loss(
    logits_per_image: torch.Tensor,
    logits_per_text: torch.Tensor,
) -> torch.Tensor:
    # Symmetric InfoNCE loss
    # Each row i should have its maximum at column i (the matching pair)
    batch_size = logits_per_image.shape[0]
    labels = torch.arange(batch_size, device=logits_per_image.device)
    loss_i2t = F.cross_entropy(logits_per_image, labels)
    loss_t2i = F.cross_entropy(logits_per_text, labels)
    return (loss_i2t + loss_t2i) / 2.0


def train_clip_one_epoch(
    model: CLIPModel,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    epoch: int,
    max_grad_norm: float = 1.0,
) -> Dict[str, float]:
    # Train CLIP for one epoch with gradient clipping
    model.train()
    total_loss = 0.0
    num_batches = 0

    for batch_idx, (images, input_ids) in enumerate(dataloader):
        images = images.to(device)
        input_ids = input_ids.to(device)

        logits_img, logits_txt, scale = model(images, input_ids)
        loss = clip_contrastive_loss(logits_img, logits_txt)

        optimizer.zero_grad()
        loss.backward()
        # Gradient clipping prevents explosion from large batch interactions
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()

        total_loss += loss.item()
        num_batches += 1

        if batch_idx % 100 == 0:
            print(
                f"Epoch {epoch} | Batch {batch_idx} | "
                f"Loss: {loss.item():.4f} | Scale: {scale.item():.2f}"
            )

    avg_loss = total_loss / max(num_batches, 1)
    return {"avg_loss": avg_loss, "logit_scale": scale.item()}


@torch.no_grad()
def zero_shot_classify(
    model: CLIPModel,
    images: torch.Tensor,
    class_names: List[str],
    tokenizer_fn,  # callable: str -> tensor of token ids
    device: torch.device,
    templates: Optional[List[str]] = None,
) -> torch.Tensor:
    # Zero-shot classification via text-image similarity
    # Uses prompt ensembling for improved accuracy
    if templates is None:
        templates = [
            "a photo of a {}.",
            "a blurry photo of a {}.",
            "a rendering of a {}.",
            "a photo of the large {}.",
            "a photo of the small {}.",
        ]

    model.eval()
    # Build class embeddings via prompt ensembling
    class_embeddings: List[torch.Tensor] = []
    for class_name in class_names:
        prompts = [t.format(class_name) for t in templates]
        token_ids = torch.stack([tokenizer_fn(p) for p in prompts]).to(device)
        embeddings = model.encode_text(token_ids)
        # Average across templates, then re-normalize
        mean_embed = F.normalize(embeddings.mean(dim=0), dim=-1)
        class_embeddings.append(mean_embed)

    class_matrix = torch.stack(class_embeddings, dim=0)  # (num_classes, proj_dim)
    image_embeds = model.encode_image(images.to(device))  # (B, proj_dim)
    similarities = image_embeds @ class_matrix.T  # (B, num_classes)
    predictions = similarities.argmax(dim=-1)
    return predictions
```

## Summary and Key Takeaways

- **CLIP** aligns visual and textual representations in a shared embedding space using contrastive learning, enabling powerful **zero-shot transfer** to unseen tasks.
- The **InfoNCE loss** treats contrastive learning as symmetric cross-entropy classification, where the batch itself provides negatives. Therefore, larger batch sizes directly improve representation quality.
- **Visual encoders** like ViT process images as patch sequences through transformer layers, while the **text encoder** processes tokenized captions similarly. Both are projected into a shared space via learned linear heads.
- **SigLIP** improves on CLIP by using per-pair sigmoid loss instead of softmax over the full batch, enabling better scaling. However, it requires careful bias initialization to avoid collapse.
- The **temperature parameter** (logit scale) controls discrimination sharpness and is best learned during training with clamping to prevent instability — a critical trade-off between sensitivity and robustness.
- **Zero-shot classification** works by computing similarity between image embeddings and text embeddings of class-name prompts. **Best practice** is to ensemble multiple prompt templates and average their embeddings for 3-5% accuracy gains.
- **Common mistake**: Using small batch sizes for contrastive training. Batch sizes below 256 often lead to poor representations because the model does not encounter enough hard negatives per step.
"""
    ),
    (
        "multimodal/fusion-strategies-cross-attention-gated",
        "Describe and compare multimodal fusion strategies including early fusion, late fusion, cross-attention fusion, gated fusion, and Flamingo-style perceiver resampler, then implement cross-attention and gated multimodal fusion layers in PyTorch for combining vision and language features with full training integration.",
        r"""# Multimodal Fusion Strategies: Cross-Attention, Gated Fusion, and Perceiver Resamplers

## The Fundamental Challenge of Multimodal Fusion

When building systems that process multiple modalities (vision, language, audio, etc.), the central engineering question is: **how and when** do we combine information from different modalities? This decision profoundly impacts model capacity, computational cost, and what kinds of cross-modal interactions the model can learn. The term "fusion" refers to any mechanism that merges representations from two or more modalities into a unified representation.

The trade-off is intuitive: fusing too early may lose modality-specific structure, while fusing too late may miss fine-grained cross-modal correspondences. Therefore, modern architectures often use **multiple fusion points** at different levels of abstraction, combining the benefits of both approaches.

**Common mistake**: Treating fusion as a one-time operation. State-of-the-art models like Flamingo and GPT-4V apply cross-modal attention at multiple layers, because early fusion captures low-level correlations (texture-word associations) while later fusion captures high-level semantics (scene-description alignment).

## Early Fusion

### Architecture and Rationale

In **early fusion**, raw or minimally processed features from all modalities are concatenated and fed into a single shared backbone. For example, image patch tokens and text tokens might be concatenated into a single sequence and processed by a unified transformer.

**Advantage**: The model can learn arbitrary cross-modal interactions from the very first layer, because all information is available simultaneously.

**Pitfall**: Early fusion requires the model to simultaneously learn modality-specific features AND cross-modal associations. This makes optimization harder and requires more data. Additionally, if one modality's tokens vastly outnumber the other's (e.g., 196 image patches vs. 20 text tokens), the model may become biased toward the dominant modality.

### When to Use Early Fusion

Early fusion works best when modalities are naturally aligned (e.g., video frames and synchronized audio) or when you have massive amounts of paired data. Models like VisualBERT and Uniter use early fusion because they pre-train on millions of image-text pairs.

## Late Fusion

### Architecture and Rationale

In **late fusion**, each modality is processed by an independent encoder, and only the final representations are combined — typically via concatenation, element-wise addition, or a small MLP. Each encoder becomes a specialist for its modality.

**Best practice**: When using late fusion, ensure the encoders produce representations of compatible dimensionality and semantic granularity. A 768-dim ViT embedding and a 768-dim BERT embedding may have the same size but very different internal structures. Therefore, always include a learned projection layer before combining them.

**Advantage**: Modular design allows swapping encoders and leveraging pre-trained specialists.

**Disadvantage**: No cross-modal interaction during encoding means the model cannot attend to text while processing the image or vice versa, limiting its ability to resolve ambiguities.

## Cross-Attention Fusion

### How Cross-Attention Works

**Cross-attention** is arguably the most powerful fusion mechanism. One modality's representations serve as queries, while the other modality provides keys and values. This allows each token in the query modality to selectively attend to relevant tokens in the other modality.

For example, in a VQA (visual question answering) model, text tokens query over image patch tokens. The word "red" can attend heavily to image patches containing red objects, creating a targeted cross-modal representation. This is powerful because the attention weights are learned end-to-end and adapt to the specific input.

**Trade-off**: Cross-attention is O(N_q * N_kv) in compute, where N_q is the query sequence length and N_kv is the key-value sequence length. For long sequences, this can be prohibitively expensive. However, the representational power justifies the cost in most multimodal applications.

## Gated Fusion

### The Gating Mechanism

**Gated fusion** uses a learned gate (typically a sigmoid-activated linear layer) to dynamically control how much each modality contributes to the fused representation. The gate is computed from both modalities, allowing the model to decide — on a per-example, per-feature basis — whether to trust the visual or textual signal more.

This is particularly valuable when modalities have **varying reliability**. For example, in a medical imaging report generation system, the visual signal (X-ray) might be highly informative for describing anatomical structures, while the textual signal (patient history) is more informative for contextualizing findings. The gate learns this automatically.

## Flamingo-Style Perceiver Resampler

### Architecture

The **Perceiver Resampler** (from DeepMind's Flamingo) is designed to handle the computational burden of processing high-resolution visual features. It uses a small set of **learned query tokens** (typically 64) that cross-attend to the full set of visual features (potentially thousands of tokens). This compresses the visual information into a fixed-size representation regardless of image resolution.

**Key insight**: The perceiver resampler acts as a learned bottleneck that extracts only the visual information relevant to language modeling. This is a critical design choice because it means the language model never directly attends to raw visual tokens — it only sees the resampled summary. Therefore, the compute cost of the language model is independent of image resolution.

## Implementation: Cross-Attention and Gated Fusion

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple, Dict
import math


class CrossAttentionFusion(nn.Module):
    # Multi-head cross-attention fusion layer
    # Query modality attends to key-value modality
    # Includes residual connection and layer norm

    def __init__(
        self,
        query_dim: int,
        kv_dim: int,
        num_heads: int = 8,
        dropout: float = 0.1,
        proj_dim: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.proj_dim = proj_dim or query_dim
        self.num_heads = num_heads
        self.head_dim = self.proj_dim // num_heads
        assert self.proj_dim % num_heads == 0, "proj_dim must be divisible by num_heads"
        self.scale = self.head_dim ** -0.5

        # Separate projections for Q (from query modality) and K,V (from kv modality)
        self.q_proj = nn.Linear(query_dim, self.proj_dim)
        self.k_proj = nn.Linear(kv_dim, self.proj_dim)
        self.v_proj = nn.Linear(kv_dim, self.proj_dim)
        self.out_proj = nn.Linear(self.proj_dim, query_dim)

        self.norm_q = nn.LayerNorm(query_dim)
        self.norm_kv = nn.LayerNorm(kv_dim)
        self.dropout = nn.Dropout(dropout)

        # Feed-forward after cross-attention
        self.ff_norm = nn.LayerNorm(query_dim)
        self.feed_forward = nn.Sequential(
            nn.Linear(query_dim, query_dim * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(query_dim * 4, query_dim),
            nn.Dropout(dropout),
        )

    def forward(
        self,
        query: torch.Tensor,
        context: torch.Tensor,
        context_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        # query: (B, N_q, query_dim) -- e.g., text tokens
        # context: (B, N_kv, kv_dim) -- e.g., image patch tokens
        # context_mask: (B, N_kv) -- True for valid positions
        B, N_q, _ = query.shape
        N_kv = context.shape[1]

        # Pre-norm
        q = self.q_proj(self.norm_q(query))
        k = self.k_proj(self.norm_kv(context))
        v = self.v_proj(self.norm_kv(context))

        # Reshape for multi-head attention
        q = q.view(B, N_q, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, N_kv, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, N_kv, self.num_heads, self.head_dim).transpose(1, 2)

        # Scaled dot-product attention
        attn_weights = (q @ k.transpose(-2, -1)) * self.scale

        if context_mask is not None:
            mask = context_mask.unsqueeze(1).unsqueeze(2)  # (B, 1, 1, N_kv)
            attn_weights = attn_weights.masked_fill(~mask, float("-inf"))

        attn_weights = F.softmax(attn_weights, dim=-1)
        attn_weights = self.dropout(attn_weights)

        attn_output = (attn_weights @ v).transpose(1, 2).reshape(B, N_q, self.proj_dim)
        attn_output = self.out_proj(attn_output)

        # Residual + feed-forward
        query = query + attn_output
        query = query + self.feed_forward(self.ff_norm(query))
        return query
```

```python
class GatedMultimodalFusion(nn.Module):
    # Gated fusion combines two modalities using a learned sigmoid gate
    # The gate dynamically weights each modality's contribution per feature

    def __init__(
        self,
        dim_vision: int,
        dim_text: int,
        output_dim: int,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        # Project both modalities to same dimensionality
        self.vision_proj = nn.Linear(dim_vision, output_dim)
        self.text_proj = nn.Linear(dim_text, output_dim)

        # Gate computed from concatenation of both modalities
        self.gate_network = nn.Sequential(
            nn.Linear(output_dim * 2, output_dim),
            nn.Sigmoid(),
        )

        self.layer_norm = nn.LayerNorm(output_dim)
        self.dropout = nn.Dropout(dropout)

        # Optional refinement MLP after gating
        self.refine = nn.Sequential(
            nn.Linear(output_dim, output_dim * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(output_dim * 4, output_dim),
        )

    def forward(
        self,
        vision_features: torch.Tensor,
        text_features: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        # vision_features: (B, dim_vision) or (B, N, dim_vision)
        # text_features: (B, dim_text) or (B, N, dim_text)
        # Returns: fused features and gate values for interpretability
        v = self.vision_proj(vision_features)
        t = self.text_proj(text_features)

        # Compute gate from joint representation
        combined = torch.cat([v, t], dim=-1)
        gate = self.gate_network(combined)  # values in [0, 1]

        # gate=1 means "use vision", gate=0 means "use text"
        fused = gate * v + (1.0 - gate) * t
        fused = self.layer_norm(fused)
        fused = fused + self.refine(fused)
        fused = self.dropout(fused)
        return fused, gate


class PerceiverResampler(nn.Module):
    # Flamingo-style perceiver resampler that compresses visual tokens
    # into a fixed number of latent tokens via cross-attention

    def __init__(
        self,
        visual_dim: int = 1024,
        latent_dim: int = 768,
        num_latents: int = 64,
        num_heads: int = 8,
        num_layers: int = 2,
    ) -> None:
        super().__init__()
        self.latents = nn.Parameter(torch.randn(num_latents, latent_dim) * 0.02)
        self.cross_attn_layers = nn.ModuleList([
            CrossAttentionFusion(
                query_dim=latent_dim,
                kv_dim=visual_dim if i == 0 else latent_dim,
                num_heads=num_heads,
            )
            for i in range(num_layers)
        ])
        self.input_proj = nn.Linear(visual_dim, latent_dim)

    def forward(self, visual_tokens: torch.Tensor) -> torch.Tensor:
        # visual_tokens: (B, N_patches, visual_dim)
        # Returns: (B, num_latents, latent_dim) -- compressed representation
        B = visual_tokens.shape[0]
        latents = self.latents.unsqueeze(0).expand(B, -1, -1)
        context = visual_tokens

        for i, layer in enumerate(self.cross_attn_layers):
            if i == 0:
                latents = layer(latents, context)
            else:
                proj_context = self.input_proj(visual_tokens)
                latents = layer(latents, proj_context)
        return latents
```

```python
# ---- Full Training Integration Example ----

class MultimodalClassifier(nn.Module):
    # Combines vision and text with configurable fusion strategy

    def __init__(
        self,
        vision_dim: int = 768,
        text_dim: int = 768,
        num_classes: int = 100,
        fusion_type: str = "gated",
    ) -> None:
        super().__init__()
        self.fusion_type = fusion_type

        if fusion_type == "cross_attention":
            self.fusion = CrossAttentionFusion(
                query_dim=text_dim, kv_dim=vision_dim, num_heads=8
            )
            self.classifier = nn.Linear(text_dim, num_classes)
        elif fusion_type == "gated":
            self.fusion = GatedMultimodalFusion(
                dim_vision=vision_dim, dim_text=text_dim, output_dim=512
            )
            self.classifier = nn.Linear(512, num_classes)
        else:
            raise ValueError(f"Unknown fusion type: {fusion_type}")

    def forward(
        self,
        vision_features: torch.Tensor,
        text_features: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        if self.fusion_type == "cross_attention":
            # text queries attend to vision
            fused = self.fusion(text_features, vision_features)
            # Pool over sequence dimension
            pooled = fused.mean(dim=1)
            logits = self.classifier(pooled)
            return {"logits": logits}
        elif self.fusion_type == "gated":
            fused, gate_values = self.fusion(vision_features, text_features)
            logits = self.classifier(fused)
            return {"logits": logits, "gate_values": gate_values}
        return {}


def train_multimodal_step(
    model: MultimodalClassifier,
    vision_feats: torch.Tensor,
    text_feats: torch.Tensor,
    labels: torch.Tensor,
    optimizer: torch.optim.Optimizer,
) -> Dict[str, float]:
    # Single training step for multimodal classifier
    model.train()
    optimizer.zero_grad()
    outputs = model(vision_feats, text_feats)
    loss = F.cross_entropy(outputs["logits"], labels)
    loss.backward()
    optimizer.step()
    acc = (outputs["logits"].argmax(-1) == labels).float().mean()
    metrics = {"loss": loss.item(), "accuracy": acc.item()}
    if "gate_values" in outputs:
        metrics["mean_gate"] = outputs["gate_values"].mean().item()
    return metrics
```

## Summary and Key Takeaways

- **Early fusion** concatenates modalities before processing, enabling deep cross-modal interaction but requiring more data and compute. It is a **best practice** only when paired training data is abundant.
- **Late fusion** processes modalities independently and combines final representations. This is modular and leverages pre-trained encoders, however it sacrifices fine-grained cross-modal attention.
- **Cross-attention fusion** is the most expressive approach, allowing each token in one modality to selectively attend to the other. The **trade-off** is O(N_q * N_kv) compute cost, but the representational power justifies this in most practical systems.
- **Gated fusion** dynamically weights each modality's contribution via a learned sigmoid gate, which is particularly valuable when modality reliability varies across examples. Therefore, it is the preferred choice for robust multimodal systems.
- The **Perceiver Resampler** (Flamingo) compresses variable-length visual tokens into a fixed set of latent tokens, decoupling the language model's compute from image resolution — a critical efficiency **best practice** for large-scale multimodal LLMs.
- **Common mistake**: Using only one fusion point. Modern architectures apply fusion at multiple layers because different depths capture different levels of cross-modal correspondence.
- **Pitfall**: Forgetting to normalize or project features before fusion. Mismatched scale or dimensionality between modalities leads to one modality dominating, because gradient magnitudes differ.
"""
    ),
    (
        "multimodal/diffusion-models-image-generation",
        "Explain image generation with diffusion models covering the forward and reverse diffusion processes, noise scheduling with linear and cosine schedules, U-Net denoiser architecture, classifier-free guidance mechanism, and DDPM versus DDIM sampling, then implement a simplified diffusion training loop and sampling procedure with classifier-free guidance in PyTorch.",
        r"""# Image Generation with Diffusion Models: From Theory to Implementation

## The Diffusion Framework

**Diffusion models** generate images by learning to reverse a gradual noising process. The intuition is elegant: if we can learn to remove a small amount of noise from an image, we can start from pure noise and iteratively denoise to produce a realistic image. This is fundamentally different from GANs (which learn a direct mapping from noise to images) and VAEs (which learn an encoder-decoder pair).

The framework has two processes: the **forward process** (diffusion) that gradually corrupts data by adding Gaussian noise, and the **reverse process** (denoising) that learns to undo the corruption step by step. Because each individual denoising step only needs to remove a small amount of noise, the learning problem is much easier than generating an image in one shot.

**Common mistake**: Thinking diffusion models are slow because they are fundamentally sequential. While the original DDPM requires hundreds of steps, techniques like DDIM, DPM-Solver, and consistency models have reduced this to as few as 1-4 steps. Therefore, the iterative nature is a training-time conceptual framework, not necessarily an inference-time bottleneck.

## Forward Diffusion Process

### Mathematical Formulation

The forward process defines a Markov chain that adds Gaussian noise over T timesteps. At each step t, we add noise controlled by a **variance schedule** beta_t:

q(x_t | x_{t-1}) = N(x_t; sqrt(1 - beta_t) * x_{t-1}, beta_t * I)

A key mathematical trick allows us to sample x_t directly from x_0 without iterating through all intermediate steps:

q(x_t | x_0) = N(x_t; sqrt(alpha_bar_t) * x_0, (1 - alpha_bar_t) * I)

where alpha_bar_t = product of (1 - beta_s) for s from 1 to t. This "closed-form sampling" is critical for efficient training, because we can jump to any arbitrary timestep directly.

### Noise Schedules

The **noise schedule** determines how quickly information is destroyed during the forward process. This is a critical design choice with significant impact on sample quality.

**Linear schedule**: beta_t increases linearly from beta_1 = 0.0001 to beta_T = 0.02. This was used in the original DDPM paper. However, it destroys information too quickly in the middle timesteps, leading to wasted model capacity.

**Cosine schedule**: Proposed by Nichol and Dhariwal, the cosine schedule ensures alpha_bar_t follows a cosine curve, producing a more gradual and uniform noise injection. This results in better sample quality because the model must learn meaningful denoising at every timestep rather than only at the boundaries.

**Best practice**: Use the cosine schedule for most applications. The linear schedule is only preferred when training stability is a concern (the cosine schedule can cause numerical issues near t=T where alpha_bar_T approaches zero). A common **pitfall** is failing to clip alpha_bar values away from exactly 0 or 1, which causes NaN losses.

## Reverse Process and U-Net Architecture

### The Denoising Network

The reverse process is parameterized by a neural network (typically a **U-Net**) that predicts the noise added at each step. Given a noisy image x_t and the timestep t, the network outputs an estimate of the noise epsilon. The training objective is simply the **mean squared error** between the predicted and actual noise:

L = E[||epsilon - epsilon_theta(x_t, t)||^2]

### U-Net Architecture for Diffusion

The U-Net is the standard backbone because its encoder-decoder structure with skip connections is ideal for dense prediction tasks. Key components include:

- **Timestep embedding**: The timestep t is encoded via sinusoidal positional embeddings and injected into each residual block via addition or FiLM conditioning
- **Residual blocks**: ConvNeXt-style blocks with group normalization and SiLU activation
- **Self-attention**: Applied at lower resolutions (e.g., 16x16, 8x8) where the sequence length is manageable
- **Cross-attention**: For conditioning on text embeddings (used in Stable Diffusion)
- **Downsampling/upsampling**: Strided convolutions and transposed convolutions with skip connections

## Classifier-Free Guidance

### Motivation and Mechanism

**Classifier-free guidance (CFG)** is a technique that dramatically improves sample quality and text adherence without requiring a separate classifier. The key idea is to train a single model both conditionally (with text prompt) and unconditionally (with empty/null prompt), then at inference time, extrapolate in the direction of the conditional prediction.

The guided prediction is: epsilon_guided = epsilon_uncond + w * (epsilon_cond - epsilon_uncond)

where w is the guidance scale. When w > 1, we amplify the difference between conditional and unconditional predictions, pushing the sample more strongly toward the text description. Typical values are w = 7.5 for Stable Diffusion.

**Trade-off**: Higher guidance scale produces more text-faithful but less diverse images. Very high values (w > 15) cause saturation artifacts and loss of fine detail. Therefore, guidance scale is the primary quality-diversity knob during inference.

### DDPM vs. DDIM Sampling

**DDPM** (Denoising Diffusion Probabilistic Models) uses stochastic sampling — each denoising step adds a small amount of random noise, making the process non-deterministic. This requires all T steps for proper sampling.

**DDIM** (Denoising Diffusion Implicit Models) reformulates the reverse process as a deterministic ODE (ordinary differential equation). Because it is deterministic, we can skip timesteps and sample in as few as 20-50 steps while maintaining quality. DDIM also enables **interpolation** in latent space, because the same initial noise always produces the same image.

**Best practice**: Use DDIM for fast inference and latent manipulation; use DDPM with full steps for maximum quality when compute permits.

## Implementation: Diffusion Training and Sampling

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple, Dict
import math


class NoiseScheduler:
    # Manages forward diffusion noise schedules
    # Supports linear and cosine schedules

    def __init__(
        self,
        num_timesteps: int = 1000,
        schedule_type: str = "cosine",
        beta_start: float = 0.0001,
        beta_end: float = 0.02,
        device: torch.device = torch.device("cpu"),
    ) -> None:
        self.num_timesteps = num_timesteps
        self.device = device

        if schedule_type == "linear":
            betas = torch.linspace(beta_start, beta_end, num_timesteps)
        elif schedule_type == "cosine":
            # Cosine schedule from Nichol & Dhariwal
            steps = torch.arange(num_timesteps + 1, dtype=torch.float64)
            alpha_bar = torch.cos(((steps / num_timesteps) + 0.008) / 1.008 * math.pi / 2) ** 2
            alpha_bar = alpha_bar / alpha_bar[0]
            betas = 1 - (alpha_bar[1:] / alpha_bar[:-1])
            betas = betas.clamp(max=0.999).float()
        else:
            raise ValueError(f"Unknown schedule: {schedule_type}")

        self.betas = betas.to(device)
        self.alphas = (1.0 - self.betas).to(device)
        self.alpha_cumprod = torch.cumprod(self.alphas, dim=0).to(device)
        self.alpha_cumprod_prev = F.pad(self.alpha_cumprod[:-1], (1, 0), value=1.0)

        # Pre-compute values needed for q(x_t | x_0)
        self.sqrt_alpha_cumprod = torch.sqrt(self.alpha_cumprod)
        self.sqrt_one_minus_alpha_cumprod = torch.sqrt(1.0 - self.alpha_cumprod)

        # Pre-compute values for posterior q(x_{t-1} | x_t, x_0)
        self.posterior_variance = (
            self.betas * (1.0 - self.alpha_cumprod_prev) / (1.0 - self.alpha_cumprod)
        )

    def add_noise(
        self, x_0: torch.Tensor, noise: torch.Tensor, timesteps: torch.Tensor
    ) -> torch.Tensor:
        # q(x_t | x_0): add noise to clean images at given timesteps
        sqrt_alpha = self.sqrt_alpha_cumprod[timesteps][:, None, None, None]
        sqrt_one_minus_alpha = self.sqrt_one_minus_alpha_cumprod[timesteps][:, None, None, None]
        return sqrt_alpha * x_0 + sqrt_one_minus_alpha * noise

    def get_velocity(
        self, x_0: torch.Tensor, noise: torch.Tensor, timesteps: torch.Tensor
    ) -> torch.Tensor:
        # v-prediction target: v = sqrt(alpha_bar) * noise - sqrt(1-alpha_bar) * x_0
        sqrt_alpha = self.sqrt_alpha_cumprod[timesteps][:, None, None, None]
        sqrt_one_minus_alpha = self.sqrt_one_minus_alpha_cumprod[timesteps][:, None, None, None]
        return sqrt_alpha * noise - sqrt_one_minus_alpha * x_0
```

```python
# ---- Simplified U-Net Denoiser ----

class TimestepEmbedding(nn.Module):
    # Sinusoidal timestep embedding followed by MLP projection

    def __init__(self, dim: int, max_period: int = 10000) -> None:
        super().__init__()
        self.dim = dim
        self.max_period = max_period
        self.mlp = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.SiLU(),
            nn.Linear(dim * 4, dim),
        )

    def forward(self, timesteps: torch.Tensor) -> torch.Tensor:
        half = self.dim // 2
        freqs = torch.exp(
            -math.log(self.max_period)
            * torch.arange(half, device=timesteps.device, dtype=torch.float32)
            / half
        )
        args = timesteps.float()[:, None] * freqs[None, :]
        embedding = torch.cat([torch.cos(args), torch.sin(args)], dim=-1)
        return self.mlp(embedding)


class ResBlock(nn.Module):
    # Residual block with timestep conditioning via addition

    def __init__(self, in_ch: int, out_ch: int, time_dim: int) -> None:
        super().__init__()
        self.norm1 = nn.GroupNorm(8, in_ch)
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.time_proj = nn.Linear(time_dim, out_ch)
        self.norm2 = nn.GroupNorm(8, out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.skip = nn.Conv2d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.act = nn.SiLU()

    def forward(self, x: torch.Tensor, t_emb: torch.Tensor) -> torch.Tensor:
        h = self.act(self.norm1(x))
        h = self.conv1(h)
        # Add timestep embedding
        h = h + self.time_proj(t_emb)[:, :, None, None]
        h = self.act(self.norm2(h))
        h = self.conv2(h)
        return h + self.skip(x)


class SimpleUNet(nn.Module):
    # Simplified U-Net for diffusion denoising
    # Supports optional class conditioning for classifier-free guidance

    def __init__(
        self,
        in_channels: int = 3,
        base_channels: int = 64,
        channel_mults: Tuple[int, ...] = (1, 2, 4, 8),
        time_dim: int = 256,
        num_classes: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.time_embed = TimestepEmbedding(time_dim)
        self.num_classes = num_classes

        if num_classes is not None:
            # Class embedding for conditional generation
            # Index 0 reserved for unconditional (null class)
            self.class_embed = nn.Embedding(num_classes + 1, time_dim)

        # Build encoder (downsampling) path
        self.encoder_blocks = nn.ModuleList()
        self.downsamplers = nn.ModuleList()
        ch = in_channels
        encoder_channels = []

        for mult in channel_mults:
            out_ch = base_channels * mult
            self.encoder_blocks.append(ResBlock(ch, out_ch, time_dim))
            encoder_channels.append(out_ch)
            self.downsamplers.append(nn.Conv2d(out_ch, out_ch, 3, stride=2, padding=1))
            ch = out_ch

        # Middle block
        self.mid_block = ResBlock(ch, ch, time_dim)

        # Build decoder (upsampling) path
        self.decoder_blocks = nn.ModuleList()
        self.upsamplers = nn.ModuleList()

        for mult in reversed(channel_mults):
            out_ch = base_channels * mult
            # Input channels doubled because of skip connections
            self.decoder_blocks.append(ResBlock(ch + out_ch, out_ch, time_dim))
            self.upsamplers.append(nn.ConvTranspose2d(out_ch, out_ch, 4, stride=2, padding=1))
            ch = out_ch

        self.final_conv = nn.Sequential(
            nn.GroupNorm(8, ch),
            nn.SiLU(),
            nn.Conv2d(ch, in_channels, 3, padding=1),
        )

    def forward(
        self,
        x: torch.Tensor,
        timesteps: torch.Tensor,
        class_labels: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        t_emb = self.time_embed(timesteps)
        if self.num_classes is not None and class_labels is not None:
            t_emb = t_emb + self.class_embed(class_labels)

        # Encoder with skip connections
        skips = []
        h = x
        for block, down in zip(self.encoder_blocks, self.downsamplers):
            h = block(h, t_emb)
            skips.append(h)
            h = down(h)

        h = self.mid_block(h, t_emb)

        # Decoder with skip connections
        for block, up in zip(self.decoder_blocks, self.upsamplers):
            skip = skips.pop()
            h = torch.cat([h, skip], dim=1)
            h = block(h, t_emb)
            h = up(h)

        return self.final_conv(h)
```

```python
# ---- Training Loop and CFG Sampling ----

def train_diffusion_step(
    model: SimpleUNet,
    scheduler: NoiseScheduler,
    images: torch.Tensor,
    optimizer: torch.optim.Optimizer,
    class_labels: Optional[torch.Tensor] = None,
    cfg_dropout_prob: float = 0.1,
) -> Dict[str, float]:
    # Single training step with classifier-free guidance dropout
    model.train()
    B = images.shape[0]
    device = images.device

    # Sample random timesteps
    timesteps = torch.randint(0, scheduler.num_timesteps, (B,), device=device)

    # Sample noise and create noisy images
    noise = torch.randn_like(images)
    noisy_images = scheduler.add_noise(images, noise, timesteps)

    # CFG: randomly drop class labels (replace with null class 0)
    train_labels = class_labels
    if class_labels is not None and cfg_dropout_prob > 0:
        drop_mask = torch.rand(B, device=device) < cfg_dropout_prob
        train_labels = class_labels.clone()
        train_labels[drop_mask] = 0  # 0 = unconditional

    # Predict noise
    predicted_noise = model(noisy_images, timesteps, train_labels)
    loss = F.mse_loss(predicted_noise, noise)

    optimizer.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    optimizer.step()

    return {"loss": loss.item()}


@torch.no_grad()
def sample_ddim_cfg(
    model: SimpleUNet,
    scheduler: NoiseScheduler,
    shape: Tuple[int, ...],
    class_labels: torch.Tensor,
    guidance_scale: float = 7.5,
    num_inference_steps: int = 50,
    device: torch.device = torch.device("cpu"),
    eta: float = 0.0,
) -> torch.Tensor:
    # DDIM sampling with classifier-free guidance
    # eta=0 is deterministic DDIM, eta=1 is DDPM-like
    model.eval()
    B = shape[0]

    # Create evenly spaced timestep schedule
    step_size = scheduler.num_timesteps // num_inference_steps
    timestep_seq = list(range(0, scheduler.num_timesteps, step_size))[::-1]

    # Start from pure noise
    x = torch.randn(shape, device=device)
    null_labels = torch.zeros_like(class_labels)  # unconditional class

    for i, t in enumerate(timestep_seq):
        t_batch = torch.full((B,), t, device=device, dtype=torch.long)

        # Conditional and unconditional predictions
        noise_cond = model(x, t_batch, class_labels)
        noise_uncond = model(x, t_batch, null_labels)

        # Classifier-free guidance: extrapolate toward conditional
        noise_pred = noise_uncond + guidance_scale * (noise_cond - noise_uncond)

        # DDIM update step
        alpha_bar_t = scheduler.alpha_cumprod[t]
        alpha_bar_prev = scheduler.alpha_cumprod[timestep_seq[i + 1]] if i + 1 < len(timestep_seq) else torch.tensor(1.0)

        # Predict x_0 from noise prediction
        pred_x0 = (x - torch.sqrt(1 - alpha_bar_t) * noise_pred) / torch.sqrt(alpha_bar_t)
        pred_x0 = pred_x0.clamp(-1, 1)  # Stability clipping

        # Direction pointing to x_t
        sigma = eta * torch.sqrt((1 - alpha_bar_prev) / (1 - alpha_bar_t) * (1 - alpha_bar_t / alpha_bar_prev))
        dir_xt = torch.sqrt(1 - alpha_bar_prev - sigma ** 2) * noise_pred

        # Noise for stochastic component (zero when eta=0)
        noise = torch.randn_like(x) if eta > 0 and i + 1 < len(timestep_seq) else torch.zeros_like(x)
        x = torch.sqrt(alpha_bar_prev) * pred_x0 + dir_xt + sigma * noise

    return x
```

## Summary and Key Takeaways

- **Diffusion models** generate images by learning to reverse a gradual noising process, which is mathematically simpler than direct generation because each step only removes a small amount of noise.
- The **forward process** has a closed-form solution allowing direct sampling at any timestep t, which is critical for efficient training. **Best practice** is to use the **cosine noise schedule** over linear, because it distributes the learning signal more uniformly across timesteps.
- The **U-Net denoiser** uses encoder-decoder architecture with skip connections, timestep conditioning via sinusoidal embeddings, and self-attention at low resolutions. However, recent work (DiT) replaces U-Nets with pure transformers.
- **Classifier-free guidance** trains a single model with random label dropout and amplifies the conditional signal at inference time. The guidance scale w controls the **trade-off** between fidelity and diversity — typical values are 5-15.
- **DDPM** sampling is stochastic and requires all T steps; **DDIM** reformulates the reverse process as a deterministic ODE enabling 10-50x fewer steps. Therefore, DDIM is preferred for production inference.
- **Common mistake**: Not clamping predicted x_0 during sampling. Without clamping, extreme noise predictions cause pixel values to explode, producing artifacts. Always clamp to [-1, 1].
- **Pitfall**: Using the same learning rate for all model components. The timestep embedding and class embedding layers benefit from higher learning rates, while the convolutional backbone prefers lower rates.
"""
    ),
    (
        "multimodal/audio-speech-ai-whisper-architecture",
        "Explain audio and speech AI systems including the Whisper architecture, mel spectrogram computation, CTC loss for speech recognition, attention-based ASR decoding, and text-to-speech approaches like VITS and Bark, then implement mel spectrogram extraction, a CTC-based decoder, and a Whisper-style encoder-decoder inference pipeline in PyTorch.",
        r"""# Audio and Speech AI: Whisper, Mel Spectrograms, CTC, and Modern ASR

## The Audio AI Landscape

**Speech and audio AI** encompasses automatic speech recognition (ASR), text-to-speech (TTS), speaker identification, audio classification, and music generation. The field has undergone a revolution similar to NLP's transformer era: large-scale pre-trained models like **Whisper** (OpenAI), **wav2vec 2.0** (Meta), and **USM** (Google) now achieve near-human accuracy on speech recognition, while **VITS**, **Bark**, and **VALL-E** generate remarkably natural speech.

The fundamental challenge in audio AI is representing the input signal. Raw audio is a 1D waveform sampled at 16,000-48,000 Hz, which is far too long for direct processing (one second of 16kHz audio is 16,000 values). Therefore, the standard approach is to convert audio to a **mel spectrogram** — a time-frequency representation that compresses the signal while preserving perceptually relevant information.

**Common mistake**: Treating audio AI as simply "NLP on spectrograms." Audio has unique challenges: variable-length alignment (speech-to-text), noise robustness, speaker variability, and the need for real-time processing. These require specialized architectures and loss functions.

## Mel Spectrograms: The Foundation of Audio AI

### From Waveform to Spectrogram

A **mel spectrogram** is computed through these steps:
1. **Windowing**: Divide the waveform into overlapping frames (typically 25ms windows with 10ms hop)
2. **FFT**: Apply the Fast Fourier Transform to each frame, producing a linear-frequency spectrogram
3. **Mel filterbank**: Apply triangular filters spaced according to the **mel scale**, which approximates human auditory perception (we are more sensitive to differences in low frequencies than high frequencies)
4. **Log compression**: Take the logarithm of the mel-filtered energies, because human loudness perception is approximately logarithmic

The result is a 2D matrix of shape (num_mel_bins, num_frames) — essentially a "spectrogram image" that can be processed by standard architectures (CNNs or transformers).

**Best practice**: Use 80 mel bins and a 400-sample FFT window at 16kHz sampling rate. These are the settings used by Whisper and most modern ASR systems. However, for music applications, 128 mel bins and larger FFT windows (2048 samples) are preferred because music requires finer frequency resolution.

### The Mel Scale

The mel scale is defined by: mel(f) = 2595 * log10(1 + f / 700). This maps linear frequency (Hz) to perceptual frequency (mels). The key insight is that the difference between 100 Hz and 200 Hz sounds much larger to humans than the difference between 8000 Hz and 8100 Hz, even though both are 100 Hz apart. Therefore, mel-spaced filters are denser at low frequencies and sparser at high frequencies.

## CTC Loss for Speech Recognition

### The Alignment Problem

In speech recognition, the input (spectrogram frames) and output (text characters) have different lengths, and we do not know the alignment between them. **CTC (Connectionist Temporal Classification)** solves this by introducing a "blank" token and marginalizing over all possible alignments.

For example, the word "cat" could align to spectrogram frames as: `--c-aa-t--` (where - is blank). CTC sums the probabilities of ALL valid alignments, and the loss is the negative log of this sum. This is computed efficiently using dynamic programming (forward-backward algorithm).

**Trade-off**: CTC assumes **conditional independence** between output tokens at each timestep, which means it cannot model inter-token dependencies well. Therefore, CTC-based models struggle with language modeling and often need an external language model for decoding. Attention-based models (like Whisper) do not have this limitation because the decoder autoregressively conditions on previously generated tokens.

**Pitfall**: CTC requires that the input sequence be at least as long as the output sequence (after removing blanks and collapsing repeats). If the spectrogram is too short relative to the text, training will diverge with NaN losses.

## Whisper Architecture

### Encoder-Decoder Design

**Whisper** is an encoder-decoder transformer trained on 680,000 hours of multilingual speech data. Its architecture is straightforward:

- **Encoder**: Takes a log-mel spectrogram (80 bins, 30-second chunks = 3000 frames) and processes it through two 1D convolution layers (for downsampling by 2x) followed by transformer encoder blocks. The output is a sequence of 1500 hidden states.
- **Decoder**: A standard autoregressive transformer decoder that generates text tokens, cross-attending to encoder outputs. Special tokens control behavior: `<|startoftranscript|>`, `<|en|>` (language), `<|transcribe|>` or `<|translate|>`, `<|notimestamps|>`.

**Key insight**: Whisper's power comes from its training data and multi-task formulation, not architectural novelty. It is trained simultaneously on transcription, translation, language identification, and timestamp prediction, because this multi-task setup provides strong regularization and forces the model to learn robust representations.

## Text-to-Speech: VITS and Bark

### VITS (Variational Inference with adversarial learning for end-to-end Text-to-Speech)

**VITS** combines a VAE (variational autoencoder), normalizing flows, and a GAN (generative adversarial network) in a single end-to-end model. It maps text to mel spectrograms (or directly to waveforms via a HiFi-GAN vocoder). The key innovation is using normalizing flows to bridge the gap between the text encoder's posterior and a simple prior, enabling diverse and natural speech synthesis.

### Bark

**Bark** (by Suno) takes a different approach: it uses a GPT-style autoregressive model to predict audio tokens from text. The audio tokens come from **EnCodec** (a neural audio codec), and the model is trained to predict them sequentially. This enables not just speech but also music, sound effects, and non-verbal sounds. However, the autoregressive nature makes it slower than parallel approaches like VITS.

## Implementation: Mel Spectrograms, CTC Decoder, and Whisper-Style Pipeline

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Tuple, Optional, Dict
import math


class MelSpectrogramExtractor(nn.Module):
    # Extracts mel spectrograms from raw audio waveforms
    # Uses torchaudio-compatible parameters

    def __init__(
        self,
        sample_rate: int = 16000,
        n_fft: int = 400,
        hop_length: int = 160,
        n_mels: int = 80,
        f_min: float = 0.0,
        f_max: Optional[float] = 8000.0,
    ) -> None:
        super().__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels

        # Pre-compute mel filterbank matrix
        mel_fb = self._create_mel_filterbank(
            n_fft // 2 + 1, n_mels, sample_rate, f_min, f_max
        )
        self.register_buffer("mel_filterbank", mel_fb)

        # Hann window for STFT
        self.register_buffer("window", torch.hann_window(n_fft))

    @staticmethod
    def _hz_to_mel(freq: float) -> float:
        return 2595.0 * math.log10(1.0 + freq / 700.0)

    @staticmethod
    def _mel_to_hz(mel: float) -> float:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    def _create_mel_filterbank(
        self,
        num_fft_bins: int,
        n_mels: int,
        sample_rate: int,
        f_min: float,
        f_max: float,
    ) -> torch.Tensor:
        # Create triangular mel filterbank matrix
        mel_min = self._hz_to_mel(f_min)
        mel_max = self._hz_to_mel(f_max)
        mel_points = torch.linspace(mel_min, mel_max, n_mels + 2)
        hz_points = torch.tensor([self._mel_to_hz(m.item()) for m in mel_points])

        # Convert to FFT bin indices
        bin_indices = (hz_points * num_fft_bins * 2 / sample_rate).long()
        filterbank = torch.zeros(n_mels, num_fft_bins)

        for i in range(n_mels):
            left = bin_indices[i]
            center = bin_indices[i + 1]
            right = bin_indices[i + 2]
            # Rising slope
            for j in range(left, center):
                if center > left:
                    filterbank[i, j] = (j - left) / (center - left)
            # Falling slope
            for j in range(center, right):
                if right > center:
                    filterbank[i, j] = (right - j) / (right - center)
        return filterbank

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        # waveform: (B, num_samples) -> mel_spec: (B, n_mels, num_frames)
        # Compute STFT
        stft = torch.stft(
            waveform, self.n_fft, self.hop_length,
            window=self.window, return_complex=True,
            center=True, pad_mode="reflect",
        )
        # Power spectrogram
        power_spec = stft.abs() ** 2  # (B, n_fft//2+1, num_frames)
        # Apply mel filterbank
        mel_spec = torch.matmul(self.mel_filterbank, power_spec)
        # Log compression with floor for numerical stability
        log_mel = torch.log(mel_spec.clamp(min=1e-10))
        return log_mel
```

```python
# ---- CTC Decoder ----

class CTCDecoder:
    # Greedy CTC decoder with optional beam search
    # Handles blank token removal and repeated character collapsing

    def __init__(self, vocabulary: List[str], blank_idx: int = 0) -> None:
        self.vocabulary = vocabulary
        self.blank_idx = blank_idx
        self.idx_to_char = {i: c for i, c in enumerate(vocabulary)}

    def greedy_decode(self, log_probs: torch.Tensor) -> List[str]:
        # log_probs: (B, T, vocab_size) -> list of decoded strings
        # Greedy: take argmax at each timestep, then collapse
        predictions = log_probs.argmax(dim=-1)  # (B, T)
        decoded: List[str] = []

        for b in range(predictions.shape[0]):
            tokens = predictions[b].tolist()
            # Remove consecutive duplicates, then remove blanks
            collapsed: List[int] = []
            prev_token = -1
            for t in tokens:
                if t != prev_token:
                    if t != self.blank_idx:
                        collapsed.append(t)
                    prev_token = t
            text = "".join(self.idx_to_char.get(t, "?") for t in collapsed)
            decoded.append(text)
        return decoded

    def beam_search_decode(
        self,
        log_probs: torch.Tensor,
        beam_width: int = 10,
    ) -> List[str]:
        # Beam search CTC decoding for a single sequence
        # log_probs: (T, vocab_size)
        T, V = log_probs.shape
        # Each beam: (prefix_tuple, score)
        beams: List[Tuple[Tuple[int, ...], float]] = [((), 0.0)]

        for t in range(T):
            new_beams: Dict[Tuple[int, ...], float] = {}
            for prefix, score in beams:
                for v in range(V):
                    new_score = score + log_probs[t, v].item()
                    if v == self.blank_idx:
                        # Blank: keep prefix unchanged
                        key = prefix
                    elif len(prefix) > 0 and v == prefix[-1]:
                        # Same character: keep prefix (CTC repeat)
                        key = prefix
                    else:
                        # New character: extend prefix
                        key = prefix + (v,)

                    if key not in new_beams or new_beams[key] < new_score:
                        new_beams[key] = new_score

            # Keep top beams
            beams = sorted(new_beams.items(), key=lambda x: x[1], reverse=True)[:beam_width]

        best_prefix = beams[0][0]
        return "".join(self.idx_to_char.get(t, "?") for t in best_prefix)
```

```python
# ---- Whisper-Style Encoder-Decoder ----

class WhisperEncoder(nn.Module):
    # Whisper-style audio encoder with conv downsampling + transformer

    def __init__(
        self,
        n_mels: int = 80,
        d_model: int = 512,
        num_heads: int = 8,
        num_layers: int = 6,
        max_audio_len: int = 1500,
    ) -> None:
        super().__init__()
        # Two 1D convolutions for downsampling (Whisper uses these)
        self.conv1 = nn.Conv1d(n_mels, d_model, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(d_model, d_model, kernel_size=3, stride=2, padding=1)
        self.positional_embedding = nn.Embedding(max_audio_len, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=num_heads, dim_feedforward=d_model * 4,
            dropout=0.1, activation="gelu", batch_first=True, norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.layer_norm = nn.LayerNorm(d_model)

    def forward(self, mel_spec: torch.Tensor) -> torch.Tensor:
        # mel_spec: (B, n_mels, T) -> (B, T//2, d_model)
        x = F.gelu(self.conv1(mel_spec))
        x = F.gelu(self.conv2(x))  # Downsample by 2x
        x = x.permute(0, 2, 1)  # (B, T//2, d_model)

        seq_len = x.shape[1]
        positions = torch.arange(seq_len, device=x.device)
        x = x + self.positional_embedding(positions)

        x = self.transformer(x)
        x = self.layer_norm(x)
        return x


class WhisperDecoder(nn.Module):
    # Autoregressive decoder with cross-attention to encoder output

    def __init__(
        self,
        vocab_size: int = 51865,
        d_model: int = 512,
        num_heads: int = 8,
        num_layers: int = 6,
        max_text_len: int = 448,
    ) -> None:
        super().__init__()
        self.token_embedding = nn.Embedding(vocab_size, d_model)
        self.positional_embedding = nn.Embedding(max_text_len, d_model)
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=d_model, nhead=num_heads, dim_feedforward=d_model * 4,
            dropout=0.1, activation="gelu", batch_first=True, norm_first=True,
        )
        self.transformer = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        self.layer_norm = nn.LayerNorm(d_model)
        self.output_proj = nn.Linear(d_model, vocab_size, bias=False)

    def forward(
        self,
        token_ids: torch.Tensor,
        encoder_output: torch.Tensor,
    ) -> torch.Tensor:
        # token_ids: (B, S) -> logits: (B, S, vocab_size)
        seq_len = token_ids.shape[1]
        positions = torch.arange(seq_len, device=token_ids.device)
        x = self.token_embedding(token_ids) + self.positional_embedding(positions)

        # Causal mask for autoregressive decoding
        causal_mask = nn.Transformer.generate_square_subsequent_mask(
            seq_len, device=token_ids.device
        )
        x = self.transformer(x, encoder_output, tgt_mask=causal_mask)
        x = self.layer_norm(x)
        logits = self.output_proj(x)
        return logits


@torch.no_grad()
def whisper_inference(
    encoder: WhisperEncoder,
    decoder: WhisperDecoder,
    mel_spec: torch.Tensor,
    start_token_id: int = 50258,
    eos_token_id: int = 50257,
    max_length: int = 224,
) -> List[int]:
    # Autoregressive greedy decoding for Whisper-style model
    encoder.eval()
    decoder.eval()

    encoder_output = encoder(mel_spec)  # (1, T, d_model)
    generated: List[int] = [start_token_id]

    for _ in range(max_length):
        token_ids = torch.tensor([generated], device=mel_spec.device)
        logits = decoder(token_ids, encoder_output)
        next_token = logits[0, -1].argmax().item()
        generated.append(next_token)

        if next_token == eos_token_id:
            break

    return generated[1:]  # Remove start token
```

## Summary and Key Takeaways

- **Mel spectrograms** convert raw audio waveforms into compact 2D time-frequency representations, using the mel scale to match human auditory perception. **Best practice** is 80 mel bins at 16kHz with log compression.
- **CTC loss** solves the alignment problem in ASR by marginalizing over all possible alignments between spectrogram frames and text. However, it assumes conditional independence, which limits its language modeling capability. Therefore, modern systems prefer attention-based decoders.
- **Whisper** uses a standard encoder-decoder transformer: convolution-based downsampling + transformer encoder for audio, autoregressive transformer decoder for text. Its strength comes from massive multilingual training data and multi-task learning, not architectural novelty.
- **Beam search decoding** significantly improves CTC-based recognition accuracy over greedy decoding, because it explores multiple hypotheses simultaneously and can recover from local errors.
- **VITS** combines VAEs, normalizing flows, and GANs for end-to-end TTS, while **Bark** uses GPT-style autoregressive prediction of audio tokens. The **trade-off** is latency vs. expressiveness: parallel models (VITS) are faster, autoregressive models (Bark) are more flexible.
- **Common mistake**: Using too-short audio windows for spectrogram computation. Windows below 20ms lose frequency resolution and produce blurry spectrograms. The standard 25ms window provides a good balance.
- **Pitfall**: Forgetting to normalize mel spectrograms before feeding them to the encoder. Whisper uses per-channel normalization (subtracting the mean and dividing by standard deviation), which is critical for stable training.
"""
    ),
    (
        "multimodal/document-understanding-ocr-layout-analysis",
        "Explain document understanding AI covering OCR integration, layout analysis algorithms, LayoutLM and DocFormer architectures, table extraction techniques, and visual question answering on documents, then implement a complete document processing pipeline in Python with text region detection, reading order determination, structured table extraction, and document VQA integration.",
        r"""# Document Understanding: OCR, Layout Analysis, and Structured Extraction

## The Document AI Challenge

**Document understanding** is the task of extracting structured information from visually rich documents — invoices, receipts, forms, scientific papers, contracts, and more. Unlike plain text NLP, document AI must reason about **spatial layout**, **visual formatting** (bold, italic, font size), **tables and figures**, and the **semantic relationships** between document regions.

This is challenging because documents encode meaning through both textual content and visual structure. For example, the number "1,250.00" means very different things depending on whether it appears next to "Total Due:" or "Account Number:". Therefore, effective document AI systems must jointly model text, position, and visual appearance.

**Common mistake**: Treating document understanding as "run OCR, then do NLP." This pipeline approach loses critical spatial information. Modern architectures like **LayoutLM** and **DocFormer** jointly encode text, position, and image features, producing far better results because they can learn correlations between visual layout and semantic meaning.

## OCR Integration

### Modern OCR Approaches

**Optical Character Recognition (OCR)** is the foundation of document AI. Modern OCR engines like **Tesseract 5**, **PaddleOCR**, **EasyOCR**, and cloud services (Google Vision, Azure Document Intelligence) provide not just text but also **bounding boxes**, **confidence scores**, and sometimes **paragraph/line grouping**.

**Best practice**: Always use OCR engines that output bounding boxes with text, not just plain text. The spatial coordinates are essential for downstream layout analysis. Additionally, ensemble multiple OCR engines for critical applications — no single engine is best across all document types, and ensembling reduces error rates by 15-30%.

### OCR Error Handling

OCR is imperfect. Common errors include: confusing similar characters (0/O, 1/l/I), missing small text, merging or splitting words incorrectly, and struggling with handwriting or unusual fonts. Therefore, robust document AI systems must include error correction mechanisms — either rule-based post-processing or learned error correction models.

**Pitfall**: Assuming OCR output is always left-to-right, top-to-bottom. Multi-column documents, forms with scattered fields, and languages with different reading directions (RTL, vertical) all violate this assumption. Layout analysis is essential to establish correct reading order.

## Layout Analysis

### Region Detection

**Layout analysis** segments a document page into semantic regions: text paragraphs, headings, tables, figures, headers, footers, page numbers, etc. This is typically formulated as an object detection problem, using architectures like Faster R-CNN, DETR, or YOLO trained on document-specific datasets (PubLayNet, DocBank, DOCLAYNET).

### Reading Order Determination

After detecting regions, we must establish the **reading order** — the sequence in which regions should be read to produce coherent text. This is non-trivial for multi-column layouts, sidebars, and documents with floating figures.

**Trade-off**: Simple heuristics (sort by y-coordinate, then x-coordinate) work for single-column documents but fail catastrophically for multi-column layouts. Learning-based approaches (treating reading order as a graph sorting problem) are more robust but require training data with annotated reading orders.

## LayoutLM and DocFormer Architectures

### LayoutLM

**LayoutLM** (Microsoft) extends BERT to incorporate 2D positional information. Each token receives:
1. **Text embedding**: Standard wordpiece embedding
2. **1D position embedding**: Sequence position (as in BERT)
3. **2D position embedding**: Bounding box coordinates (x0, y0, x1, y1) normalized to the page
4. **Image embedding** (LayoutLMv2+): CNN features from the corresponding image region

These are summed and processed by a transformer encoder. The 2D positional embeddings allow the model to learn spatial relationships — for example, that labels are typically to the left of or above their corresponding values.

### DocFormer

**DocFormer** goes further by using a **multi-modal attention mechanism** that creates separate attention scores for text, position, and image modalities, then combines them. This is more expressive than LayoutLM's simple addition of embeddings, because it allows the model to weight modalities differently depending on context.

## Table Extraction

### The Table Problem

Tables are one of the hardest document elements to extract. Challenges include:
- **Bordered vs. borderless tables**: Lines may or may not separate cells
- **Merged cells**: Row/column spans complicate the grid structure
- **Nested tables**: Tables within tables
- **Implicit tables**: Visually aligned data without any explicit table structure

### Extraction Approaches

1. **Rule-based**: Detect horizontal and vertical lines, find intersections, segment cells
2. **Detection-based**: Use object detection to find table regions, then cell detection within each table
3. **Structure recognition**: Predict the table's HTML/XML structure directly from the image (as in TableFormer)

## Implementation: Document Processing Pipeline

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Tuple, Dict, Optional, Any
from dataclasses import dataclass, field
import math
import re


@dataclass
class TextRegion:
    # Represents a detected text region on a document page
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1) normalized 0-1
    confidence: float
    region_type: str = "paragraph"  # paragraph, heading, table_cell, header, footer
    font_size_estimate: float = 12.0
    is_bold: bool = False

    @property
    def center_x(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def center_y(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class TableCell:
    # Represents a single cell in an extracted table
    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False


@dataclass
class ExtractedTable:
    # Represents a fully extracted table with structure
    cells: List[TableCell]
    num_rows: int
    num_cols: int
    bbox: Tuple[float, float, float, float]

    def to_dict_rows(self) -> List[Dict[str, str]]:
        # Convert table to list of row dictionaries
        # Uses first row as headers
        headers: Dict[int, str] = {}
        data_rows: List[Dict[str, str]] = []

        for cell in self.cells:
            if cell.is_header or cell.row == 0:
                headers[cell.col] = cell.text.strip()

        for row_idx in range(1, self.num_rows):
            row_cells = [c for c in self.cells if c.row == row_idx]
            row_dict: Dict[str, str] = {}
            for cell in row_cells:
                header = headers.get(cell.col, f"col_{cell.col}")
                row_dict[header] = cell.text.strip()
            if row_dict:
                data_rows.append(row_dict)
        return data_rows


class ColumnDetector:
    # Detects column layout in a document page
    # Uses projection profile analysis to find column boundaries

    def __init__(self, min_gap_ratio: float = 0.03) -> None:
        self.min_gap_ratio = min_gap_ratio  # Minimum gap width relative to page

    def detect_columns(
        self, regions: List[TextRegion], page_width: float = 1.0
    ) -> List[Tuple[float, float]]:
        # Returns list of (left_edge, right_edge) for each column
        if not regions:
            return [(0.0, page_width)]

        # Build horizontal projection profile
        num_bins = 200
        profile = [0.0] * num_bins

        for region in regions:
            left_bin = int(region.bbox[0] * num_bins)
            right_bin = int(region.bbox[2] * num_bins)
            for b in range(max(0, left_bin), min(num_bins, right_bin)):
                profile[b] += region.height

        # Find gaps (bins with near-zero projection)
        threshold = max(profile) * 0.05
        min_gap_bins = int(self.min_gap_ratio * num_bins)

        gaps: List[Tuple[int, int]] = []
        gap_start: Optional[int] = None

        for i, val in enumerate(profile):
            if val <= threshold:
                if gap_start is None:
                    gap_start = i
            else:
                if gap_start is not None:
                    gap_len = i - gap_start
                    if gap_len >= min_gap_bins:
                        gaps.append((gap_start, i))
                    gap_start = None

        # Convert gaps to column boundaries
        columns: List[Tuple[float, float]] = []
        prev_end = 0.0
        for gap_start_bin, gap_end_bin in gaps:
            gap_center = ((gap_start_bin + gap_end_bin) / 2) / num_bins
            if gap_center > prev_end + 0.05:
                columns.append((prev_end, gap_center))
            prev_end = gap_center

        if prev_end < page_width - 0.05:
            columns.append((prev_end, page_width))

        return columns if columns else [(0.0, page_width)]
```

```python
# ---- Reading Order and Table Extraction ----

class ReadingOrderSorter:
    # Determines reading order for document regions
    # Handles multi-column layouts using column detection

    def __init__(self, y_tolerance: float = 0.008) -> None:
        self.y_tolerance = y_tolerance
        self.column_detector = ColumnDetector()

    def _assign_columns(
        self,
        regions: List[TextRegion],
        columns: List[Tuple[float, float]],
    ) -> Dict[int, List[TextRegion]]:
        # Assign each region to its column
        column_regions: Dict[int, List[TextRegion]] = {i: [] for i in range(len(columns))}

        for region in regions:
            best_col = 0
            best_overlap = 0.0
            for col_idx, (col_left, col_right) in enumerate(columns):
                overlap_left = max(region.bbox[0], col_left)
                overlap_right = min(region.bbox[2], col_right)
                overlap = max(0, overlap_right - overlap_left)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_col = col_idx
            column_regions[best_col].append(region)
        return column_regions

    def sort_regions(self, regions: List[TextRegion]) -> List[TextRegion]:
        # Sort regions into reading order: left column top-to-bottom,
        # then right column top-to-bottom
        if not regions:
            return []

        # Separate full-width regions (headings, etc.) from column content
        columns = self.column_detector.detect_columns(regions)

        full_width: List[TextRegion] = []
        column_content: List[TextRegion] = []

        page_width = 1.0
        for region in regions:
            if region.width > page_width * 0.7:
                full_width.append(region)
            else:
                column_content.append(region)

        # Sort full-width by y position
        full_width.sort(key=lambda r: r.bbox[1])

        # Sort column content within columns
        col_assignments = self._assign_columns(column_content, columns)
        ordered: List[TextRegion] = []

        # Interleave full-width and column regions by y position
        col_idx = 0
        fw_idx = 0
        all_columns_sorted = []
        for c_idx in sorted(col_assignments.keys()):
            col_regions = col_assignments[c_idx]
            col_regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
            all_columns_sorted.extend(col_regions)

        # Merge: full-width items appear at their y position
        combined = full_width + all_columns_sorted
        combined.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
        return combined


class TableExtractor:
    # Extracts table structure from detected text regions
    # Uses spatial clustering to identify rows and columns

    def __init__(
        self,
        row_tolerance: float = 0.008,
        col_tolerance: float = 0.02,
    ) -> None:
        self.row_tolerance = row_tolerance
        self.col_tolerance = col_tolerance

    def _cluster_values(
        self, values: List[float], tolerance: float
    ) -> List[List[int]]:
        # Cluster nearby values into groups
        if not values:
            return []
        indexed = sorted(enumerate(values), key=lambda x: x[1])
        clusters: List[List[int]] = [[indexed[0][0]]]

        for i in range(1, len(indexed)):
            if indexed[i][1] - indexed[i - 1][1] <= tolerance:
                clusters[-1].append(indexed[i][0])
            else:
                clusters.append([indexed[i][0]])
        return clusters

    def extract_table(
        self, cell_regions: List[TextRegion], table_bbox: Tuple[float, float, float, float]
    ) -> ExtractedTable:
        # Given text regions within a table bounding box,
        # determine grid structure and assign cells
        if not cell_regions:
            return ExtractedTable([], 0, 0, table_bbox)

        # Cluster by y-center for rows
        y_centers = [r.center_y for r in cell_regions]
        row_clusters = self._cluster_values(y_centers, self.row_tolerance)

        # Cluster by x-center for columns
        x_centers = [r.center_x for r in cell_regions]
        col_clusters = self._cluster_values(x_centers, self.col_tolerance)

        # Build row/column index maps
        region_to_row: Dict[int, int] = {}
        for row_idx, cluster in enumerate(row_clusters):
            for region_idx in cluster:
                region_to_row[region_idx] = row_idx

        region_to_col: Dict[int, int] = {}
        for col_idx, cluster in enumerate(col_clusters):
            for region_idx in cluster:
                region_to_col[region_idx] = col_idx

        # Create cells
        cells: List[TableCell] = []
        for i, region in enumerate(cell_regions):
            row = region_to_row.get(i, 0)
            col = region_to_col.get(i, 0)
            is_header = row == 0  # First row assumed header
            cells.append(TableCell(
                text=region.text,
                row=row,
                col=col,
                is_header=is_header,
            ))

        return ExtractedTable(
            cells=cells,
            num_rows=len(row_clusters),
            num_cols=len(col_clusters),
            bbox=table_bbox,
        )
```

```python
# ---- LayoutLM-Style Feature Encoding and Document VQA ----

class LayoutAwareEncoder(nn.Module):
    # LayoutLM-inspired encoder that combines text, position, and visual features
    # Uses 2D position embeddings for spatial awareness

    def __init__(
        self,
        vocab_size: int = 30522,
        max_2d_position: int = 1024,
        d_model: int = 768,
        num_heads: int = 12,
        num_layers: int = 6,
        max_seq_len: int = 512,
    ) -> None:
        super().__init__()
        self.token_embedding = nn.Embedding(vocab_size, d_model)
        self.seq_position_embedding = nn.Embedding(max_seq_len, d_model)

        # 2D spatial embeddings (one for each bbox coordinate)
        self.x_embedding = nn.Embedding(max_2d_position, d_model // 4)
        self.y_embedding = nn.Embedding(max_2d_position, d_model // 4)
        self.w_embedding = nn.Embedding(max_2d_position, d_model // 4)
        self.h_embedding = nn.Embedding(max_2d_position, d_model // 4)

        # Visual feature projection (from CNN/ViT features)
        self.visual_proj = nn.Linear(256, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=num_heads, dim_feedforward=d_model * 4,
            dropout=0.1, activation="gelu", batch_first=True, norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.layer_norm = nn.LayerNorm(d_model)

    def forward(
        self,
        token_ids: torch.Tensor,
        bbox_coords: torch.Tensor,
        visual_features: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        # token_ids: (B, S) -- wordpiece token IDs
        # bbox_coords: (B, S, 4) -- normalized bbox [x0, y0, x1, y1] scaled to max_2d_position
        # visual_features: (B, S, 256) -- optional CNN features per token
        B, S = token_ids.shape

        # Text embedding
        text_emb = self.token_embedding(token_ids)
        seq_pos = torch.arange(S, device=token_ids.device)
        text_emb = text_emb + self.seq_position_embedding(seq_pos)

        # 2D position embedding from bounding boxes
        x0 = bbox_coords[:, :, 0].long().clamp(0, 1023)
        y0 = bbox_coords[:, :, 1].long().clamp(0, 1023)
        x1 = bbox_coords[:, :, 2].long().clamp(0, 1023)
        y1 = bbox_coords[:, :, 3].long().clamp(0, 1023)

        spatial_emb = torch.cat([
            self.x_embedding(x0),
            self.y_embedding(y0),
            self.x_embedding(x1) + self.w_embedding((x1 - x0).clamp(0, 1023)),
            self.y_embedding(y1) + self.h_embedding((y1 - y0).clamp(0, 1023)),
        ], dim=-1)  # (B, S, d_model)

        combined = text_emb + spatial_emb

        if visual_features is not None:
            combined = combined + self.visual_proj(visual_features)

        output = self.transformer(combined)
        output = self.layer_norm(output)
        return output


class DocumentVQA(nn.Module):
    # Document Visual Question Answering model
    # Encodes document layout + text, then answers questions extractively

    def __init__(
        self,
        vocab_size: int = 30522,
        d_model: int = 768,
        num_heads: int = 12,
        num_layers: int = 6,
    ) -> None:
        super().__init__()
        self.encoder = LayoutAwareEncoder(
            vocab_size=vocab_size, d_model=d_model,
            num_heads=num_heads, num_layers=num_layers,
        )
        # Span prediction heads (extractive QA like BERT)
        self.start_head = nn.Linear(d_model, 1)
        self.end_head = nn.Linear(d_model, 1)

    def forward(
        self,
        token_ids: torch.Tensor,
        bbox_coords: torch.Tensor,
        visual_features: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        # Returns start and end logits for answer span
        encoded = self.encoder(token_ids, bbox_coords, visual_features)
        start_logits = self.start_head(encoded).squeeze(-1)  # (B, S)
        end_logits = self.end_head(encoded).squeeze(-1)  # (B, S)
        return start_logits, end_logits


class DocumentProcessor:
    # End-to-end document processing pipeline
    # Orchestrates OCR, layout analysis, table extraction, and VQA

    def __init__(self) -> None:
        self.reading_order_sorter = ReadingOrderSorter()
        self.table_extractor = TableExtractor()

    def process_page(
        self,
        ocr_regions: List[TextRegion],
        table_bboxes: Optional[List[Tuple[float, float, float, float]]] = None,
    ) -> Dict[str, Any]:
        # Full pipeline: sort reading order, extract tables, structure output
        # Step 1: Sort into reading order
        sorted_regions = self.reading_order_sorter.sort_regions(ocr_regions)

        # Step 2: Separate table regions from text regions
        tables: List[ExtractedTable] = []
        text_regions: List[TextRegion] = []

        if table_bboxes:
            for table_bbox in table_bboxes:
                # Find regions within table bounding box
                table_cells = [
                    r for r in sorted_regions
                    if (r.bbox[0] >= table_bbox[0] - 0.01 and
                        r.bbox[1] >= table_bbox[1] - 0.01 and
                        r.bbox[2] <= table_bbox[2] + 0.01 and
                        r.bbox[3] <= table_bbox[3] + 0.01)
                ]
                table_region_set = set(id(r) for r in table_cells)
                table = self.table_extractor.extract_table(table_cells, table_bbox)
                tables.append(table)

            # Remaining regions are text
            table_region_ids = set()
            for table_bbox in table_bboxes:
                for r in sorted_regions:
                    if (r.bbox[0] >= table_bbox[0] - 0.01 and
                        r.bbox[1] >= table_bbox[1] - 0.01 and
                        r.bbox[2] <= table_bbox[2] + 0.01 and
                        r.bbox[3] <= table_bbox[3] + 0.01):
                        table_region_ids.add(id(r))
            text_regions = [r for r in sorted_regions if id(r) not in table_region_ids]
        else:
            text_regions = sorted_regions

        # Step 3: Build structured output
        full_text = "\n".join(r.text for r in text_regions)
        table_dicts = [t.to_dict_rows() for t in tables]

        return {
            "full_text": full_text,
            "text_regions": text_regions,
            "tables": table_dicts,
            "num_tables": len(tables),
            "reading_order_count": len(sorted_regions),
        }
```

## Summary and Key Takeaways

- **Document understanding** requires jointly modeling text content, spatial layout, and visual appearance — simple "OCR then NLP" pipelines lose critical spatial information. Therefore, layout-aware models like **LayoutLM** significantly outperform text-only approaches.
- **OCR integration** must preserve bounding boxes and confidence scores. **Best practice** is to ensemble multiple OCR engines and include error correction, because no single engine handles all document types well.
- **Layout analysis** segments pages into semantic regions and establishes **reading order**. Column detection via projection profiles is a robust baseline, however learning-based detectors (DETR, Faster R-CNN) handle complex layouts better.
- **Table extraction** is one of the hardest document AI tasks. The **trade-off** is between rule-based methods (fast, interpretable, but brittle) and learned methods (robust, but require annotated table data). Spatial clustering of cell regions into row/column groups is an effective middle ground.
- **LayoutLM** extends BERT with 2D positional embeddings for each bounding box coordinate, while **DocFormer** uses modality-specific attention. Both dramatically improve over text-only baselines on information extraction tasks.
- **Common mistake**: Assuming all documents are single-column. Multi-column layouts require explicit column detection before reading order can be determined, otherwise extracted text will interleave content from different columns.
- **Pitfall**: Normalizing bounding box coordinates inconsistently between OCR output and model input. Always normalize to [0, 1] relative to page dimensions, then scale to the model's expected range (e.g., 0-1000 for LayoutLM).
"""
    ),
]
