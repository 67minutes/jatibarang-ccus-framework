from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

PROMOTED_CHECKPOINT = (
    REPO_ROOT
    / "models"
    / "checkpoints"
    / "model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0.pt"
)

PROMOTED_CHECKPOINT_SHA256 = "7A685C7EDB99BF00F6075D6DE4AA55EF2F4A7D8CC7F93ABB7B37A6359885566B"

UPSTREAM_BOREYES_ROOT = Path(r"C:\Users\mauli\Documents\boreyes2026")
UPSTREAM_METRICS = (
    UPSTREAM_BOREYES_ROOT
    / "outputs"
    / "model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0_metrics.json"
)
UPSTREAM_TRAIN_SUMMARY = (
    UPSTREAM_BOREYES_ROOT
    / "outputs"
    / "model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0_train.json"
)
UPSTREAM_FINAL_MANIFEST = UPSTREAM_BOREYES_ROOT / "exports_hnp_expressive" / "final" / "manifest.json"


@dataclass(frozen=True)
class ChannelContract:
    tin: int = 8
    stored_dynamic_channels: int = 20
    forward_dynamic_channels: int = 13
    static_channels: int = 12
    spatial_channels: int = 4
    production_delta_channels: int = 2
    output_contract: str = "production_v2"


CHANNEL_CONTRACT = ChannelContract()

