"""
Training Engine for Phase 4 GraphSAGE Model.
Trains 2-layer GraphSAGE encoder with Link Decoders (comparing MLP, Dot-Product, and Cosine),
evaluating on validation splits, tracking loss history, and saving model checkpoints.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_fscore_support

from phase4.config import (
    OUTPUT_DIR, MODEL_DIR, HIDDEN_DIM, EMBED_DIM, DROPOUT,
    LEARNING_RATE, WEIGHT_DECAY, NUM_EPOCHS, RANDOM_SEED
)
from phase4.graph_loader import GraphLoader
from phase4.features import FeatureExtractor
from phase4.candidate_generation import CandidateGenerator
from phase4.split import DataSplitter
from phase4.model import GraphSAGEModel

def set_seed(seed: int = RANDOM_SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

class GraphSAGETrainer:
    def __init__(self, random_seed: int = RANDOM_SEED):
        set_seed(random_seed)
        self.seed = random_seed
        self.output_dir = Path(OUTPUT_DIR)
        self.model_dir = Path(MODEL_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.loader = GraphLoader()
        self.multi_graph = self.loader.load_graph()
        self.norm_adj = self.loader.build_normalized_adj()

        self.extractor = FeatureExtractor()
        self.x, self.feature_names = self.extractor.extract_node_features(
            self.multi_graph, self.loader.node_to_idx
        )

        self.candidate_gen = CandidateGenerator(self.multi_graph, random_seed=random_seed)
        self.candidates = self.candidate_gen.generate_all_candidates()

        self.splitter = DataSplitter(self.candidates, random_seed=random_seed)
        self.case_split = self.splitter.create_case_aware_split()
        self.entity_split = self.splitter.create_entity_disjoint_split()
        self.hard_negatives = self.splitter.extract_hard_negative_evaluation_set()

    def _prepare_tensors(self, pairs: List[Dict[str, Any]]) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Converts pair dictionaries into index and label tensors."""
        u_idx = [self.loader.node_to_idx[p["source"]] for p in pairs]
        v_idx = [self.loader.node_to_idx[p["target"]] for p in pairs]
        labels = [float(p["label"]) for p in pairs]
        return (
            torch.tensor(u_idx, dtype=torch.long),
            torch.tensor(v_idx, dtype=torch.long),
            torch.tensor(labels, dtype=torch.float32)
        )

    def train_decoder_comparison(self) -> Dict[str, Any]:
        """
        Trains and compares Dot-Product, Cosine, and MLP decoders on the validation set
        to select the best architecture configuration.
        """
        train_pairs = self.case_split["train_pairs"]
        val_pairs = self.case_split["val_pairs"]

        u_tr, v_tr, y_tr = self._prepare_tensors(train_pairs)
        u_va, v_va, y_val = self._prepare_tensors(val_pairs)

        decoder_types = ["mlp", "dot", "cosine"]
        comparison_results = {}
        best_val_prauc = -1.0
        best_decoder = "mlp"

        in_dim = self.x.shape[1]

        for dec_type in decoder_types:
            set_seed(self.seed)
            model = GraphSAGEModel(
                in_dim=in_dim,
                hidden_dim=HIDDEN_DIM,
                embed_dim=EMBED_DIM,
                decoder_type=dec_type,
                dropout=DROPOUT
            )
            optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
            criterion = nn.BCELoss()

            for epoch in range(1, NUM_EPOCHS + 1):
                model.train()
                optimizer.zero_grad()
                preds = model(self.x, self.norm_adj, u_tr, v_tr)
                loss = criterion(preds, y_tr)
                loss.backward()
                optimizer.step()

            # Evaluate on Validation
            model.eval()
            with torch.no_grad():
                val_preds = model(self.x, self.norm_adj, u_va, v_va).numpy()
                y_val_np = y_val.numpy()

            if len(np.unique(y_val_np)) > 1:
                roc = roc_auc_score(y_val_np, val_preds)
                prauc = average_precision_score(y_val_np, val_preds)
            else:
                roc, prauc = 0.5, 0.5

            comparison_results[dec_type] = {
                "val_roc_auc": round(float(roc), 4),
                "val_pr_auc": round(float(prauc), 4)
            }

            if prauc > best_val_prauc:
                best_val_prauc = prauc
                best_decoder = dec_type

        comparison_results["selected_decoder"] = best_decoder
        return comparison_results

    def train_final_model(self, decoder_type: str = "mlp") -> Tuple[GraphSAGEModel, Dict[str, Any]]:
        """
        Trains the final GraphSAGE model on the full training split with the selected decoder,
        records epoch-by-epoch loss history, and exports trained embeddings and model weights.
        """
        set_seed(self.seed)
        in_dim = self.x.shape[1]

        model = GraphSAGEModel(
            in_dim=in_dim,
            hidden_dim=HIDDEN_DIM,
            embed_dim=EMBED_DIM,
            decoder_type=decoder_type,
            dropout=DROPOUT
        )
        optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
        criterion = nn.BCELoss()

        train_pairs = self.case_split["train_pairs"]
        u_tr, v_tr, y_tr = self._prepare_tensors(train_pairs)

        loss_history = []
        for epoch in range(1, NUM_EPOCHS + 1):
            model.train()
            optimizer.zero_grad()
            preds = model(self.x, self.norm_adj, u_tr, v_tr)
            loss = criterion(preds, y_tr)
            loss.backward()
            optimizer.step()

            loss_history.append(round(float(loss.item()), 5))

        # Save model state
        model_path = self.model_dir / "graphsage_model.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "in_dim": in_dim,
            "hidden_dim": HIDDEN_DIM,
            "embed_dim": EMBED_DIM,
            "decoder_type": decoder_type,
            "feature_names": self.feature_names
        }, model_path)

        train_metrics = {
            "num_epochs": NUM_EPOCHS,
            "final_train_loss": loss_history[-1],
            "initial_train_loss": loss_history[0],
            "loss_history": loss_history,
            "training_pairs_count": len(train_pairs),
            "feature_dim": in_dim,
            "embedding_dim": EMBED_DIM,
            "selected_decoder": decoder_type
        }

        # Save training metrics JSON
        with open(self.output_dir / "train_metrics.json", mode="w", encoding="utf-8") as f:
            json.dump(train_metrics, f, indent=2)

        return model, train_metrics
