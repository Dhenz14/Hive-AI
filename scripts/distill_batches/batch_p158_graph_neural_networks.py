"""Graph Neural Networks — GCN, GAT, message passing, and applications."""

PAIRS = [
    (
        "ai/gnn-message-passing",
        "Show GNN message passing patterns: GCN, GAT, GraphSAGE, and node/edge/graph-level tasks with PyTorch Geometric.",
        '''Graph Neural Networks with PyTorch Geometric:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, GATv2Conv, SAGEConv, global_mean_pool
from torch_geometric.data import Data, DataLoader
from torch_geometric.utils import add_self_loops, degree


# === Graph Convolutional Network (GCN) ===

class GCN(nn.Module):
    """Graph Convolutional Network for node classification.

    Message passing: aggregate neighbor features, transform, combine.
    h_v^(l+1) = sigma(sum_{u in N(v)} (1/sqrt(d_v * d_u)) * W * h_u^(l))
    """

    def __init__(self, in_channels: int, hidden_channels: int, out_channels: int,
                 num_layers: int = 3, dropout: float = 0.5):
        super().__init__()
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()

        self.convs.append(GCNConv(in_channels, hidden_channels))
        self.norms.append(nn.BatchNorm1d(hidden_channels))

        for _ in range(num_layers - 2):
            self.convs.append(GCNConv(hidden_channels, hidden_channels))
            self.norms.append(nn.BatchNorm1d(hidden_channels))

        self.convs.append(GCNConv(hidden_channels, out_channels))
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for i, (conv, norm) in enumerate(zip(self.convs[:-1], self.norms)):
            x = conv(x, edge_index)
            x = norm(x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)

        x = self.convs[-1](x, edge_index)
        return x  # [num_nodes, out_channels]


# === Graph Attention Network (GAT) ===

class GAT(nn.Module):
    """GAT with multi-head attention on edges.

    Learns attention coefficients between neighbors:
    alpha_ij = softmax(LeakyReLU(a^T [Wh_i || Wh_j]))
    """

    def __init__(self, in_channels: int, hidden_channels: int, out_channels: int,
                 heads: int = 8, dropout: float = 0.6):
        super().__init__()
        self.conv1 = GATv2Conv(in_channels, hidden_channels, heads=heads, dropout=dropout)
        self.conv2 = GATv2Conv(hidden_channels * heads, out_channels, heads=1,
                                concat=False, dropout=dropout)
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.conv1(x, edge_index)
        x = F.elu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.conv2(x, edge_index)
        return x


# === GraphSAGE (inductive learning) ===

class GraphSAGE(nn.Module):
    """GraphSAGE: sample neighbors and aggregate for inductive learning.

    Unlike GCN/GAT, works on unseen nodes (inductive, not transductive).
    """

    def __init__(self, in_channels: int, hidden_channels: int, out_channels: int,
                 num_layers: int = 3):
        super().__init__()
        self.convs = nn.ModuleList()
        self.convs.append(SAGEConv(in_channels, hidden_channels))
        for _ in range(num_layers - 2):
            self.convs.append(SAGEConv(hidden_channels, hidden_channels))
        self.convs.append(SAGEConv(hidden_channels, out_channels))

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for conv in self.convs[:-1]:
            x = conv(x, edge_index)
            x = F.relu(x)
        return self.convs[-1](x, edge_index)


# === Graph-level classification (molecular property prediction) ===

class MoleculeClassifier(nn.Module):
    """Classify entire graphs (e.g., molecules) using GNN + pooling."""

    def __init__(self, in_channels: int, hidden_channels: int, num_classes: int):
        super().__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, hidden_channels)
        self.conv3 = GCNConv(hidden_channels, hidden_channels)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_channels, hidden_channels),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(hidden_channels, num_classes),
        )

    def forward(self, data: Data) -> torch.Tensor:
        x, edge_index, batch = data.x, data.edge_index, data.batch

        x = F.relu(self.conv1(x, edge_index))
        x = F.relu(self.conv2(x, edge_index))
        x = F.relu(self.conv3(x, edge_index))

        # Global mean pooling: aggregate all node features per graph
        x = global_mean_pool(x, batch)  # [num_graphs, hidden]

        return self.classifier(x)


# === Link prediction (knowledge graph completion) ===

class LinkPredictor(nn.Module):
    """Predict missing edges in a graph."""

    def __init__(self, in_channels: int, hidden_channels: int):
        super().__init__()
        self.encoder = GraphSAGE(in_channels, hidden_channels, hidden_channels)
        self.decoder = nn.Sequential(
            nn.Linear(hidden_channels * 2, hidden_channels),
            nn.ReLU(),
            nn.Linear(hidden_channels, 1),
        )

    def encode(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        return self.encoder(x, edge_index)

    def decode(self, z: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        src, dst = edge_index
        edge_features = torch.cat([z[src], z[dst]], dim=-1)
        return self.decoder(edge_features).squeeze(-1)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor,
                pos_edges: torch.Tensor, neg_edges: torch.Tensor) -> torch.Tensor:
        z = self.encode(x, edge_index)
        pos_scores = self.decode(z, pos_edges)
        neg_scores = self.decode(z, neg_edges)

        pos_loss = F.binary_cross_entropy_with_logits(pos_scores, torch.ones_like(pos_scores))
        neg_loss = F.binary_cross_entropy_with_logits(neg_scores, torch.zeros_like(neg_scores))
        return pos_loss + neg_loss


# === Build graph from data ===

def build_citation_graph(papers: list[dict], citations: list[tuple]) -> Data:
    """Build a PyG graph from paper data."""
    # Node features (e.g., bag-of-words or embeddings)
    x = torch.tensor([p["features"] for p in papers], dtype=torch.float)

    # Edge index (citation links)
    src = [c[0] for c in citations]
    dst = [c[1] for c in citations]
    edge_index = torch.tensor([src, dst], dtype=torch.long)

    # Labels
    y = torch.tensor([p["label"] for p in papers], dtype=torch.long)

    # Train/test masks
    num_nodes = len(papers)
    train_mask = torch.zeros(num_nodes, dtype=torch.bool)
    train_mask[:int(0.8 * num_nodes)] = True
    test_mask = ~train_mask

    return Data(x=x, edge_index=edge_index, y=y,
                train_mask=train_mask, test_mask=test_mask)
```

GNN task types:

| Task | Output | Pooling | Example |
|------|--------|---------|---------|
| **Node classification** | Per-node labels | None | Citation networks, social networks |
| **Link prediction** | Edge existence | Pair concat | Knowledge graphs, recommendations |
| **Graph classification** | Per-graph label | Global pool | Molecule properties, program analysis |
| **Node regression** | Per-node values | None | Traffic prediction, weather |

Key patterns:
1. **Message passing** — each node aggregates features from neighbors, transforms, and updates its representation
2. **GCN normalization** — `1/sqrt(d_i * d_j)` prevents high-degree nodes from dominating
3. **GAT attention** — learnable attention weights let the model focus on important neighbors
4. **GraphSAGE** — sample-and-aggregate for inductive learning (works on unseen nodes/graphs)
5. **Global pooling** — mean/max/sum over all node features for graph-level representations'''
    ),
    (
        "ai/gnn-applications",
        "Show GNN applications: recommendation systems, fraud detection, knowledge graph reasoning, and traffic prediction.",
        '''GNN real-world applications:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, HeteroConv, GATConv, global_mean_pool
from torch_geometric.data import HeteroData
from torch_geometric.transforms import RandomLinkSplit


# === Recommendation System (bipartite graph) ===

class RecommenderGNN(nn.Module):
    """User-Item recommendation via heterogeneous GNN.

    Graph: Users --interacts--> Items (bipartite)
    Features: user profile, item attributes
    Task: predict which items a user will interact with
    """

    def __init__(self, user_features: int, item_features: int,
                 hidden_dim: int = 128, num_layers: int = 3):
        super().__init__()
        self.user_embed = nn.Linear(user_features, hidden_dim)
        self.item_embed = nn.Linear(item_features, hidden_dim)

        # Heterogeneous convolutions (different for each edge type)
        self.convs = nn.ModuleList()
        for _ in range(num_layers):
            conv = HeteroConv({
                ("user", "interacts", "item"): SAGEConv(hidden_dim, hidden_dim),
                ("item", "rev_interacts", "user"): SAGEConv(hidden_dim, hidden_dim),
            }, aggr="sum")
            self.convs.append(conv)

    def forward(self, data: HeteroData) -> dict[str, torch.Tensor]:
        x_dict = {
            "user": self.user_embed(data["user"].x),
            "item": self.item_embed(data["item"].x),
        }

        for conv in self.convs:
            x_dict = conv(x_dict, data.edge_index_dict)
            x_dict = {key: F.relu(x) for key, x in x_dict.items()}

        return x_dict

    def predict_links(self, user_emb: torch.Tensor, item_emb: torch.Tensor,
                      edge_index: torch.Tensor) -> torch.Tensor:
        """Score user-item pairs."""
        src, dst = edge_index
        scores = (user_emb[src] * item_emb[dst]).sum(dim=-1)
        return torch.sigmoid(scores)


# === Fraud Detection (heterogeneous graph) ===

class FraudDetector(nn.Module):
    """Detect fraudulent transactions using graph structure.

    Graph nodes: Users, Merchants, Transactions, Devices
    Fraudsters create clusters of suspicious activity patterns.
    """

    def __init__(self, feature_dims: dict[str, int], hidden_dim: int = 64):
        super().__init__()
        self.encoders = nn.ModuleDict({
            node_type: nn.Linear(dim, hidden_dim)
            for node_type, dim in feature_dims.items()
        })

        self.conv1 = HeteroConv({
            ("user", "makes", "transaction"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("transaction", "at", "merchant"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("user", "uses", "device"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("transaction", "rev_makes", "user"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("merchant", "rev_at", "transaction"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("device", "rev_uses", "user"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
        }, aggr="sum")

        self.conv2 = HeteroConv({
            ("user", "makes", "transaction"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("transaction", "at", "merchant"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("transaction", "rev_makes", "user"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
            ("merchant", "rev_at", "transaction"): GATConv(hidden_dim, hidden_dim, heads=4, concat=False),
        }, aggr="sum")

        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, 1),  # Binary: fraud or not
        )

    def forward(self, data: HeteroData) -> torch.Tensor:
        x_dict = {
            node_type: self.encoders[node_type](data[node_type].x)
            for node_type in self.encoders
        }

        x_dict = {k: F.relu(v) for k, v in self.conv1(x_dict, data.edge_index_dict).items()}
        x_dict = {k: F.relu(v) for k, v in self.conv2(x_dict, data.edge_index_dict).items()}

        # Classify transactions as fraud/not fraud
        return self.classifier(x_dict["transaction"]).squeeze(-1)


# === Traffic Prediction (spatio-temporal graph) ===

class TrafficPredictor(nn.Module):
    """Predict traffic flow using spatial GNN + temporal sequence.

    Spatial: road network as graph (intersections = nodes, roads = edges)
    Temporal: historical traffic readings as time series
    """

    def __init__(self, num_nodes: int, in_steps: int = 12,
                 out_steps: int = 12, hidden_dim: int = 64):
        super().__init__()
        self.in_steps = in_steps
        self.out_steps = out_steps

        # Spatial encoding (GNN)
        self.spatial_conv1 = GATConv(in_steps, hidden_dim, heads=4, concat=False)
        self.spatial_conv2 = GATConv(hidden_dim, hidden_dim, heads=4, concat=False)

        # Temporal encoding (GRU)
        self.temporal = nn.GRU(hidden_dim, hidden_dim, num_layers=2, batch_first=True)

        # Prediction head
        self.output = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, out_steps),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """
        x: [batch, num_nodes, in_steps] — historical traffic readings
        edge_index: road network adjacency
        Returns: [batch, num_nodes, out_steps] — predicted traffic
        """
        batch_size, num_nodes, _ = x.shape

        # Spatial: GNN processes each timestep's spatial relationships
        x_flat = x.reshape(batch_size * num_nodes, self.in_steps)
        edge_batch = self._expand_edges(edge_index, batch_size, num_nodes)

        spatial = F.relu(self.spatial_conv1(x_flat, edge_batch))
        spatial = F.relu(self.spatial_conv2(spatial, edge_batch))
        spatial = spatial.reshape(batch_size, num_nodes, -1)

        # Temporal: GRU processes each node's temporal pattern
        temporal_out, _ = self.temporal(spatial.reshape(batch_size * num_nodes, 1, -1))
        temporal_out = temporal_out.reshape(batch_size, num_nodes, -1)

        return self.output(temporal_out)

    def _expand_edges(self, edge_index: torch.Tensor, batch_size: int,
                      num_nodes: int) -> torch.Tensor:
        """Expand edge_index for batched graphs."""
        offsets = torch.arange(batch_size, device=edge_index.device) * num_nodes
        edges = []
        for offset in offsets:
            edges.append(edge_index + offset)
        return torch.cat(edges, dim=1)
```

GNN application comparison:

| Application | Graph type | Node types | Task | Scale |
|-------------|-----------|-----------|------|-------|
| **Recommendation** | Bipartite | User, Item | Link prediction | Millions |
| **Fraud detection** | Heterogeneous | User, Transaction, Device | Node classification | Real-time |
| **Traffic** | Spatial-temporal | Intersection | Regression | City-scale |
| **Drug discovery** | Molecular | Atom | Graph classification | Thousands |

Key patterns:
1. **Heterogeneous graphs** — different node/edge types with separate learned transformations per type
2. **GAT for fraud** — attention highlights suspicious neighbor patterns that rule-based systems miss
3. **Bipartite GNN** — user-item interactions with message passing in both directions
4. **Spatio-temporal** — GNN for spatial structure + RNN/GRU for temporal dynamics
5. **Inductive learning** — GraphSAGE-based models generalize to unseen nodes (new users, new transactions)'''
    ),
]
