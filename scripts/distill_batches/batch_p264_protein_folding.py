"""AI for science — protein structure, molecular dynamics, scientific ML."""

PAIRS = [
    (
        "ai/protein-structure",
        "Show protein structure prediction concepts: sequence embeddings, attention over residues, distance prediction, and structure refinement.",
        '''Protein structure prediction with deep learning:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np


class ResidueEmbedding(nn.Module):
    """Embed amino acid sequence for structure prediction."""

    def __init__(self, vocab_size: int = 21, embed_dim: int = 256,
                 max_len: int = 1024):
        super().__init__()
        self.token_embed = nn.Embedding(vocab_size, embed_dim)
        self.pos_embed = nn.Embedding(max_len, embed_dim)
        self.norm = nn.LayerNorm(embed_dim)

    def forward(self, sequence: torch.Tensor) -> torch.Tensor:
        """sequence: [B, L] amino acid indices -> [B, L, D]"""
        positions = torch.arange(sequence.shape[1], device=sequence.device)
        x = self.token_embed(sequence) + self.pos_embed(positions)
        return self.norm(x)


class PairwiseFeatures(nn.Module):
    """Compute pairwise residue features for distance prediction."""

    def __init__(self, single_dim: int = 256, pair_dim: int = 128):
        super().__init__()
        self.left_proj = nn.Linear(single_dim, pair_dim)
        self.right_proj = nn.Linear(single_dim, pair_dim)
        self.pair_bias = nn.Parameter(torch.zeros(pair_dim))

    def forward(self, single: torch.Tensor) -> torch.Tensor:
        """single: [B, L, D] -> pair: [B, L, L, pair_dim]"""
        left = self.left_proj(single)   # [B, L, P]
        right = self.right_proj(single) # [B, L, P]
        pair = left.unsqueeze(2) + right.unsqueeze(1) + self.pair_bias
        return pair


class TriangleAttention(nn.Module):
    """Triangle attention from AlphaFold2 — attention over edges.

    Key insight: if residue i is close to j, and j is close to k,
    then i should be close to k. Triangle inequality as inductive bias.
    """

    def __init__(self, pair_dim: int = 128, n_heads: int = 4):
        super().__init__()
        self.norm = nn.LayerNorm(pair_dim)
        self.attn = nn.MultiheadAttention(pair_dim, n_heads, batch_first=True)

    def forward(self, pair: torch.Tensor) -> torch.Tensor:
        """pair: [B, L, L, C] -> [B, L, L, C] (attend along one axis)"""
        B, L, _, C = pair.shape
        # Attend along rows (starting node)
        pair_flat = pair.reshape(B * L, L, C)
        pair_flat = self.norm(pair_flat)
        out, _ = self.attn(pair_flat, pair_flat, pair_flat)
        return pair + out.reshape(B, L, L, C)


class DistancePredictor(nn.Module):
    """Predict inter-residue distance distribution."""

    def __init__(self, pair_dim: int = 128, n_bins: int = 64):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(pair_dim, pair_dim), nn.ReLU(),
            nn.Linear(pair_dim, n_bins),
        )

    def forward(self, pair: torch.Tensor) -> torch.Tensor:
        """pair: [B, L, L, C] -> [B, L, L, n_bins] distance distribution"""
        logits = self.head(pair)
        # Symmetrize: distance(i,j) = distance(j,i)
        logits = (logits + logits.transpose(1, 2)) / 2
        return logits


class StructurePrediction(nn.Module):
    """Simplified structure prediction pipeline."""

    def __init__(self, embed_dim: int = 256, pair_dim: int = 128,
                 n_layers: int = 4, n_bins: int = 64):
        super().__init__()
        self.embed = ResidueEmbedding(embed_dim=embed_dim)
        self.pairwise = PairwiseFeatures(embed_dim, pair_dim)

        self.single_layers = nn.ModuleList([
            nn.TransformerEncoderLayer(embed_dim, nhead=8, batch_first=True)
            for _ in range(n_layers)
        ])
        self.triangle_layers = nn.ModuleList([
            TriangleAttention(pair_dim) for _ in range(n_layers)
        ])
        self.dist_head = DistancePredictor(pair_dim, n_bins)

    def forward(self, sequence):
        single = self.embed(sequence)
        pair = self.pairwise(single)

        for s_layer, t_layer in zip(self.single_layers, self.triangle_layers):
            single = s_layer(single)
            pair = t_layer(pair)

        dist_logits = self.dist_head(pair)
        return dist_logits
```

Key patterns:
1. **Pairwise representation** — L×L matrix captures relationships between all residue pairs
2. **Triangle attention** — enforce geometric constraints (triangle inequality) through attention
3. **Distance binning** — predict distribution over distance bins rather than single value
4. **Symmetrization** — distance matrix must be symmetric; average logits with transpose
5. **MSA features** — production systems use multiple sequence alignment as additional input'''
    ),
    (
        "ai/molecular-generation",
        "Show molecular generation with AI: SMILES-based generation, graph neural networks for molecules, and property-guided optimization.",
        '''AI for molecular generation and optimization:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class MoleculeGNN(nn.Module):
    """Graph Neural Network for molecular property prediction.

    Molecules as graphs: atoms = nodes, bonds = edges.
    Message passing aggregates neighbor information.
    """

    def __init__(self, atom_features: int = 32, hidden_dim: int = 128,
                 n_layers: int = 3, n_properties: int = 1):
        super().__init__()
        self.atom_embed = nn.Linear(atom_features, hidden_dim)

        self.message_layers = nn.ModuleList([
            MessagePassingLayer(hidden_dim) for _ in range(n_layers)
        ])

        self.readout = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, n_properties),
        )

    def forward(self, atom_feats, edge_index, batch):
        """Predict molecular properties from graph."""
        h = self.atom_embed(atom_feats)

        for layer in self.message_layers:
            h = layer(h, edge_index)

        # Global readout: sum pooling over atoms per molecule
        mol_feats = scatter_sum(h, batch, dim=0)
        return self.readout(mol_feats)


class MessagePassingLayer(nn.Module):
    """MPNN layer: aggregate neighbor messages and update node features."""

    def __init__(self, dim: int):
        super().__init__()
        self.message_fn = nn.Sequential(
            nn.Linear(dim * 2, dim), nn.ReLU(),
            nn.Linear(dim, dim),
        )
        self.update_fn = nn.GRUCell(dim, dim)
        self.norm = nn.LayerNorm(dim)

    def forward(self, h, edge_index):
        src, dst = edge_index
        # Compute messages from neighbors
        messages = self.message_fn(torch.cat([h[src], h[dst]], dim=-1))
        # Aggregate messages for each node
        agg = scatter_sum(messages, dst, dim=0, dim_size=h.shape[0])
        # Update node features
        h_new = self.update_fn(agg, h)
        return self.norm(h_new)


def scatter_sum(src, index, dim=0, dim_size=None):
    """Sum pooling by index (like torch_scatter)."""
    if dim_size is None:
        dim_size = index.max().item() + 1
    out = torch.zeros(dim_size, *src.shape[1:], device=src.device)
    return out.scatter_add_(dim, index.unsqueeze(-1).expand_as(src), src)


class PropertyGuidedGenerator:
    """Generate molecules optimized for target properties."""

    def __init__(self, predictor: MoleculeGNN, vocab_size: int = 100):
        self.predictor = predictor
        self.generator = nn.GRU(vocab_size, 256, batch_first=True)
        self.output = nn.Linear(256, vocab_size)

    def guided_generation(self, target_property: float,
                          n_candidates: int = 100) -> list:
        """Generate SMILES and filter by predicted property."""
        candidates = []
        for _ in range(n_candidates):
            smiles = self._sample_smiles()
            mol_graph = smiles_to_graph(smiles)
            if mol_graph is not None:
                pred = self.predictor(mol_graph.atom_feats,
                                       mol_graph.edge_index,
                                       mol_graph.batch)
                candidates.append((smiles, pred.item()))

        # Rank by closeness to target
        candidates.sort(key=lambda x: abs(x[1] - target_property))
        return candidates[:10]
```

Key patterns:
1. **Message passing** — nodes aggregate information from neighbors; captures local chemical structure
2. **GRU update** — gated update preserves information across message passing rounds
3. **Global readout** — sum/mean pooling over atoms gives fixed-size molecular representation
4. **SMILES generation** — autoregressive string generation; validate chemistry post-generation
5. **Property-guided** — use property predictor to filter/rank generated molecules'''
    ),
    (
        "ai/scientific-ml",
        "Show scientific machine learning: physics-informed neural networks (PINNs), neural ODEs, and surrogate models for simulation.",
        '''Scientific machine learning — physics-informed models:

```python
import torch
import torch.nn as nn


class PINN(nn.Module):
    """Physics-Informed Neural Network.

    Learn solution to PDEs by encoding physics in the loss function.
    No labeled data needed — physics provides supervision.

    Example: Heat equation u_t = α * u_xx
    """

    def __init__(self, hidden_dim: int = 64, n_layers: int = 4):
        super().__init__()
        layers = [nn.Linear(2, hidden_dim), nn.Tanh()]  # input: (x, t)
        for _ in range(n_layers - 1):
            layers.extend([nn.Linear(hidden_dim, hidden_dim), nn.Tanh()])
        layers.append(nn.Linear(hidden_dim, 1))  # output: u(x, t)
        self.net = nn.Sequential(*layers)

    def forward(self, x, t):
        inputs = torch.cat([x, t], dim=-1)
        return self.net(inputs)

    def physics_loss(self, x, t, alpha=0.01):
        """PDE residual loss: enforce u_t = α * u_xx."""
        x.requires_grad_(True)
        t.requires_grad_(True)

        u = self(x, t)

        # Automatic differentiation for PDE terms
        u_t = torch.autograd.grad(u, t, torch.ones_like(u), create_graph=True)[0]
        u_x = torch.autograd.grad(u, x, torch.ones_like(u), create_graph=True)[0]
        u_xx = torch.autograd.grad(u_x, x, torch.ones_like(u_x), create_graph=True)[0]

        # PDE residual: u_t - α * u_xx = 0
        residual = u_t - alpha * u_xx
        return (residual ** 2).mean()

    def boundary_loss(self, x_bc, t_bc, u_bc):
        """Boundary/initial condition loss."""
        u_pred = self(x_bc, t_bc)
        return ((u_pred - u_bc) ** 2).mean()


class NeuralODE(nn.Module):
    """Neural ODE: learn continuous dynamics dx/dt = f(x, t).

    Uses ODE solver for forward pass; adjoint method for backprop.
    Memory-efficient: O(1) memory regardless of integration steps.
    """

    def __init__(self, state_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.dynamics = nn.Sequential(
            nn.Linear(state_dim + 1, hidden_dim), nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim), nn.Tanh(),
            nn.Linear(hidden_dim, state_dim),
        )

    def forward_dynamics(self, t, x):
        """dx/dt = f(x, t)"""
        t_expanded = t.expand(x.shape[0], 1)
        return self.dynamics(torch.cat([x, t_expanded], dim=-1))

    def integrate(self, x0, t_span, n_steps: int = 100):
        """Simple Euler integration (use torchdiffeq in production)."""
        dt = (t_span[1] - t_span[0]) / n_steps
        x = x0
        trajectory = [x]
        t = t_span[0]

        for _ in range(n_steps):
            dx = self.forward_dynamics(torch.tensor([t]), x)
            x = x + dx * dt
            t += dt
            trajectory.append(x)

        return torch.stack(trajectory)


class SurrogateModel(nn.Module):
    """Neural surrogate for expensive simulations.

    Train on simulation outputs, then use for fast inference.
    1000-10000x speedup over full simulation.
    """

    def __init__(self, input_dim: int, output_dim: int, hidden: int = 256):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, output_dim),
        )
        self.uncertainty = nn.Linear(hidden, output_dim)

    def forward(self, params):
        h = self.encoder(params)
        prediction = self.decoder(h)
        log_var = self.uncertainty(h)
        return prediction, log_var

    def loss(self, params, targets):
        pred, log_var = self(params)
        # Negative log likelihood with learned uncertainty
        nll = 0.5 * (torch.exp(-log_var) * (pred - targets)**2 + log_var)
        return nll.mean()
```

Key patterns:
1. **Physics loss** — PDE residual via autograd; no labeled data needed, physics supervises
2. **Boundary conditions** — separate loss term enforces initial/boundary values
3. **Neural ODE** — learn continuous dynamics; constant memory via adjoint method
4. **Tanh activation** — smooth activation for smooth solutions; ReLU causes kinks in derivatives
5. **Uncertainty estimation** — surrogate outputs mean + variance; know when to fall back to simulation'''
    ),
]
