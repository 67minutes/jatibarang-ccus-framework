/**
 * Bake a small terrain heightmap from the SRTM GeoTIFF for the 3D viewport.
 *
 * The full raster (province-scale, tens of MB) can't be read in the browser, so
 * this offline step clips to the Jatibarang study extent, downsamples to a
 * modest mesh, and writes a compact JSON the viewport loads as a static asset.
 *
 * Run from the repo root:
 *   node frontend/scripts/bake-terrain.mjs
 *
 * Writes: frontend/public/assets/terrain.json
 */
import { fromFile } from "geotiff";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const TIF = resolve(
  REPO_ROOT,
  "data/terrain/12. DEM SRTM 30m Provinsi Jawa Barat/DEM SRTM 30M JAWA BARAT.tif",
);
const OUT = resolve(REPO_ROOT, "frontend/public/assets/terrain.json");

// Jatibarang study extent — a margin around the demo source and wells.
const EXTENT = { minLon: 108.24, maxLon: 108.40, minLat: -6.56, maxLat: -6.42 };
const TARGET = 120; // mesh resolution per side

async function main() {
  const tiff = await fromFile(TIF);
  const image = await tiff.getImage();
  const [minX, minY, maxX, maxY] = image.getBoundingBox();
  const rasterW = image.getWidth();
  const rasterH = image.getHeight();

  // Map the requested geographic extent to pixel window (raster is north-up).
  const px = (lon) => ((lon - minX) / (maxX - minX)) * rasterW;
  const py = (lat) => ((maxY - lat) / (maxY - minY)) * rasterH;
  const win = [
    Math.max(0, Math.floor(px(EXTENT.minLon))),
    Math.max(0, Math.floor(py(EXTENT.maxLat))),
    Math.min(rasterW, Math.ceil(px(EXTENT.maxLon))),
    Math.min(rasterH, Math.ceil(py(EXTENT.minLat))),
  ];

  const data = await image.readRasters({
    window: win,
    width: TARGET,
    height: TARGET,
    resampleMethod: "bilinear",
  });
  const band = data[0];
  const noData = image.getGDALNoData();

  let minElev = Infinity;
  let maxElev = -Infinity;
  const elevations = new Array(band.length);
  for (let i = 0; i < band.length; i++) {
    let v = band[i];
    if (noData != null && v === noData) v = 0;
    if (!Number.isFinite(v) || v < -500) v = 0;
    elevations[i] = v;
    if (v < minElev) minElev = v;
    if (v > maxElev) maxElev = v;
  }

  const out = {
    width: TARGET,
    height: TARGET,
    extent: EXTENT,
    minElev,
    maxElev,
    // Round to whole metres to keep the asset small.
    elevations: elevations.map((v) => Math.round(v)),
  };
  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify(out));
  console.log(
    `wrote ${OUT}: ${TARGET}x${TARGET}, elevation ${minElev}..${maxElev} m`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
