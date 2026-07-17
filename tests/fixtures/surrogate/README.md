# Surrogate Regression Fixtures

Tiny surrogate regression fixtures belong here. These are for Feature 001 tests
that verify the ported inference service reproduces known outputs from
`boreyes2026`.

Current layout:

- `case_0016_inputs.npz` and `case_0016_expected.npz`
- `case_0115_inputs.npz` and `case_0115_expected.npz`
- `case_0197_inputs.npz` and `case_0197_expected.npz`
- `manifest.json`

Keep these fixtures small and reviewable. Full-field paper-validation cases
belong in `data/validation_cases/` and are ignored.

The three physical-input fixtures verify static/dynamic tensor identity within
`1e-6`. Case 0016 also pins a 24-step scheduled rollout; its current single-scenario
output matches the saved upstream arrays exactly. The fixture manifest records source
identity and derivation without copying the 177-case MRST corpus.
