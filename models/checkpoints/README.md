# Model Checkpoints

PyTorch checkpoint binaries are stored here locally and ignored by git.

Current local checkpoint:

- File: `model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0.pt`
- Source: `C:\Users\mauli\Documents\boreyes2026\outputs\checkpoints\model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0.pt`
- SHA256: `7A685C7EDB99BF00F6075D6DE4AA55EF2F4A7D8CC7F93ABB7B37A6359885566B`
- Status: promoted checkpoint for this framework, confirmed by the user on
  2026-06-06. The markdown files in `boreyes2026` may still lag this decision.

Do not substitute another checkpoint unless the user explicitly changes the
promoted model.

The service verifies the hash before deserializing the checkpoint. A small tracked
derivative of the promoted one-step/T+5/T+10/T+11/T+24 accuracy metadata lives at
`models/metadata/production_v2_accuracy.json`; it contains no model weights or raw
training cases and is returned through `GET /model/info`.
