"""Multimodal AI — vision-language, document understanding, video analysis."""

PAIRS = [
    (
        "ai/document-understanding",
        "Show document understanding with AI: OCR integration, layout analysis, table extraction, and document QA.",
        '''Document AI pipeline:

```python
from dataclasses import dataclass
from typing import Optional
from anthropic import Anthropic
import base64
from pathlib import Path


@dataclass
class DocumentResult:
    text: str
    tables: list[list[list[str]]]
    metadata: dict
    confidence: float


class DocumentProcessor:
    """Process documents using multimodal AI."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic()
        self.model = model

    def process_image(self, image_path: str, task: str = "extract") -> DocumentResult:
        """Process document image with vision model."""
        image_data = base64.b64encode(Path(image_path).read_bytes()).decode()
        media_type = "image/png" if image_path.endswith(".png") else "image/jpeg"

        prompts = {
            "extract": "Extract ALL text from this document image. Preserve formatting, headers, and structure. Output the text exactly as it appears.",
            "table": "Extract all tables from this document. Output each table as a JSON array of rows, where each row is an array of cell values.",
            "summarize": "Summarize the key information in this document. Include: document type, key dates, amounts, parties involved, and main content.",
            "qa": None,  # Set dynamically
        }

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": prompts.get(task, task)},
                ],
            }],
        )

        text = response.content[0].text
        return DocumentResult(text=text, tables=[], metadata={"task": task}, confidence=0.9)

    def answer_question(self, image_path: str, question: str) -> str:
        """Visual question answering on document."""
        image_data = base64.b64encode(Path(image_path).read_bytes()).decode()
        media_type = "image/png" if image_path.endswith(".png") else "image/jpeg"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": f"Based on this document, answer: {question}"},
                ],
            }],
        )
        return response.content[0].text

    def compare_documents(self, image_path_a: str, image_path_b: str, criteria: str) -> str:
        """Compare two documents."""
        images = []
        for path in [image_path_a, image_path_b]:
            data = base64.b64encode(Path(path).read_bytes()).decode()
            mt = "image/png" if path.endswith(".png") else "image/jpeg"
            images.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": images + [{"type": "text", "text": f"Compare these two documents: {criteria}"}],
            }],
        )
        return response.content[0].text
```

Key patterns:
1. **Base64 encoding** — encode images for API; vision models process document layout natively
2. **Task-specific prompts** — different prompts for extraction, table parsing, QA, and summarization
3. **Document QA** — answer questions about document content using visual understanding
4. **Multi-document** — compare or cross-reference multiple documents in one call
5. **Layout awareness** — vision models understand spatial layout, headers, columns, and tables'''
    ),
    (
        "ai/video-understanding",
        "Show video analysis with AI: frame sampling, temporal understanding, video QA, and action recognition patterns.",
        '''Video understanding pipeline:

```python
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from dataclasses import dataclass


@dataclass
class VideoSegment:
    start_time: float
    end_time: float
    description: str
    confidence: float


class FrameSampler:
    """Sample representative frames from video."""

    @staticmethod
    def uniform_sample(video_frames: np.ndarray, n_frames: int = 8) -> np.ndarray:
        """Uniformly sample n frames from video."""
        total = len(video_frames)
        indices = np.linspace(0, total - 1, n_frames, dtype=int)
        return video_frames[indices]

    @staticmethod
    def keyframe_sample(video_frames: np.ndarray, n_frames: int = 8,
                        threshold: float = 30.0) -> np.ndarray:
        """Sample frames at scene changes (high frame difference)."""
        diffs = []
        for i in range(1, len(video_frames)):
            diff = np.abs(video_frames[i].astype(float) - video_frames[i-1].astype(float)).mean()
            diffs.append(diff)

        # Select frames with highest differences (scene changes)
        diff_indices = np.argsort(diffs)[::-1][:n_frames - 1]
        indices = sorted([0] + [i + 1 for i in diff_indices])

        return video_frames[indices[:n_frames]]


class VideoEncoder(nn.Module):
    """Temporal video encoder: frame features + temporal modeling."""

    def __init__(self, frame_dim: int = 768, hidden_dim: int = 512, n_classes: int = 400):
        super().__init__()
        # Temporal modeling over frame embeddings
        self.temporal = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=frame_dim, nhead=8,
                dim_feedforward=frame_dim * 4,
                batch_first=True,
            ),
            num_layers=4,
        )
        self.temporal_token = nn.Parameter(torch.randn(1, 1, frame_dim))
        self.classifier = nn.Linear(frame_dim, n_classes)

    def forward(self, frame_features: torch.Tensor) -> torch.Tensor:
        """frame_features: [B, T, D] -> class logits: [B, n_classes]"""
        B = frame_features.shape[0]
        # Prepend [CLS] token for classification
        cls_token = self.temporal_token.expand(B, -1, -1)
        x = torch.cat([cls_token, frame_features], dim=1)
        x = self.temporal(x)
        return self.classifier(x[:, 0])  # CLS token output


class VideoQA:
    """Video question answering using frame sampling + VLM."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model
        self.sampler = FrameSampler()

    def answer(self, frames: list, question: str) -> str:
        """Answer question about video content."""
        import base64
        import io
        from PIL import Image

        # Encode frames as images
        image_content = []
        for i, frame in enumerate(frames[:8]):  # Max 8 frames
            img = Image.fromarray(frame)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            b64 = base64.b64encode(buffer.getvalue()).decode()
            image_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })

        image_content.append({
            "type": "text",
            "text": f"These are frames from a video in chronological order. {question}",
        })

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": image_content}],
        )
        return response.content[0].text
```

Key patterns:
1. **Frame sampling** — uniform or keyframe-based; 8-16 frames usually sufficient
2. **Temporal modeling** — transformer over frame features captures temporal relationships
3. **CLS token pooling** — prepend learnable token; its output represents the full video
4. **Multi-frame VLM** — send sampled frames to vision-language model for understanding
5. **Keyframe detection** — scene changes have high frame differences; more informative samples'''
    ),
    (
        "ai/image-generation-control",
        "Show controlled image generation patterns: ControlNet conditioning, IP-Adapter for style, and inpainting with diffusion models.",
        '''Controlled image generation with diffusion models:

```python
import torch
from diffusers import (
    StableDiffusionXLControlNetPipeline,
    ControlNetModel,
    StableDiffusionXLInpaintPipeline,
    AutoencoderKL,
)
from PIL import Image
import numpy as np


def generate_with_controlnet(
    prompt: str,
    control_image: Image.Image,
    control_type: str = "canny",
    negative_prompt: str = "low quality, blurry, deformed",
    num_inference_steps: int = 30,
    guidance_scale: float = 7.5,
    controlnet_scale: float = 0.8,
) -> Image.Image:
    """Generate image with structural control from ControlNet.

    Control types:
    - canny: edge detection → generate matching edges
    - depth: depth map → generate matching 3D structure
    - pose: skeleton → generate matching human pose
    - seg: segmentation map → generate matching regions
    """
    # Load ControlNet for the control type
    controlnet_models = {
        "canny": "diffusers/controlnet-canny-sdxl-1.0",
        "depth": "diffusers/controlnet-depth-sdxl-1.0",
    }

    controlnet = ControlNetModel.from_pretrained(
        controlnet_models[control_type],
        torch_dtype=torch.float16,
    )

    pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        controlnet=controlnet,
        torch_dtype=torch.float16,
    ).to("cuda")

    # Enable memory optimizations
    pipe.enable_model_cpu_offload()

    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=control_image,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        controlnet_conditioning_scale=controlnet_scale,
    ).images[0]

    return result


def inpaint_image(
    prompt: str,
    image: Image.Image,
    mask: Image.Image,
    strength: float = 0.8,
) -> Image.Image:
    """Inpaint masked region of image with diffusion model.

    Mask: white = inpaint, black = keep original.
    """
    pipe = StableDiffusionXLInpaintPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
    ).to("cuda")
    pipe.enable_model_cpu_offload()

    result = pipe(
        prompt=prompt,
        image=image,
        mask_image=mask,
        strength=strength,
        num_inference_steps=30,
    ).images[0]

    return result


def prepare_canny_control(image: Image.Image, low: int = 100, high: int = 200) -> Image.Image:
    """Extract Canny edges from image for ControlNet."""
    import cv2
    img_array = np.array(image)
    edges = cv2.Canny(img_array, low, high)
    return Image.fromarray(edges)
```

Controlled generation comparison:

| Method | Control type | Flexibility | Quality |
|--------|------------|------------|---------|
| **ControlNet** | Structural (edges, depth, pose) | High | Excellent |
| **IP-Adapter** | Style/content from reference image | High | Good |
| **Inpainting** | Region-specific editing | Medium | Excellent |
| **img2img** | Overall style transfer | Low | Good |
| **Textual Inversion** | Learned concept from few images | Low | Good |

Key patterns:
1. **ControlNet conditioning** — additional input (edges, depth, pose) guides spatial structure
2. **Conditioning scale** — 0.0-1.0 controls how strictly to follow the control signal
3. **Inpainting** — mask regions to regenerate; keeps unmasked areas intact
4. **CPU offload** — `enable_model_cpu_offload()` moves unused models to CPU; saves VRAM
5. **Negative prompts** — specify what to avoid; improves quality significantly'''
    ),
]
