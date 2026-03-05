"""Neural radiance fields and 3D AI — NeRF, 3D Gaussian Splatting, point clouds."""

PAIRS = [
    (
        "ai/nerf-basics",
        "Show Neural Radiance Field (NeRF) implementation: positional encoding, MLP architecture, volume rendering, and training from posed images.",
        '''NeRF — Neural Radiance Fields:

```python
import torch
import torch.nn as nn
import numpy as np


class PositionalEncoding(nn.Module):
    """Map coordinates to higher dimension using sinusoidal functions.

    Key insight: MLPs struggle with high-frequency detail in low dimensions.
    Positional encoding lifts (x,y,z) to a higher-dimensional space where
    the MLP can represent sharp features.
    """

    def __init__(self, n_freqs: int = 10, include_input: bool = True):
        super().__init__()
        self.n_freqs = n_freqs
        self.include_input = include_input
        freqs = 2.0 ** torch.arange(n_freqs)
        self.register_buffer("freqs", freqs)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [..., D] -> [..., D * (2*n_freqs + include_input)]
        encoded = []
        if self.include_input:
            encoded.append(x)
        for freq in self.freqs:
            encoded.append(torch.sin(freq * x))
            encoded.append(torch.cos(freq * x))
        return torch.cat(encoded, dim=-1)

    @property
    def output_dim(self):
        d = self.n_freqs * 2
        if self.include_input:
            d += 1
        return d


class NeRF(nn.Module):
    """Neural Radiance Field: maps (x,y,z,θ,φ) → (RGB, σ).

    Architecture:
    - 8-layer MLP for density (view-independent)
    - Skip connection at layer 4
    - 1 additional layer for color (view-dependent)
    """

    def __init__(self, pos_dim: int = 63, dir_dim: int = 27,
                 hidden_dim: int = 256):
        super().__init__()
        # Density network (view-independent)
        self.density_layers = nn.ModuleList()
        self.density_layers.append(nn.Linear(pos_dim, hidden_dim))
        for i in range(7):
            if i == 3:
                self.density_layers.append(nn.Linear(hidden_dim + pos_dim, hidden_dim))
            else:
                self.density_layers.append(nn.Linear(hidden_dim, hidden_dim))

        self.sigma_out = nn.Linear(hidden_dim, 1)
        self.feature_out = nn.Linear(hidden_dim, hidden_dim)

        # Color network (view-dependent)
        self.color_layers = nn.Sequential(
            nn.Linear(hidden_dim + dir_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 3),
            nn.Sigmoid(),
        )

    def forward(self, pos_encoded, dir_encoded):
        h = pos_encoded
        for i, layer in enumerate(self.density_layers):
            if i == 4:
                h = torch.cat([h, pos_encoded], dim=-1)
            h = torch.relu(layer(h))

        sigma = torch.relu(self.sigma_out(h))
        features = self.feature_out(h)
        color = self.color_layers(torch.cat([features, dir_encoded], dim=-1))
        return color, sigma


def volume_render(colors, sigmas, t_vals):
    """Classic volume rendering: accumulate color along ray.

    T_i = exp(-sum_{j<i} sigma_j * delta_j)  (transmittance)
    C = sum_i T_i * (1 - exp(-sigma_i * delta_i)) * c_i
    """
    deltas = t_vals[..., 1:] - t_vals[..., :-1]
    deltas = torch.cat([deltas, torch.full_like(deltas[..., :1], 1e10)], dim=-1)

    alpha = 1.0 - torch.exp(-sigmas.squeeze(-1) * deltas)
    transmittance = torch.cumprod(1.0 - alpha + 1e-10, dim=-1)
    transmittance = torch.cat([torch.ones_like(transmittance[..., :1]),
                                transmittance[..., :-1]], dim=-1)

    weights = alpha * transmittance
    rgb = (weights.unsqueeze(-1) * colors).sum(dim=-2)
    depth = (weights * t_vals).sum(dim=-1)

    return rgb, depth, weights
```

Key patterns:
1. **Positional encoding** — sinusoidal mapping lifts low-dim coordinates to high-dim; enables sharp detail
2. **View-dependent color** — density is view-independent but color depends on viewing direction (specular)
3. **Skip connection** — concatenate input at layer 4; helps gradient flow in deep MLP
4. **Volume rendering** — alpha compositing along rays; differentiable end-to-end for backprop
5. **Transmittance** — cumulative product of (1-alpha); ensures occluded points contribute less'''
    ),
    (
        "ai/gaussian-splatting",
        "Show 3D Gaussian Splatting concepts: representing scenes as 3D Gaussians, differentiable rasterization, and real-time rendering.",
        '''3D Gaussian Splatting — real-time radiance fields:

```python
import torch
import torch.nn as nn
import numpy as np
from dataclasses import dataclass


@dataclass
class Gaussian3D:
    """Single 3D Gaussian primitive."""
    position: torch.Tensor     # [3] xyz center
    covariance: torch.Tensor   # [3,3] or [6] upper-triangle
    color_sh: torch.Tensor     # [C] spherical harmonic coefficients
    opacity: torch.Tensor      # [1] alpha value
    scale: torch.Tensor        # [3] scale factors
    rotation: torch.Tensor     # [4] quaternion


class GaussianModel(nn.Module):
    """Collection of 3D Gaussians representing a scene."""

    def __init__(self, n_points: int, sh_degree: int = 3):
        super().__init__()
        n_sh = (sh_degree + 1) ** 2

        # Learnable parameters for each Gaussian
        self.positions = nn.Parameter(torch.randn(n_points, 3))
        self.scales = nn.Parameter(torch.zeros(n_points, 3))  # log scale
        self.rotations = nn.Parameter(torch.zeros(n_points, 4))  # quaternion
        self.opacities = nn.Parameter(torch.zeros(n_points, 1))  # logit
        self.sh_coeffs = nn.Parameter(torch.zeros(n_points, n_sh, 3))  # RGB SH

        # Initialize rotations to identity quaternion
        self.rotations.data[:, 0] = 1.0

    def get_covariance(self) -> torch.Tensor:
        """Compute 3D covariance from scale and rotation."""
        S = torch.diag_embed(torch.exp(self.scales))  # [N, 3, 3]
        R = quaternion_to_matrix(self.rotations)       # [N, 3, 3]
        # Σ = R S S^T R^T
        RS = R @ S
        return RS @ RS.transpose(-1, -2)

    def project_to_2d(self, viewmat: torch.Tensor, projmat: torch.Tensor):
        """Project 3D Gaussians to 2D screen space."""
        # Transform positions to camera space
        pos_h = torch.cat([self.positions, torch.ones_like(self.positions[:, :1])], -1)
        cam_pos = (viewmat @ pos_h.T).T[:, :3]

        # 2D covariance via Jacobian of projection
        cov3d = self.get_covariance()
        J = compute_projection_jacobian(cam_pos, projmat)
        cov2d = J @ cov3d @ J.transpose(-1, -2)

        return cam_pos, cov2d[:, :2, :2]

    def adaptive_density_control(self, grad_threshold: float = 0.0002):
        """Split large Gaussians, clone small ones, prune transparent ones."""
        grad_norms = self.positions.grad.norm(dim=-1)
        scales = torch.exp(self.scales).max(dim=-1).values

        # Clone small Gaussians with high gradient (under-reconstruction)
        clone_mask = (grad_norms > grad_threshold) & (scales < 0.01)
        # Split large Gaussians with high gradient (over-reconstruction)
        split_mask = (grad_norms > grad_threshold) & (scales >= 0.01)
        # Prune nearly transparent Gaussians
        prune_mask = torch.sigmoid(self.opacities).squeeze() < 0.005

        return clone_mask, split_mask, prune_mask


def quaternion_to_matrix(q: torch.Tensor) -> torch.Tensor:
    """Convert quaternion [w,x,y,z] to rotation matrix."""
    q = q / q.norm(dim=-1, keepdim=True)
    w, x, y, z = q.unbind(-1)
    return torch.stack([
        1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y),
        2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x),
        2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y),
    ], dim=-1).reshape(-1, 3, 3)
```

NeRF vs 3D Gaussian Splatting:

| Aspect | NeRF | 3DGS |
|--------|------|------|
| **Representation** | Implicit (MLP) | Explicit (Gaussians) |
| **Render speed** | Seconds per frame | Real-time (100+ FPS) |
| **Training** | Hours | Minutes |
| **Editability** | Hard | Easy (move/delete Gaussians) |
| **Memory** | Low (MLP weights) | High (millions of Gaussians) |

Key patterns:
1. **Explicit primitives** — scene represented as millions of 3D Gaussians; no neural network at render time
2. **Differentiable rasterization** — project and splat Gaussians to screen; backprop through rasterizer
3. **Spherical harmonics** — encode view-dependent color; compact representation of angular variation
4. **Adaptive density** — clone, split, and prune Gaussians during training for quality optimization
5. **Covariance from scale+rotation** — Σ = RSS^TR^T; numerically stable parameterization'''
    ),
    (
        "ai/point-cloud-processing",
        "Show point cloud processing with deep learning: PointNet architecture, 3D object detection, and point cloud segmentation.",
        '''Point cloud deep learning:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class TNet(nn.Module):
    """Spatial Transformer Network for point cloud alignment."""

    def __init__(self, k: int = 3):
        super().__init__()
        self.k = k
        self.conv = nn.Sequential(
            nn.Conv1d(k, 64, 1), nn.BatchNorm1d(64), nn.ReLU(),
            nn.Conv1d(64, 128, 1), nn.BatchNorm1d(128), nn.ReLU(),
            nn.Conv1d(128, 1024, 1), nn.BatchNorm1d(1024), nn.ReLU(),
        )
        self.fc = nn.Sequential(
            nn.Linear(1024, 512), nn.BatchNorm1d(512), nn.ReLU(),
            nn.Linear(512, 256), nn.BatchNorm1d(256), nn.ReLU(),
            nn.Linear(256, k * k),
        )

    def forward(self, x):
        B = x.shape[0]
        h = self.conv(x)
        h = h.max(dim=-1)[0]  # Global max pooling
        h = self.fc(h)
        # Initialize as identity
        identity = torch.eye(self.k, device=x.device).flatten().unsqueeze(0).expand(B, -1)
        return (h + identity).reshape(B, self.k, self.k)


class PointNet(nn.Module):
    """PointNet: per-point features + global max pooling.

    Key insight: max pooling over points is permutation-invariant,
    making the network agnostic to point ordering.
    """

    def __init__(self, n_classes: int = 40):
        super().__init__()
        self.input_transform = TNet(k=3)
        self.feature_transform = TNet(k=64)

        self.conv1 = nn.Sequential(nn.Conv1d(3, 64, 1), nn.BatchNorm1d(64), nn.ReLU())
        self.conv2 = nn.Sequential(nn.Conv1d(64, 64, 1), nn.BatchNorm1d(64), nn.ReLU())
        self.conv3 = nn.Sequential(nn.Conv1d(64, 128, 1), nn.BatchNorm1d(128), nn.ReLU())
        self.conv4 = nn.Sequential(nn.Conv1d(128, 1024, 1), nn.BatchNorm1d(1024), nn.ReLU())

        self.classifier = nn.Sequential(
            nn.Linear(1024, 512), nn.BatchNorm1d(512), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(512, 256), nn.BatchNorm1d(256), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(256, n_classes),
        )

    def forward(self, x):
        """x: [B, 3, N] point cloud -> [B, n_classes] logits"""
        # Input alignment
        T = self.input_transform(x)
        x = torch.bmm(T, x)

        # Per-point features
        x = self.conv1(x)
        x = self.conv2(x)

        # Feature alignment
        T_feat = self.feature_transform(x)
        x = torch.bmm(T_feat, x)

        x = self.conv3(x)
        x = self.conv4(x)

        # Global feature (permutation invariant)
        global_feat = x.max(dim=-1)[0]

        return self.classifier(global_feat)


class PointNetSegmentation(nn.Module):
    """PointNet for per-point segmentation."""

    def __init__(self, n_classes: int, n_points: int = 2048):
        super().__init__()
        # Local features
        self.local_feat = nn.Sequential(
            nn.Conv1d(3, 64, 1), nn.BatchNorm1d(64), nn.ReLU(),
            nn.Conv1d(64, 128, 1), nn.BatchNorm1d(128), nn.ReLU(),
            nn.Conv1d(128, 128, 1), nn.BatchNorm1d(128), nn.ReLU(),
        )
        # Global features
        self.global_feat = nn.Sequential(
            nn.Conv1d(128, 512, 1), nn.BatchNorm1d(512), nn.ReLU(),
            nn.Conv1d(512, 1024, 1), nn.BatchNorm1d(1024), nn.ReLU(),
        )
        # Segmentation head (local + global concatenated)
        self.seg_head = nn.Sequential(
            nn.Conv1d(1024 + 128, 512, 1), nn.BatchNorm1d(512), nn.ReLU(),
            nn.Conv1d(512, 256, 1), nn.BatchNorm1d(256), nn.ReLU(),
            nn.Conv1d(256, n_classes, 1),
        )

    def forward(self, x):
        """x: [B, 3, N] -> [B, n_classes, N] per-point logits"""
        local = self.local_feat(x)           # [B, 128, N]
        g = self.global_feat(local)           # [B, 1024, N]
        g = g.max(dim=-1)[0]                  # [B, 1024]
        g = g.unsqueeze(-1).expand(-1, -1, local.shape[-1])  # [B, 1024, N]
        combined = torch.cat([local, g], dim=1)  # [B, 1152, N]
        return self.seg_head(combined)
```

Key patterns:
1. **Max pooling symmetry** — max over points gives permutation invariance; order doesn't matter
2. **Spatial transformer** — learn alignment transform; handles arbitrary rotations
3. **Local + global** — concatenate per-point features with global context for segmentation
4. **Conv1d as pointwise MLP** — 1×1 convolutions process each point independently
5. **Feature transform regularization** — constrain feature TNet close to orthogonal for stability'''
    ),
]
