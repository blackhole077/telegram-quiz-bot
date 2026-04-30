"""Migrate questions.json to v2 schema.

Changes applied:
- Each reference gains ``source_type: "paper"`` (all existing refs are papers).
- Each question gains ``domain`` inferred from topic; falls back to ``""``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "data" / "questions.json"

_TOPIC_DOMAIN: dict[str, str] = {
    # reinforcement_learning
    "C51": "reinforcement_learning",
    "DQN": "reinforcement_learning",
    "Double DQN": "reinforcement_learning",
    "Dueling DQN": "reinforcement_learning",
    "GAE": "reinforcement_learning",
    "NoisyNets": "reinforcement_learning",
    "Options": "reinforcement_learning",
    "PAIRED": "reinforcement_learning",
    "PER": "reinforcement_learning",
    "PLR future work": "reinforcement_learning",
    "PLR vs PER — IS correction": "reinforcement_learning",
    "PLR — L1 value loss vs TD error": "reinforcement_learning",
    "PLR — PER analogy": "reinforcement_learning",
    "PLR — catastrophic interference": "reinforcement_learning",
    "PLR — emergent curriculum": "reinforcement_learning",
    "PLR — final mixture": "reinforcement_learning",
    "PLR — hyperparameter design principle": "reinforcement_learning",
    "PLR — rank prioritization": "reinforcement_learning",
    "PLR — score distribution temperature": "reinforcement_learning",
    "PLR — staleness distribution": "reinforcement_learning",
    "PLR — staleness purpose": "reinforcement_learning",
    "PLR — value correction hypothesis": "reinforcement_learning",
    "Rainbow": "reinforcement_learning",
    "TRPO": "reinforcement_learning",
    "log-derivative trick": "reinforcement_learning",
    # speech_ml
    "ContextNet SE layer": "speech_ml",
    "ContextNet skip connection": "speech_ml",
    "HuBERT BERT-like loss": "speech_ml",
    "HuBERT architecture": "speech_ml",
    "HuBERT fine-tuning": "speech_ml",
    "HuBERT iterative refinement": "speech_ml",
    "HuBERT loss function": "speech_ml",
    "HuBERT masking": "speech_ml",
    "HuBERT offline clustering": "speech_ml",
    "HuBERT pseudo-labeling": "speech_ml",
    "HuBERT self-supervised learning": "speech_ml",
    "VITS normalizing flow": "speech_ml",
    "VITS prior at inference": "speech_ml",
    "neural vocoder motivation": "speech_ml",
    "phase and DFT": "speech_ml",
    "phase problem": "speech_ml",
    "reconstruction loss mel-spectrogram": "speech_ml",
    "spectral loss": "speech_ml",
    # generative_models
    "GAN motivation": "generative_models",
    "VAE ELBO tension": "generative_models",
    "VAE KL direction": "generative_models",
    "VAE KL regularization": "generative_models",
    "VAE encoder": "generative_models",
    "VAE generation": "generative_models",
    "VAE latent space": "generative_models",
    "VAE prior": "generative_models",
    "VAE reconstruction vs KL tension": "generative_models",
    "reparameterization trick": "generative_models",
    # probability
    "CDF": "probability",
    "Expectation": "probability",
    "KL divergence asymmetry": "probability",
    "KL divergence bounds": "probability",
    "KL divergence formula": "probability",
    "KL divergence zero": "probability",
    "KL weighting": "probability",
    "KL weighting near zero": "probability",
    "Random Variables": "probability",
    "Variance": "probability",
    "prior vs posterior": "probability",
    # linear_algebra
    "Vector Projections": "linear_algebra",
    "dot product magnitude": "linear_algebra",
    "inner product": "linear_algebra",
    "inner product axioms": "linear_algebra",
    "linearity": "linear_algebra",
    "matrix geometry": "linear_algebra",
    "norm": "linear_algebra",
    "orthogonality": "linear_algebra",
    "projection geometry": "linear_algebra",
    "scalar projection": "linear_algebra",
    "vector projection formula": "linear_algebra",
    # deep_learning
    "attention and dot product": "deep_learning",
    "attention mechanism": "deep_learning",
    "attention scaling": "deep_learning",
    "nonlinearity and depth": "deep_learning",
    "universal approximation theorem": "deep_learning",
}


def migrate(path: Path) -> None:
    data = json.loads(path.read_text())
    unrecognised: set[str] = set()
    for question in data:
        topic = question.get("topic", "")
        question["domain"] = _TOPIC_DOMAIN.get(topic, "")
        if not question["domain"]:
            unrecognised.add(topic)
        for ref in question.get("references", []):
            if "source_type" not in ref:
                ref["source_type"] = "paper"
    path.write_text(json.dumps(data, indent=2))
    print(f"Written {len(data)} questions to {path}")
    if unrecognised:
        print(f"WARNING: no domain assigned for topics: {sorted(unrecognised)}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    migrate(target)
