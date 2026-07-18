# Bundled Earth assets

These files are bundled for the workbench's fully offline Earth view. Runtime
rendering makes no requests to tile, imagery, or map services.

- `blue_marble_2048.jpg` — NASA Visible Earth, *Blue Marble: Land Surface,
  Shallow Water, and Shaded Topography*, 2048 × 1024 image. Downloaded
  2026-07-18 from
  `https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57752/land_shallow_topo_2048.jpg`.
  NASA is credited as the source; this informational use follows NASA's Images
  and Media Usage Guidelines (NASA content is generally not subject to U.S.
  copyright, but NASA identifiers and endorsement remain restricted).
- `ne_50m_coastline.json` — Natural Earth 1:50m coastline, whose map data are
  public domain. Downloaded 2026-07-18 from the `nvkelso/natural-earth-vector`
  GeoJSON distribution and simplified by `tools/earth/simplify_coastline.py`
  with a 0.1-degree tolerance.

Both visual layers are optional at runtime. If either same-origin static fetch
fails, the globe remains usable with its fallback surface, graticule, and
registered-terrain footprints.
