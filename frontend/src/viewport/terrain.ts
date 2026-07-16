import type { Coordinate } from "../api/types";

/**
 * Terrain heightmap loading and a shared geographic → scene projection so the
 * terrain mesh and the scene objects (sources, wells, routes) share one
 * coordinate frame in the 3D viewport.
 */

export interface TerrainData {
  width: number;
  height: number;
  extent: { minLon: number; maxLon: number; minLat: number; maxLat: number };
  minElev: number;
  maxElev: number;
  elevations: number[];
}

let cache: Promise<TerrainData> | null = null;

export function loadTerrain(): Promise<TerrainData> {
  if (!cache) {
    cache = fetch("/assets/terrain.json").then((r) => {
      if (!r.ok) throw new Error("terrain asset unavailable");
      return r.json() as Promise<TerrainData>;
    });
  }
  return cache;
}

/** Half-width of the terrain plane in scene units (plane spans [-SIZE, SIZE]). */
export const TERRAIN_SIZE = 10;

export interface TerrainProjector {
  /** Project a coordinate to scene x/z within the terrain plane. */
  toXZ: (c: Coordinate) => [number, number];
  /** Bilinear-sampled ground elevation (metres) at a coordinate. */
  elevationAt: (c: Coordinate) => number;
  /** Scene-unit height for an elevation, given the vertical exaggeration. */
  heightOf: (elevationMetres: number, exaggeration: number) => number;
  data: TerrainData;
}

export function makeProjector(data: TerrainData): TerrainProjector {
  const { minLon, maxLon, minLat, maxLat } = data.extent;
  const spanLon = maxLon - minLon || 1e-9;
  const spanLat = maxLat - minLat || 1e-9;
  // 1 metre of real elevation -> scene units. The plane is TERRAIN_SIZE*2 wide
  // for a ground span of ~15 km, so pick a base scale in that proportion.
  const groundSpanMetres = spanLat * 111_000;
  const metresPerSceneUnit = groundSpanMetres / (TERRAIN_SIZE * 2);

  const toXZ = (c: Coordinate): [number, number] => {
    const u = (c.longitude - minLon) / spanLon; // 0..1 west->east
    const v = (c.latitude - minLat) / spanLat; // 0..1 south->north
    return [(u - 0.5) * 2 * TERRAIN_SIZE, -(v - 0.5) * 2 * TERRAIN_SIZE];
  };

  const elevationAt = (c: Coordinate): number => {
    const fx = ((c.longitude - minLon) / spanLon) * (data.width - 1);
    const fy = ((maxLat - c.latitude) / spanLat) * (data.height - 1); // north-up rows
    const x0 = Math.max(0, Math.min(data.width - 1, Math.floor(fx)));
    const y0 = Math.max(0, Math.min(data.height - 1, Math.floor(fy)));
    const x1 = Math.min(data.width - 1, x0 + 1);
    const y1 = Math.min(data.height - 1, y0 + 1);
    const tx = fx - x0;
    const ty = fy - y0;
    const e = (x: number, y: number) => data.elevations[y * data.width + x];
    const top = e(x0, y0) * (1 - tx) + e(x1, y0) * tx;
    const bot = e(x0, y1) * (1 - tx) + e(x1, y1) * tx;
    return top * (1 - ty) + bot * ty;
  };

  const heightOf = (elevationMetres: number, exaggeration: number): number =>
    (elevationMetres / metresPerSceneUnit) * exaggeration;

  return { toXZ, elevationAt, heightOf, data };
}
