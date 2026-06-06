# Surrogate Regression Fixtures

Tiny surrogate regression fixtures belong here. These are for Feature 001 tests
that verify the ported inference service reproduces known outputs from
`boreyes2026`.

Suggested layout:

- `case_01_inputs.npz`
- `case_01_expected.npz`
- `manifest.json`

Keep these fixtures small and reviewable. Full-field paper-validation cases
belong in `data/validation_cases/` and are ignored.
