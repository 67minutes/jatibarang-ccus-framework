# Machine-local import store

This directory holds derived runtime artifacts for reservoir, terrain, and road
imports. Its payloads are machine-local state and are ignored by Git; only this
README is tracked.

Imported files use content-addressed directories:

```text
data/imports/
├── terrain_registry.json
├── roads_registry.json
└── <sha16>/
    ├── <original file>
    ├── roads_graph.npz
    └── roads_layers.json
```

- `<sha16>/<original file>` is the copied source artifact, addressed by the
  first 16 hexadecimal characters of its SHA-256 digest.
- `terrain_registry.json` indexes imported terrain metadata and cached layer
  references.
- `roads_registry.json` indexes imported OSM road networks.
- `roads_graph.npz` stores the clipped routing graph arrays used by the backend.
- `roads_layers.json` stores simplified map geometry used by the frontend.

Study memos do not embed these payloads. They reference imported artifacts by
stable ID and full SHA-256 digest, allowing the application to verify and relink
files that are still present here. Copy the required import-store artifacts with
a memo when moving a study to another machine; otherwise the memo remains
readable but the missing inputs must be re-imported before screening again.
