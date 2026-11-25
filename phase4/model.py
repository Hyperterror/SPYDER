"""
GraphSAGE Neural Network Architecture and Link Decoders for Phase 4.
Implements native PyTorch 2-layer GraphSAGE encoder with mean aggregation,
along with Dot-Product, Cosine, and MLP link decoders.
"""

import math
from typing import Dict, List, Any, Optional
import torch
import torch.nn as nn
import torch.nn.functional as F

from phase4.config import HIDDEN_DIM, EMBED_DIM, DROPOUT

class GraphSAGELayer(nn.Module):
    def __init__(self, in_features: int, out_features: int, dropout: float = DROPOUT):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.dropout = nn.Dropout(dropout)

        # Transformation for self-node and aggregated neighborhood
        self.linear_self = nn.Linear(in_features, out_features, bias=False)
        self.linear_neigh = nn.Linear(in_features, out_features, bias=False)
        self.bias = nn.Parameter(torch.zeros(out_features))

        self.layer_norm = nn.LayerNorm(out_features)
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.linear_self.weight)
        nn.init.xavier_uniform_(self.linear_neigh.weight)
        nn.init.zeros_(self.bias)

    def forward(self, x: torch.Tensor, norm_adj: torch.Tensor) -> torch.Tensor:
        """
        x: [N, in_features]
        norm_adj: [N, N] row-normalized adjacency matrix
        """
        # Neighborhood aggregation
        h_neigh = torch.matmul(norm_adj, x)
        
        # Transform and combine
        out_self = self.linear_self(x)
        out_neigh = self.linear_neigh(h_neigh)
        h = out_self + out_neigh + self.bias
        
        h = self.layer_norm(h)
        h = F.relu(h)
        h = self.dropout(h)
        return h

class GraphSAGEEncoder(nn.Module):
    def __init__(
        self,
        in_dim: int,
        hidden_dim: int = HIDDEN_DIM,
        embed_dim: int = EMBED_DIM,
        dropout: float = DROPOUT
    ):
        super().__init__()
        self.layer1 = GraphSAGELayer(in_dim, hidden_dim, dropout=dropout)
        self.layer2 = GraphSAGELayer(hidden_dim, embed_dim, dropout=0.0)  # Output embedding layer

    def forward(self, x: torch.Tensor, norm_adj: torch.Tensor) -> torch.Tensor:
        h1 = self.layer1(x, norm_adj)
        z = self.layer2(h1, norm_adj)
        # L2 normalize embeddings for stable geometric distances
        z = F.normalize(z, p=2, dim=-1)
        return z

# ----------------- Link Decoders -----------------

class DotProductDecoder(nn.Module):
    """Computes calibrated sigmoid of dot product between node embeddings."""
    def __init__(self):
        super().__init__()
        self.logit_scale = nn.Parameter(torch.tensor(2.0))
        self.logit_bias = nn.Parameter(torch.tensor(-1.5))

    def forward(self, z_u: torch.Tensor, z_v: torch.Tensor) -> torch.Tensor:
        # z_u, z_v: [B, embed_dim]
        dot = (z_u * z_v).sum(dim=-1)
        return torch.sigmoid(dot * self.logit_scale + self.logit_bias)

class CosineDecoder(nn.Module):
    """Computes calibrated scaled cosine similarity between embeddings."""
    def __init__(self, scale: float = 4.0):
        super().__init__()
        self.logit_scale = nn.Parameter(torch.tensor(float(scale)))
        self.logit_bias = nn.Parameter(torch.tensor(-2.0))

    def forward(self, z_u: torch.Tensor, z_v: torch.Tensor) -> torch.Tensor:
        cos = F.cosine_similarity(z_u, z_v, dim=-1)
        return torch.sigmoid(cos * self.logit_scale + self.logit_bias)

class MLPDecoder(nn.Module):
    """Multi-Layer Perceptron link decoder over concatenated and Hadamard representations."""
    def __init__(self, embed_dim: int = EMBED_DIM, hidden_dim: int = 32):
        super().__init__()
        # Features: [z_u, z_v, z_u * z_v, |z_u - z_v|] -> 4 * embed_dim
        in_dim = embed_dim * 4
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(self, z_u: torch.Tensor, z_v: torch.Tensor) -> torch.Tensor:
        cat_feats = torch.cat([z_u, z_v, z_u * z_v, torch.abs(z_u - z_v)], dim=-1)
        logits = self.net(cat_feats).squeeze(-1)
        return torch.sigmoid(logits)

# ----------------- Full Model Wrapper -----------------

class GraphSAGEModel(nn.Module):
    def __init__(
        self,
        in_dim: int,
        hidden_dim: int = HIDDEN_DIM,
        embed_dim: int = EMBED_DIM,
        decoder_type: str = "mlp",
        dropout: float = DROPOUT
    ):
        super().__init__()
        self.encoder = GraphSAGEEncoder(in_dim, hidden_dim, embed_dim, dropout)
        self.decoder_type = decoder_type.lower()
        
        if self.decoder_type == "dot":
            self.decoder = DotProductDecoder()
        elif self.decoder_type == "cosine":
            self.decoder = CosineDecoder()
        else:
            self.decoder = MLPDecoder(embed_dim)

    def encode(self, x: torch.Tensor, norm_adj: torch.Tensor) -> torch.Tensor:
        return self.encoder(x, norm_adj)

    def decode(self, z: torch.Tensor, u_indices: torch.Tensor, v_indices: torch.Tensor) -> torch.Tensor:
        z_u = z[u_indices]
        z_v = z[v_indices]
        return self.decoder(z_u, z_v)

    def forward(
        self,
        x: torch.Tensor,
        norm_adj: torch.Tensor,
        u_indices: torch.Tensor,
        v_indices: torch.Tensor
    ) -> torch.Tensor:
        z = self.encode(x, norm_adj)
        return self.decode(z, u_indices, v_indices)
