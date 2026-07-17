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

export interface TerrainBounds {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
}

export type TerrainPalette = "geologic" | "monochrome";

const GEOLOGIC_STOPS: Array<[number, [number, number, number]]> = [
  [0, [0.075, 0.15, 0.16]],
  [0.22, [0.12, 0.24, 0.21]],
  [0.5, [0.24, 0.32, 0.23]],
  [0.74, [0.42, 0.38, 0.27]],
  [1, [0.66, 0.65, 0.56]],
];

const MONOCHROME_STOPS: Array<[number, [number, number, number]]> = [
  [0, [0.11, 0.13, 0.15]],
  [0.5, [0.31, 0.34, 0.37]],
  [1, [0.66, 0.68, 0.69]],
];

/** Restrained terrain color with enough hue contrast to make relief legible. */
export function terrainColor(
  normalizedElevation: number,
  palette: TerrainPalette,
): [number, number, number] {
  const t = Math.max(0, Math.min(1, normalizedElevation));
  const stops = palette === "geologic" ? GEOLOGIC_STOPS : MONOCHROME_STOPS;
  for (let index = 1; index < stops.length; index++) {
    const [upperT, upper] = stops[index];
    if (t > upperT) continue;
    const [lowerT, lower] = stops[index - 1];
    const local = (t - lowerT) / Math.max(1e-6, upperT - lowerT);
    return [
      lower[0] + (upper[0] - lower[0]) * local,
      lower[1] + (upper[1] - lower[1]) * local,
      lower[2] + (upper[2] - lower[2]) * local,
    ];
  }
  return stops[stops.length - 1][1];
}

/** Half-width of the terrain plane in scene units (plane spans [-SIZE, SIZE]). */
export const TERRAIN_SIZE = 10;

/**
 * Geographic crop used by the field-level scene. The reservoir has no native
 * georeference, so the imported footprint is centred on the user's placement
 * and padded by three footprint widths before the backend clips it to the DEM.
 */
export function fieldWindowBounds(
  center: Coordinate,
  footprint: { length_x_m: number; length_y_m: number },
  paddingMultiplier = 3,
): TerrainBounds {
  const paddingMetres =
    Math.max(footprint.length_x_m, footprint.length_y_m) * paddingMultiplier;
  const latitudeRadians = (center.latitude * Math.PI) / 180;
  const metresPerDegreeLongitude = Math.max(
    1,
    111_320 * Math.abs(Math.cos(latitudeRadians)),
  );
  const latitudePadding = paddingMetres / 111_320;
  const longitudePadding = paddingMetres / metresPerDegreeLongitude;
  return {
    minLon: center.longitude - longitudePadding,
    minLat: center.latitude - latitudePadding,
    maxLon: center.longitude + longitudePadding,
    maxLat: center.latitude + latitudePadding,
  };
}

export interface TerrainProjector {
  /** Project a coordinate to scene x/z within the terrain plane. */
  toXZ: (c: Coordinate) => [number, number];
  /** Bilinear-sampled ground elevation (metres) at a coordinate. */
  elevationAt: (c: Coordinate) => number;
  /** Scene-unit height for an elevation, given the vertical exaggeration. */
  heightOf: (elevationMetres: number, exaggeration: number) => number;
  /** Uniform local scale used by reservoir geometry and other metric objects. */
  metresPerSceneUnit: number;
  data: TerrainData;
}

/** Inverse of TerrainProjector.toXZ for scene interactions and drag handles. */
export function xzToCoordinate(
  projector: TerrainProjector,
  x: number,
  z: number,
): Coordinate {
  const { minLon, maxLon, minLat, maxLat } = projector.data.extent;
  const u = x / (2 * TERRAIN_SIZE) + 0.5;
  const v = -z / (2 * TERRAIN_SIZE) + 0.5;
  return {
    longitude: minLon + u * (maxLon - minLon),
    latitude: minLat + v * (maxLat - minLat),
  };
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

  return { toXZ, elevationAt, heightOf, metresPerSceneUnit, data };
}
