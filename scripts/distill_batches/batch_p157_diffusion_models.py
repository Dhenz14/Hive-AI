"""Diffusion Models — denoising, DDPM, classifier-free guidance, and SDXL patterns."""

PAIRS = [
    (
        "ai/diffusion-fundamentals",
        "Show diffusion model fundamentals: forward/reverse process, DDPM training, noise scheduling, and the denoising U-Net.",
        '''Diffusion model fundamentals (DDPM):

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class GaussianDiffusion:
    """Denoising Diffusion Probabilistic Model (DDPM).

    Forward process: gradually add noise to data over T steps
    Reverse process: learn to denoise step by step
    """

    def __init__(self, num_timesteps: int = 1000, beta_start: float = 1e-4,
                 beta_end: float = 0.02, schedule: str = "cosine"):
        self.num_timesteps = num_timesteps

        if schedule == "linear":
            betas = torch.linspace(beta_start, beta_end, num_timesteps)
        elif schedule == "cosine":
            betas = self._cosine_schedule(num_timesteps)
        else:
            raise ValueError(f"Unknown schedule: {schedule}")

        self.betas = betas
        self.alphas = 1.0 - betas
        self.alphas_cumprod = torch.cumprod(self.alphas, dim=0)
        self.alphas_cumprod_prev = F.pad(self.alphas_cumprod[:-1], (1, 0), value=1.0)

        # Precompute coefficients
        self.sqrt_alphas_cumprod = torch.sqrt(self.alphas_cumprod)
        self.sqrt_one_minus_alphas_cumprod = torch.sqrt(1.0 - self.alphas_cumprod)
        self.sqrt_recip_alphas = torch.sqrt(1.0 / self.alphas)
        self.posterior_variance = betas * (1.0 - self.alphas_cumprod_prev) / (1.0 - self.alphas_cumprod)

    def _cosine_schedule(self, T: int, s: float = 0.008) -> torch.Tensor:
        steps = torch.arange(T + 1, dtype=torch.float64)
        f_t = torch.cos(((steps / T) + s) / (1 + s) * math.pi * 0.5) ** 2
        alphas_cumprod = f_t / f_t[0]
        betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
        return torch.clamp(betas, 0.0001, 0.9999).float()

    def q_sample(self, x_start: torch.Tensor, t: torch.Tensor,
                 noise: torch.Tensor | None = None) -> torch.Tensor:
        """Forward process: add noise to x_start at timestep t.

        q(x_t | x_0) = N(sqrt(alpha_bar_t) * x_0, (1 - alpha_bar_t) * I)
        """
        if noise is None:
            noise = torch.randn_like(x_start)

        sqrt_alpha = self.sqrt_alphas_cumprod[t].view(-1, 1, 1, 1)
        sqrt_one_minus = self.sqrt_one_minus_alphas_cumprod[t].view(-1, 1, 1, 1)

        return sqrt_alpha * x_start + sqrt_one_minus * noise

    def training_loss(self, model: nn.Module, x_start: torch.Tensor,
                      condition: torch.Tensor | None = None) -> torch.Tensor:
        """Compute training loss: predict noise from noisy image.

        L = E[||noise - model(x_t, t, condition)||^2]
        """
        batch_size = x_start.shape[0]
        t = torch.randint(0, self.num_timesteps, (batch_size,), device=x_start.device)
        noise = torch.randn_like(x_start)

        x_noisy = self.q_sample(x_start, t, noise)
        predicted_noise = model(x_noisy, t, condition)

        return F.mse_loss(predicted_noise, noise)

    @torch.no_grad()
    def p_sample(self, model: nn.Module, x: torch.Tensor, t: int,
                 condition: torch.Tensor | None = None) -> torch.Tensor:
        """Reverse process: denoise one step."""
        t_batch = torch.full((x.shape[0],), t, device=x.device, dtype=torch.long)
        predicted_noise = model(x, t_batch, condition)

        beta = self.betas[t]
        sqrt_recip_alpha = self.sqrt_recip_alphas[t]
        sqrt_one_minus = self.sqrt_one_minus_alphas_cumprod[t]

        # Predict x_{t-1} mean
        mean = sqrt_recip_alpha * (x - beta / sqrt_one_minus * predicted_noise)

        if t > 0:
            noise = torch.randn_like(x)
            sigma = torch.sqrt(self.posterior_variance[t])
            return mean + sigma * noise
        return mean

    @torch.no_grad()
    def sample(self, model: nn.Module, shape: tuple, condition: torch.Tensor | None = None,
               guidance_scale: float = 7.5) -> torch.Tensor:
        """Generate samples by running full reverse process."""
        device = next(model.parameters()).device
        x = torch.randn(shape, device=device)

        for t in reversed(range(self.num_timesteps)):
            if condition is not None and guidance_scale > 1.0:
                # Classifier-free guidance
                noise_cond = model(x, torch.full((shape[0],), t, device=device), condition)
                noise_uncond = model(x, torch.full((shape[0],), t, device=device), None)
                predicted_noise = noise_uncond + guidance_scale * (noise_cond - noise_uncond)

                # Manual denoising step with guided noise
                beta = self.betas[t]
                mean = self.sqrt_recip_alphas[t] * (
                    x - beta / self.sqrt_one_minus_alphas_cumprod[t] * predicted_noise
                )
                if t > 0:
                    x = mean + torch.sqrt(self.posterior_variance[t]) * torch.randn_like(x)
                else:
                    x = mean
            else:
                x = self.p_sample(model, x, t, condition)

        return x


class SinusoidalTimeEmbedding(nn.Module):
    """Sinusoidal embedding for timestep t (like positional encoding)."""

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        half_dim = self.dim // 2
        emb = math.log(10000) / (half_dim - 1)
        emb = torch.exp(torch.arange(half_dim, device=t.device) * -emb)
        emb = t.float().unsqueeze(1) * emb.unsqueeze(0)
        return torch.cat([emb.sin(), emb.cos()], dim=-1)


class SimpleUNet(nn.Module):
    """Simplified U-Net for noise prediction."""

    def __init__(self, in_channels: int = 3, base_channels: int = 64,
                 time_emb_dim: int = 256, condition_dim: int | None = 768):
        super().__init__()
        self.time_mlp = nn.Sequential(
            SinusoidalTimeEmbedding(time_emb_dim),
            nn.Linear(time_emb_dim, time_emb_dim),
            nn.SiLU(),
        )

        # Condition projection (e.g., text embedding from CLIP)
        self.cond_proj = None
        if condition_dim:
            self.cond_proj = nn.Linear(condition_dim, time_emb_dim)

        ch = base_channels
        # Encoder
        self.down1 = DownBlock(in_channels, ch, time_emb_dim)
        self.down2 = DownBlock(ch, ch * 2, time_emb_dim)
        self.down3 = DownBlock(ch * 2, ch * 4, time_emb_dim)

        # Bottleneck
        self.mid = ResBlock(ch * 4, ch * 4, time_emb_dim)

        # Decoder (with skip connections)
        self.up3 = UpBlock(ch * 4 + ch * 4, ch * 2, time_emb_dim)
        self.up2 = UpBlock(ch * 2 + ch * 2, ch, time_emb_dim)
        self.up1 = UpBlock(ch + ch, ch, time_emb_dim)

        self.final = nn.Conv2d(ch, in_channels, 1)

    def forward(self, x: torch.Tensor, t: torch.Tensor,
                condition: torch.Tensor | None = None) -> torch.Tensor:
        t_emb = self.time_mlp(t)

        if condition is not None and self.cond_proj is not None:
            t_emb = t_emb + self.cond_proj(condition)

        d1 = self.down1(x, t_emb)
        d2 = self.down2(d1, t_emb)
        d3 = self.down3(d2, t_emb)

        m = self.mid(d3, t_emb)

        u3 = self.up3(torch.cat([m, d3], dim=1), t_emb)
        u2 = self.up2(torch.cat([u3, d2], dim=1), t_emb)
        u1 = self.up1(torch.cat([u2, d1], dim=1), t_emb)

        return self.final(u1)
```

Diffusion model concepts:
```
Forward:  x_0 (clean) → x_1 → x_2 → ... → x_T (pure noise)
                  +ε₁      +ε₂              (add noise each step)

Reverse:  x_T (noise) → x_{T-1} → ... → x_1 → x_0 (generated)
                  -ε̂_T          -ε̂₂      -ε̂₁   (predict & remove noise)
```

Key patterns:
1. **Noise prediction** — model predicts the noise added at each step, not the clean image directly
2. **Cosine schedule** — better than linear; preserves more signal at early timesteps
3. **Classifier-free guidance** — train with condition dropout; at inference interpolate between conditional and unconditional predictions
4. **U-Net architecture** — skip connections preserve spatial detail; time embedding modulates each layer
5. **Guidance scale** — higher values (7-15) produce images more aligned to the prompt but less diverse'''
    ),
    (
        "ai/sdxl-inference",
        "Show Stable Diffusion XL inference pipeline: text encoding, latent diffusion, VAE decoding, and advanced sampling.",
        '''Stable Diffusion XL inference pipeline:

```python
import torch
from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler
from diffusers import AutoencoderKL
from PIL import Image


# === Basic SDXL inference ===

def generate_image(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted",
    width: int = 1024,
    height: int = 1024,
    num_steps: int = 30,
    guidance_scale: float = 7.5,
    seed: int | None = None,
) -> Image.Image:
    """Generate image with SDXL."""
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16",
    ).to("cuda")

    # Use DPM-Solver for faster sampling (vs default DDPM)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        algorithm_type="dpmsolver++",
        use_karras_sigmas=True,
    )

    generator = torch.Generator("cuda").manual_seed(seed) if seed else None

    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_inference_steps=num_steps,
        guidance_scale=guidance_scale,
        generator=generator,
    )

    return result.images[0]


# === SDXL with refiner (two-stage) ===

def generate_with_refiner(
    prompt: str,
    base_steps: int = 30,
    refiner_steps: int = 10,
    high_noise_fraction: float = 0.8,
) -> Image.Image:
    """Two-stage SDXL: base generates, refiner adds detail."""
    from diffusers import StableDiffusionXLImg2ImgPipeline

    # Stage 1: Base model (global composition)
    base = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
    ).to("cuda")

    # Stage 2: Refiner (local detail, textures)
    refiner = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        torch_dtype=torch.float16,
    ).to("cuda")

    # Base generates with partial denoising
    image = base(
        prompt=prompt,
        num_inference_steps=base_steps,
        denoising_end=high_noise_fraction,
        output_type="latent",
    ).images

    # Refiner completes denoising with fine details
    image = refiner(
        prompt=prompt,
        image=image,
        num_inference_steps=refiner_steps,
        denoising_start=high_noise_fraction,
    ).images[0]

    return image


# === LoRA loading for style transfer ===

def generate_with_lora(
    prompt: str,
    lora_path: str,
    lora_scale: float = 0.8,
) -> Image.Image:
    """Apply LoRA adapter for style-specific generation."""
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
    ).to("cuda")

    # Load LoRA weights
    pipe.load_lora_weights(lora_path)

    result = pipe(
        prompt=prompt,
        num_inference_steps=30,
        cross_attention_kwargs={"scale": lora_scale},
    )

    pipe.unload_lora_weights()
    return result.images[0]


# === IP-Adapter (image prompt) ===

def image_to_image_with_prompt(
    text_prompt: str,
    reference_image: Image.Image,
    ip_adapter_scale: float = 0.6,
) -> Image.Image:
    """Use reference image as visual prompt alongside text."""
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
    ).to("cuda")

    pipe.load_ip_adapter(
        "h94/IP-Adapter",
        subfolder="sdxl_models",
        weight_name="ip-adapter-plus_sdxl_vit-h.safetensors",
    )
    pipe.set_ip_adapter_scale(ip_adapter_scale)

    result = pipe(
        prompt=text_prompt,
        ip_adapter_image=reference_image,
        num_inference_steps=30,
    )
    return result.images[0]


# === ControlNet (structural guidance) ===

def generate_with_controlnet(
    prompt: str,
    control_image: Image.Image,
    control_type: str = "canny",
    controlnet_scale: float = 0.5,
) -> Image.Image:
    """Generate with structural control (edges, depth, pose)."""
    from diffusers import ControlNetModel, StableDiffusionXLControlNetPipeline

    controlnet = ControlNetModel.from_pretrained(
        f"diffusers/controlnet-{control_type}-sdxl-1.0",
        torch_dtype=torch.float16,
    )

    pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        controlnet=controlnet,
        torch_dtype=torch.float16,
    ).to("cuda")

    result = pipe(
        prompt=prompt,
        image=control_image,
        controlnet_conditioning_scale=controlnet_scale,
        num_inference_steps=30,
    )
    return result.images[0]
```

SDXL architecture:
```
Text → CLIP-L + CLIP-G → Text Embeddings (pooled + sequence)
                              ↓
Noise → U-Net (guided denoising, 30 steps) → Latent
                              ↓
Latent → VAE Decoder → 1024x1024 Image
```

Key patterns:
1. **Latent diffusion** — operate in compressed latent space (8x smaller than pixel space); VAE encodes/decodes
2. **Dual text encoders** — CLIP-L (local detail) + CLIP-G (global semantics) for richer text conditioning
3. **DPM-Solver++** — faster sampler (20-30 steps vs 50+ for DDPM) with Karras noise schedule
4. **Base + Refiner** — two-stage pipeline: base for composition, refiner for textures and fine detail
5. **ControlNet** — inject structural guidance (edges, depth, pose) without retraining the base model'''
    ),
]
