# Machine-local import store

This directory holds derived runtime artifacts for reservoir, terrain, screening
spatial fields, and road imports. Payloads are machine-local state and are ignored
by Git; only this README is tracked. The raw 177-case MRST corpus is never copied
here.

The content-addressed layout is:

```text
data/imports/
|-- terrain_registry.json
|-- roads_registry.json
|-- downloads/
|   `-- java-260717.osm.pbf
`-- <sha16>/
    |-- <copied terrain or reservoir artifact>
    |-- screening-spatial.json.gz
    |-- roads_graph.npz
    `-- roads_layers.json
```

- `<sha16>/<artifact>` is addressed by the first 16 hexadecimal characters of
  its full SHA-256 digest.
- `terrain_registry.json` indexes terrain metadata and cached layer references.
- `roads_registry.json` records the source hash, padded terrain bounding box,
  graph/layer counts, and cache schema for imported OSM networks.
- `roads_graph.npz` is the full clipped connected routing graph used by the
  optimizer. Cache schema 4 stores compact NumPy/CSR arrays rather than a
  province-scale NetworkX object; it is distinct from the display sample.
- `roads_layers.json` is a deterministic cartographic sample capped at 4,000
  major and 4,000 minor polylines plus 250 place labels. The frontend batches
  each line class into one draw call; route calculations still use every
  retained graph edge.
- `bounded_locations_<bbox12>.idx` is a transient disk-backed pyosmium join index containing
  only nodes inside the padded terrain extent. It prevents a Java-wide in-memory
  node map. The verified Java import's 2.36 GB index was removed after the NPZ,
  layers, and exact paths passed validation. It can be regenerated from the
  retained PBF and is not required for routing or display.
- `screening-spatial.json.gz` contains only retained top-K dynamic result fields.
  Memo v4 references it by artifact ID, full SHA-256, and request fingerprint.

The local Java source is the official [Geofabrik Java extract](https://download.geofabrik.de/asia/indonesia/java.html)
(`java-260717.osm.pbf`), distributed under the OpenStreetMap ODbL terms. Its
downloaded size is 894,664,667 bytes and its verified MD5 is
`BA8CAFF24817408C76B2333BAA205BCD`; SHA-256 is
`3A57EA2910F5F1619368EB3ADCB9F76097B1600AF4EC395BFE3EEED91393DBE0`.
The registered `roads-3a57ea2910f5f161` cache contains 8,599,655 nodes and
8,900,434 undirected edges. Its 253,859,461-byte CSR graph accompanies 4,000
major and 4,000 minor display roads, 391 coastline lines, and 250 place labels.
Exact Subang-to-W01-W20 paths carry 1,656-2,907 graph points and span
76.061-98.564 km. The PBF remains under the ignored downloads folder; the routing
graph and display layers are derived caches.

Study memos do not embed these payloads. They reference imported artifacts by
stable ID and full SHA-256 digest, allowing the application to verify and relink
files that remain here. Copy the required import-store artifacts with a memo when
moving a study to another machine; otherwise the memo stays readable but its
missing inputs must be re-imported before screening again.
