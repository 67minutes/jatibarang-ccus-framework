import { Html } from "@react-three/drei";
import { useMemo } from "react";
import type {
  CarbonPricePlan,
  Coordinate,
  ScreenResult,
} from "../api/types";
import type { PlacedWell } from "../state/field.store";
import type { TerrainProjector } from "./terrain";

const METRES_PER_DEGREE_LATITUDE = 111_320;
const MIN_LONGITUDE_COSINE = 1e-6;

export interface InfluenceEntry {
  candidate_id: string;
  lat: number;
  lon: number;
  radius_m: number;
  flagged: boolean;
}

export interface ProjectedInfluenceEntry extends InfluenceEntry {
  x: number;
  y: number;
  z: number;
  radius_x: number;
  radius_z: number;
}

function isFiniteCoordinate(well: PlacedWell): boolean {
  return (
    Number.isFinite(well.lat) &&
    well.lat >= -90 &&
    well.lat <= 90 &&
    Number.isFinite(well.lon) &&
    well.lon >= -180 &&
    well.lon <= 180
  );
}

/**
 * Convert the selected wells in one screening plan into map-ready influence
 * zones. The per-well plume prediction is the radius source; the interference
 * audit only supplies the warning state.
 */
export function influenceEntries(
  result: ScreenResult,
  plan: CarbonPricePlan | null,
  wells: PlacedWell[],
): InfluenceEntry[] {
  if (!plan) return [];

  // Refuse a detached/stale plan instead of combining values from two runs.
  const canonicalPlan = result.plans.find(
    (candidate) =>
      candidate.carbon_price_scenario_id === plan.carbon_price_scenario_id,
  );
  if (!canonicalPlan) return [];

  const flaggedIds = new Set<string>();
  for (const pair of canonicalPlan.interference?.flagged_pairs ?? []) {
    if (pair.overlap !== true) continue;
    if (pair.first_well_id) flaggedIds.add(pair.first_well_id);
    if (pair.second_well_id) flaggedIds.add(pair.second_well_id);
  }

  const wellById = new Map<string, PlacedWell>();
  for (const well of wells) {
    if (!wellById.has(well.id) && isFiniteCoordinate(well)) {
      wellById.set(well.id, well);
    }
  }

  const strategyById = new Map(
    canonicalPlan.well_strategies.map((strategy) => [
      strategy.candidate_id,
      strategy,
    ]),
  );

  const selectedIds = [...new Set(canonicalPlan.selected_wells)].sort((a, b) =>
    a.localeCompare(b),
  );
  const entries: InfluenceEntry[] = [];
  for (const candidateId of selectedIds) {
    const well = wellById.get(candidateId);
    const radius = strategyById.get(candidateId)?.prediction?.plume
      ?.influence_radius_m;
    if (
      !well ||
      typeof radius !== "number" ||
      !Number.isFinite(radius) ||
      radius <= 0
    ) {
      continue;
    }
    entries.push({
      candidate_id: candidateId,
      lat: well.lat,
      lon: well.lon,
      radius_m: radius,
      flagged: flaggedIds.has(candidateId),
    });
  }
  return entries;
}

/**
 * Project a metric radius through the same geographic transform as terrain.
 * East and north offsets are projected independently so non-square terrain
 * extents produce a physically meaningful ellipse rather than a scene-space
 * circle with a guessed scale.
 */
export function projectInfluenceEntry(
  projector: TerrainProjector,
  entry: InfluenceEntry,
  exaggeration = 1,
): ProjectedInfluenceEntry | null {
  if (
    !Number.isFinite(entry.lat) ||
    !Number.isFinite(entry.lon) ||
    !Number.isFinite(entry.radius_m) ||
    entry.radius_m <= 0
  ) {
    return null;
  }

  const center: Coordinate = {
    latitude: entry.lat,
    longitude: entry.lon,
  };
  const latitudeRadians = (entry.lat * Math.PI) / 180;
  const longitudeScale =
    METRES_PER_DEGREE_LATITUDE *
    Math.max(MIN_LONGITUDE_COSINE, Math.abs(Math.cos(latitudeRadians)));
  const east: Coordinate = {
    latitude: entry.lat,
    longitude: entry.lon + entry.radius_m / longitudeScale,
  };
  const north: Coordinate = {
    latitude: entry.lat + entry.radius_m / METRES_PER_DEGREE_LATITUDE,
    longitude: entry.lon,
  };

  const [x, z] = projector.toXZ(center);
  const [eastX, eastZ] = projector.toXZ(east);
  const [northX, northZ] = projector.toXZ(north);
  const radiusX = Math.hypot(eastX - x, eastZ - z);
  const radiusZ = Math.hypot(northX - x, northZ - z);
  const elevation = projector.elevationAt(center);
  const y = projector.heightOf(elevation, exaggeration);
  if (
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    !Number.isFinite(z) ||
    !Number.isFinite(radiusX) ||
    !Number.isFinite(radiusZ) ||
    radiusX <= 0 ||
    radiusZ <= 0
  ) {
    return null;
  }

  return {
    ...entry,
    x,
    y,
    z,
    radius_x: radiusX,
    radius_z: radiusZ,
  };
}

export function InfluenceZones({
  projector,
  entries,
  exaggeration = 1,
}: {
  projector: TerrainProjector;
  entries: InfluenceEntry[];
  exaggeration?: number;
}) {
  const projected = useMemo(
    () =>
      entries
        .map((entry) => projectInfluenceEntry(projector, entry, exaggeration))
        .filter((entry): entry is ProjectedInfluenceEntry => entry !== null),
    [entries, exaggeration, projector],
  );

  return (
    <group name="influence-zones">
      {projected.map((entry) => (
        <group
          key={entry.candidate_id}
          name={`influence-zone-${entry.candidate_id}`}
          position={[entry.x, entry.y + 0.025, entry.z]}
        >
          <mesh
            rotation={[-Math.PI / 2, 0, 0]}
            scale={[entry.radius_x, entry.radius_z, 1]}
            raycast={() => undefined}
          >
            <circleGeometry args={[1, 64]} />
            <meshBasicMaterial
              color={entry.flagged ? "#e4463b" : "#c9922e"}
              transparent
              opacity={0.18}
              depthWrite={false}
              polygonOffset
              polygonOffsetFactor={-1}
            />
          </mesh>
          {entry.flagged ? (
            <Html
              center
              position={[0, 0.1, 0]}
              distanceFactor={3}
              zIndexRange={[11, 0]}
              style={{ pointerEvents: "none" }}
            >
              <span className="influence-warning-badge">interference</span>
            </Html>
          ) : null}
        </group>
      ))}
    </group>
  );
}
