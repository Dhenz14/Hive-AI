"""Vision-Language Models — CLIP, LLaVA, multimodal fusion patterns."""

PAIRS = [
    (
        "ai/clip-embeddings",
        "Show CLIP-style contrastive vision-language pretraining: dual-encoder architecture, contrastive loss, and zero-shot classification.",
        '''CLIP-style contrastive vision-language model:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image


class CLIPModel(nn.Module):
    """Contrastive Language-Image Pretraining (CLIP).

    Two encoders trained to align image and text embeddings
    in a shared space via contrastive learning.
    """

    def __init__(self, embed_dim: int = 512, vision_width: int = 768, text_width: int = 512):
        super().__init__()
        self.visual = VisionEncoder(output_dim=embed_dim, width=vision_width)
        self.text = TextEncoder(output_dim=embed_dim, width=text_width)

        # Learnable temperature for contrastive loss
        self.logit_scale = nn.Parameter(torch.ones([]) * 2.6592)  # ln(1/0.07)

    def encode_image(self, images: torch.Tensor) -> torch.Tensor:
        features = self.visual(images)
        return F.normalize(features, dim=-1)

    def encode_text(self, input_ids: torch.Tensor) -> torch.Tensor:
        features = self.text(input_ids)
        return F.normalize(features, dim=-1)

    def forward(self, images: torch.Tensor, input_ids: torch.Tensor) -> dict:
        image_features = self.encode_image(images)
        text_features = self.encode_text(input_ids)

        # Cosine similarity as logits
        logit_scale = self.logit_scale.exp().clamp(max=100)
        logits_per_image = logit_scale * image_features @ text_features.t()
        logits_per_text = logits_per_image.t()

        return {"logits_per_image": logits_per_image, "logits_per_text": logits_per_text}


class VisionEncoder(nn.Module):
    """Vision Transformer encoder for images."""

    def __init__(self, output_dim: int = 512, width: int = 768,
                 patch_size: int = 16, image_size: int = 224, layers: int = 12):
        super().__init__()
        num_patches = (image_size // patch_size) ** 2

        self.patch_embed = nn.Conv2d(3, width, patch_size, stride=patch_size, bias=False)
        self.cls_token = nn.Parameter(torch.randn(1, 1, width) * 0.02)
        self.pos_embed = nn.Parameter(torch.randn(1, num_patches + 1, width) * 0.02)
        self.ln_pre = nn.LayerNorm(width)

        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=width, nhead=12, dim_feedforward=width * 4,
                                       dropout=0.0, activation="gelu", batch_first=True),
            num_layers=layers,
        )
        self.ln_post = nn.LayerNorm(width)
        self.projection = nn.Linear(width, output_dim, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.patch_embed(x).flatten(2).transpose(1, 2)  # [B, N, D]
        cls = self.cls_token.expand(x.shape[0], -1, -1)
        x = torch.cat([cls, x], dim=1)
        x = self.ln_pre(x + self.pos_embed)
        x = self.transformer(x)
        x = self.ln_post(x[:, 0])  # CLS token
        return self.projection(x)


class TextEncoder(nn.Module):
    """Transformer text encoder."""

    def __init__(self, output_dim: int = 512, width: int = 512,
                 vocab_size: int = 49408, max_length: int = 77, layers: int = 12):
        super().__init__()
        self.token_embed = nn.Embedding(vocab_size, width)
        self.pos_embed = nn.Parameter(torch.randn(1, max_length, width) * 0.02)

        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=width, nhead=8, dim_feedforward=width * 4,
                                       dropout=0.0, activation="gelu", batch_first=True),
            num_layers=layers,
        )
        self.ln_final = nn.LayerNorm(width)
        self.projection = nn.Linear(width, output_dim, bias=False)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.token_embed(input_ids) + self.pos_embed[:, :input_ids.shape[1]]
        # Causal mask for autoregressive text encoding
        mask = nn.Transformer.generate_square_subsequent_mask(input_ids.shape[1], device=x.device)
        x = self.transformer(x, mask=mask, is_causal=True)
        x = self.ln_final(x)
        # Use [EOS] token features (last non-padding token)
        x = x[torch.arange(x.shape[0]), input_ids.argmax(dim=-1)]
        return self.projection(x)


def clip_contrastive_loss(logits_per_image: torch.Tensor, logits_per_text: torch.Tensor) -> torch.Tensor:
    """Symmetric contrastive loss (InfoNCE).

    Each image should match its paired text, and vice versa.
    The diagonal of the similarity matrix contains positive pairs.
    """
    batch_size = logits_per_image.shape[0]
    labels = torch.arange(batch_size, device=logits_per_image.device)

    loss_i2t = F.cross_entropy(logits_per_image, labels)
    loss_t2i = F.cross_entropy(logits_per_text, labels)
    return (loss_i2t + loss_t2i) / 2


def zero_shot_classify(model: CLIPModel, image: torch.Tensor,
                        class_names: list[str], tokenizer) -> dict[str, float]:
    """Zero-shot image classification using CLIP.

    No training needed — just compare image embedding to text embeddings
    of class descriptions.
    """
    # Create text prompts for each class
    prompts = [f"a photo of a {name}" for name in class_names]
    text_tokens = tokenizer(prompts, padding=True, return_tensors="pt")

    with torch.no_grad():
        image_features = model.encode_image(image.unsqueeze(0))
        text_features = model.encode_text(text_tokens["input_ids"])

        similarity = (100.0 * image_features @ text_features.t()).softmax(dim=-1)

    return {name: score.item() for name, score in zip(class_names, similarity[0])}
```

CLIP architecture:
```
Image → Patch Embed → ViT → CLS token → Projection → L2 Normalize ──┐
                                                                       ├── Contrastive Loss
Text  → Token Embed → Transformer → EOS token → Projection → L2 Norm ┘
```

Key patterns:
1. **Dual encoder** — separate vision and text encoders project to shared embedding space
2. **Contrastive loss (InfoNCE)** — diagonal of similarity matrix = positive pairs; off-diagonal = negatives
3. **Learnable temperature** — `logit_scale` controls sharpness of similarity distribution
4. **Zero-shot transfer** — compare image embedding to text embeddings of class descriptions, no fine-tuning needed
5. **L2 normalization** — cosine similarity via normalized dot product ensures embeddings are comparable'''
    ),
    (
        "ai/vlm-inference",
        "Show vision-language model inference patterns: LLaVA-style architecture, image-text interleaving, and visual question answering.",
        '''Vision-Language Model inference (LLaVA-style):

```python
import torch
import torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer, CLIPVisionModel, CLIPImageProcessor
from PIL import Image


class VisionLanguageModel(nn.Module):
    """LLaVA-style Vision-Language Model.

    Architecture: CLIP Vision Encoder → Projection → LLM
    Visual tokens are injected into the LLM's token sequence.
    """

    def __init__(
        self,
        vision_model_name: str = "openai/clip-vit-large-patch14-336",
        llm_name: str = "Qwen/Qwen2.5-7B-Instruct",
        projection_dim: int = 4096,
    ):
        super().__init__()
        # Vision encoder (frozen)
        self.vision_encoder = CLIPVisionModel.from_pretrained(vision_model_name)
        self.image_processor = CLIPImageProcessor.from_pretrained(vision_model_name)
        for param in self.vision_encoder.parameters():
            param.requires_grad = False

        # LLM (fine-tuned or LoRA)
        self.llm = AutoModelForCausalLM.from_pretrained(
            llm_name, torch_dtype=torch.bfloat16, device_map="auto"
        )
        self.tokenizer = AutoTokenizer.from_pretrained(llm_name)

        # Multi-layer perceptron projection (vision dim → LLM dim)
        vision_dim = self.vision_encoder.config.hidden_size
        llm_dim = self.llm.config.hidden_size
        self.mm_projector = nn.Sequential(
            nn.Linear(vision_dim, projection_dim),
            nn.GELU(),
            nn.Linear(projection_dim, llm_dim),
        )

        # Special tokens
        self.image_token_id = self.tokenizer.convert_tokens_to_ids("<image>")
        self.num_image_tokens = 576  # 24x24 patches for CLIP ViT-L/14@336

    def encode_image(self, image: Image.Image) -> torch.Tensor:
        """Encode image into LLM-compatible token embeddings."""
        pixel_values = self.image_processor(image, return_tensors="pt")["pixel_values"]
        pixel_values = pixel_values.to(self.vision_encoder.device, dtype=torch.float16)

        with torch.no_grad():
            vision_outputs = self.vision_encoder(pixel_values, output_hidden_states=True)
            # Use second-to-last hidden state (better features than last)
            image_features = vision_outputs.hidden_states[-2][:, 1:]  # Skip CLS

        # Project to LLM embedding space
        image_embeds = self.mm_projector(image_features.to(self.mm_projector[0].weight.dtype))
        return image_embeds  # [1, 576, llm_dim]

    def prepare_inputs(
        self,
        text: str,
        images: list[Image.Image] | None = None,
    ) -> dict:
        """Prepare interleaved image-text inputs for the LLM."""
        if images:
            # Replace <image> placeholder with image token sequence
            image_embeds = []
            for img in images:
                embeds = self.encode_image(img)
                image_embeds.append(embeds)

            # Tokenize text
            parts = text.split("<image>")
            input_embeds = []
            input_ids = []

            for i, part in enumerate(parts):
                if part:
                    tokens = self.tokenizer(part, return_tensors="pt", add_special_tokens=(i == 0))
                    token_embeds = self.llm.get_input_embeddings()(tokens["input_ids"].to(self.llm.device))
                    input_embeds.append(token_embeds)

                if i < len(image_embeds):
                    input_embeds.append(image_embeds[i])

            inputs_embeds = torch.cat(input_embeds, dim=1)
            return {"inputs_embeds": inputs_embeds}
        else:
            tokens = self.tokenizer(text, return_tensors="pt")
            return {"input_ids": tokens["input_ids"].to(self.llm.device)}

    @torch.inference_mode()
    def generate(
        self,
        text: str,
        images: list[Image.Image] | None = None,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Generate response for image+text input."""
        inputs = self.prepare_inputs(text, images)

        output_ids = self.llm.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            top_p=0.9,
        )

        # Decode only new tokens
        if "input_ids" in inputs:
            new_tokens = output_ids[:, inputs["input_ids"].shape[1]:]
        else:
            new_tokens = output_ids  # Full output when using inputs_embeds

        return self.tokenizer.decode(new_tokens[0], skip_special_tokens=True)


# === Usage patterns ===

def visual_qa(model: VisionLanguageModel, image_path: str, question: str) -> str:
    """Visual question answering."""
    image = Image.open(image_path).convert("RGB")
    prompt = f"<image>\\nUser: {question}\\nAssistant:"
    return model.generate(prompt, images=[image])


def image_captioning(model: VisionLanguageModel, image_path: str) -> str:
    """Generate detailed image caption."""
    image = Image.open(image_path).convert("RGB")
    prompt = "<image>\\nDescribe this image in detail."
    return model.generate(prompt, images=[image], temperature=0.2)


def multi_image_reasoning(model: VisionLanguageModel, image_paths: list[str], question: str) -> str:
    """Reason across multiple images."""
    images = [Image.open(p).convert("RGB") for p in image_paths]
    image_tags = " ".join(f"Image {i+1}: <image>" for i in range(len(images)))
    prompt = f"{image_tags}\\n\\n{question}"
    return model.generate(prompt, images=images)


def ocr_and_extract(model: VisionLanguageModel, image_path: str) -> str:
    """Extract text from image with structure."""
    image = Image.open(image_path).convert("RGB")
    prompt = (
        "<image>\\nExtract all text from this image. "
        "Preserve the layout and structure. Output as markdown."
    )
    return model.generate(prompt, images=[image], temperature=0.1)
```

VLM architecture (LLaVA-style):
```
Image → CLIP ViT (frozen) → [576 patch tokens] → MLP Projector → Visual Tokens
                                                                        ↓
Text  → Tokenizer → Token Embeddings ─────────────────────────→ [text + visual tokens]
                                                                        ↓
                                                                   LLM (Qwen/Llama)
                                                                        ↓
                                                                   Generated Text
```

Key patterns:
1. **Frozen vision encoder** — CLIP ViT extracts visual features; no need to retrain on images
2. **MLP projector** — two-layer projection bridges vision and language embedding spaces
3. **Image token injection** — visual tokens replace `<image>` placeholder in the text sequence
4. **Second-to-last hidden state** — better features than the final layer for downstream tasks
5. **Multi-image support** — multiple `<image>` placeholders allow reasoning across several images'''
    ),
    (
        "ai/multimodal-fusion",
        "Show multimodal fusion strategies: early, late, and cross-attention fusion for combining vision, text, and audio features.",
        '''Multimodal fusion strategies:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


# === Early Fusion ===

class EarlyFusion(nn.Module):
    """Concatenate modalities before processing.

    Pros: Learns cross-modal interactions from the start
    Cons: Computationally expensive, needs aligned inputs
    """

    def __init__(self, image_dim: int = 768, text_dim: int = 512,
                 audio_dim: int = 256, hidden_dim: int = 1024, num_classes: int = 100):
        super().__init__()
        # Project all modalities to same dimension
        self.image_proj = nn.Linear(image_dim, hidden_dim)
        self.text_proj = nn.Linear(text_dim, hidden_dim)
        self.audio_proj = nn.Linear(audio_dim, hidden_dim)

        # Modality type embeddings (like token type in BERT)
        self.modality_embed = nn.Embedding(3, hidden_dim)

        # Joint transformer processes all modalities together
        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=hidden_dim, nhead=8, dim_feedforward=hidden_dim * 4,
                dropout=0.1, batch_first=True,
            ),
            num_layers=6,
        )
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def forward(self, image_tokens: torch.Tensor, text_tokens: torch.Tensor,
                audio_tokens: torch.Tensor) -> torch.Tensor:
        # Project to shared space
        img = self.image_proj(image_tokens) + self.modality_embed(torch.zeros(1, dtype=torch.long, device=image_tokens.device))
        txt = self.text_proj(text_tokens) + self.modality_embed(torch.ones(1, dtype=torch.long, device=text_tokens.device))
        aud = self.audio_proj(audio_tokens) + self.modality_embed(torch.full((1,), 2, dtype=torch.long, device=audio_tokens.device))

        # Concatenate all tokens
        combined = torch.cat([img, txt, aud], dim=1)  # [B, N_img+N_txt+N_aud, D]

        # Joint processing
        out = self.transformer(combined)
        pooled = out.mean(dim=1)
        return self.classifier(pooled)


# === Late Fusion ===

class LateFusion(nn.Module):
    """Process modalities independently, combine decisions.

    Pros: Modular, can use pretrained encoders, missing modality friendly
    Cons: No cross-modal interaction during encoding
    """

    def __init__(self, image_dim: int = 768, text_dim: int = 512,
                 audio_dim: int = 256, hidden_dim: int = 512, num_classes: int = 100):
        super().__init__()
        # Independent encoders (can be pretrained)
        self.image_encoder = nn.Sequential(
            nn.Linear(image_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim)
        )
        self.text_encoder = nn.Sequential(
            nn.Linear(text_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim)
        )
        self.audio_encoder = nn.Sequential(
            nn.Linear(audio_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim)
        )

        # Learnable fusion weights
        self.fusion_weights = nn.Parameter(torch.ones(3) / 3)

        # Final classifier
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def forward(self, image_feat: torch.Tensor, text_feat: torch.Tensor,
                audio_feat: torch.Tensor,
                available_modalities: list[bool] | None = None) -> torch.Tensor:
        encodings = []
        weights = F.softmax(self.fusion_weights, dim=0)

        if available_modalities is None:
            available_modalities = [True, True, True]

        # Process each available modality independently
        modality_outputs = []
        active_weights = []

        if available_modalities[0]:
            modality_outputs.append(self.image_encoder(image_feat))
            active_weights.append(weights[0])
        if available_modalities[1]:
            modality_outputs.append(self.text_encoder(text_feat))
            active_weights.append(weights[1])
        if available_modalities[2]:
            modality_outputs.append(self.audio_encoder(audio_feat))
            active_weights.append(weights[2])

        # Weighted sum of modality representations
        active_weights = torch.stack(active_weights)
        active_weights = active_weights / active_weights.sum()  # Renormalize

        fused = sum(w * out for w, out in zip(active_weights, modality_outputs))
        return self.classifier(fused)


# === Cross-Attention Fusion ===

class CrossAttentionFusion(nn.Module):
    """Modalities attend to each other via cross-attention.

    Pros: Rich cross-modal interaction, selective attention
    Cons: Quadratic complexity in combined sequence length
    Used by: Flamingo, GPT-4V, Gemini
    """

    def __init__(self, dim: int = 512, num_heads: int = 8, num_layers: int = 4):
        super().__init__()
        self.layers = nn.ModuleList([
            CrossAttentionBlock(dim, num_heads) for _ in range(num_layers)
        ])
        self.final_norm = nn.LayerNorm(dim)

    def forward(self, query_tokens: torch.Tensor,
                context_tokens: torch.Tensor) -> torch.Tensor:
        """Query modality attends to context modality.

        E.g., text tokens attend to image tokens to ground language in vision.
        """
        x = query_tokens
        for layer in self.layers:
            x = layer(x, context_tokens)
        return self.final_norm(x)


class CrossAttentionBlock(nn.Module):
    def __init__(self, dim: int, num_heads: int):
        super().__init__()
        self.self_attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.cross_attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * 4), nn.GELU(), nn.Linear(dim * 4, dim)
        )
        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.norm3 = nn.LayerNorm(dim)

    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        # Self-attention within query modality
        residual = x
        x = self.norm1(x)
        x = residual + self.self_attn(x, x, x)[0]

        # Cross-attention: query attends to context
        residual = x
        x = self.norm2(x)
        x = residual + self.cross_attn(x, context, context)[0]

        # Feed-forward
        residual = x
        x = self.norm3(x)
        x = residual + self.ffn(x)

        return x


# === Perceiver-style Fusion (handles any number of modalities) ===

class PerceiverFusion(nn.Module):
    """Perceiver: modality-agnostic fusion via learned latent queries.

    A fixed set of latent tokens cross-attend to any input modality.
    Handles variable-length, variable-modality inputs uniformly.
    """

    def __init__(self, dim: int = 512, num_latents: int = 64,
                 num_layers: int = 6, num_heads: int = 8):
        super().__init__()
        self.latents = nn.Parameter(torch.randn(num_latents, dim) * 0.02)

        self.cross_attn_layers = nn.ModuleList([
            CrossAttentionBlock(dim, num_heads) for _ in range(num_layers)
        ])

    def forward(self, *modality_tokens: torch.Tensor) -> torch.Tensor:
        """Process any number of modality inputs."""
        # Concatenate all modality tokens
        context = torch.cat(modality_tokens, dim=1)  # [B, total_tokens, D]

        # Latent tokens cross-attend to all modalities
        x = self.latents.unsqueeze(0).expand(context.shape[0], -1, -1)

        for layer in self.cross_attn_layers:
            x = layer(x, context)

        return x  # [B, num_latents, D] — fixed-size output
```

Fusion strategy comparison:

| Strategy | Cross-modal | Missing modality | Compute | Used by |
|----------|------------|-----------------|---------|---------|
| **Early** | Full (joint transformer) | Requires all | O((N₁+N₂)²) | ViLBERT |
| **Late** | None during encoding | Graceful | O(N₁²+N₂²) | Ensemble |
| **Cross-attention** | Selective attention | Graceful | O(N₁·N₂) | Flamingo, GPT-4V |
| **Perceiver** | Via latent bottleneck | Graceful | O(L·N_total) | Perceiver IO |

Key patterns:
1. **Early fusion** — concatenate modality tokens with type embeddings; joint transformer learns cross-modal patterns
2. **Late fusion** — independent encoders + learnable weighted combination; works with missing modalities
3. **Cross-attention** — query modality selectively attends to context modality; used in Flamingo and GPT-4V
4. **Perceiver** — fixed latent queries cross-attend to any combination of modalities; constant output size regardless of input
5. **Modality dropout** — randomly drop modalities during training to build robustness to missing inputs'''
    ),
]
