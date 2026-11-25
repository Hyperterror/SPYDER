"""
Sentence Transformer Embedding Generator and Cache.
Computes contextual text embeddings strictly from observable person attributes
using sentence-transformers/all-MiniLM-L6-v2.
"""

import hashlib
import pickle
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

from entity_resolution.config import EMBEDDING_MODEL_NAME, EMBEDDING_CACHE_FILE


class _DeterministicHashEncoder:
    """
    Deterministic pure-NumPy fallback encoder when sentence_transformers or local
    HF weights are unavailable (e.g., airgapped or lightweight worker environments).
    Produces normalized 384-d n-gram + token projections compatible with MiniLM dim.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def encode(self, text: str, normalize_embeddings: bool = True) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        clean = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        tokens = clean.split()
        grams: List[str] = list(tokens)
        for tok in tokens:
            for n in (3, 4):
                if len(tok) >= n:
                    for i in range(len(tok) - n + 1):
                        grams.append(tok[i : i + n])
        for g in grams:
            digest = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            weight = 2.0 if g in tokens else 1.0
            vec[idx] += sign * weight
        if normalize_embeddings:
            norm = float(np.linalg.norm(vec))
            if norm > 0.0:
                vec = vec / norm
        return vec


class EmbeddingManager:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, cache_path: Path = EMBEDDING_CACHE_FILE):
        self.model_name = model_name
        self.cache_path = Path(cache_path)
        self.model = None
        self.cache: Dict[str, np.ndarray] = {}
        self._load_cache()

    def _load_cache(self):
        """Loads cached embeddings from disk if available."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "rb") as f:
                    self.cache = pickle.load(f)
            except Exception:
                self.cache = {}

    def save_cache(self):
        """Persists cached embeddings to disk."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "wb") as f:
            pickle.dump(self.cache, f)

    def _get_model(self):
        """Lazy loader for SentenceTransformer model with offline deterministic fallback."""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
            except Exception:
                self.model = _DeterministicHashEncoder(dim=384)
        return self.model

    def build_text_payload(self, profile: Dict[str, Any]) -> str:
        """
        Builds observable descriptive text for sentence embedding.
        Strictly excludes any hidden ground truth tokens.
        """
        alias_part = f" (also known as {profile['raw_alias']})" if profile.get("raw_alias") else ""
        occ_part = f", working as {profile['occupation']}" if profile.get("occupation") else ""
        role_part = f", dossier status: {profile['role']}" if profile.get("role") else ""
        addr_part = f", associated address: {profile['address']}" if profile.get("address") else ""

        text = f"Subject: {profile['raw_name']}{alias_part}{occ_part}{role_part}{addr_part}."
        return text

    def get_embedding(self, person_id: str, profile: Dict[str, Any]) -> np.ndarray:
        """Retrieves or computes the embedding vector for a given person profile."""
        if person_id in self.cache:
            return self.cache[person_id]

        text = self.build_text_payload(profile)
        model = self._get_model()
        try:
            vec = model.encode(text, normalize_embeddings=True)
        except Exception:
            self.model = _DeterministicHashEncoder(dim=384)
            vec = self.model.encode(text, normalize_embeddings=True)
        self.cache[person_id] = np.array(vec, dtype=np.float32)
        return self.cache[person_id]

    def compute_cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Computes cosine similarity between two normalized embedding vectors."""
        if vec1 is None or vec2 is None:
            return 0.0
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        sim = float(np.dot(vec1, vec2) / (norm1 * norm2))
        return max(-1.0, min(1.0, sim))

    def get_similarity_for_pair(self, pid_a: str, profile_a: Dict[str, Any], pid_b: str, profile_b: Dict[str, Any]) -> float:
        """Gets cosine similarity for a pair of person profiles."""
        vec_a = self.get_embedding(pid_a, profile_a)
        vec_b = self.get_embedding(pid_b, profile_b)
        return self.compute_cosine_similarity(vec_a, vec_b)
