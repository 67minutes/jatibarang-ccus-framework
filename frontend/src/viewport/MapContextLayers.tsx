import { useMemo } from "react";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { useFieldStore } from "../state/field.store";
import type { LayerVisibility } from "../state/workspace.store";
import type { TerrainProjector } from "./terrain";

interface MapContextLayersProps {
  projector: TerrainProjector;
  exaggeration: number;
  layers: LayerVisibility;
}

interface ProjectedPlace {
  key: string;
  name: string;
  position: THREE.Vector3;
}

export function lineSegmentPositions(lines: THREE.Vector3[][]): Float32Array {
  const segmentCount = lines.reduce(
    (count, points) => count + Math.max(points.length - 1, 0),
    0,
  );
  const values = new Float32Array(segmentCount * 6);
  let offset = 0;
  for (const points of lines) {
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      values[offset] = start.x;
      values[offset + 1] = start.y;
      values[offset + 2] = start.z;
      values[offset + 3] = end.x;
      values[offset + 4] = end.y;
      values[offset + 5] = end.z;
      offset += 6;
    }
  }
  return values;
}

function SegmentLayer({
  positions,
  color,
}: {
  positions: Float32Array;
  color: string;
}) {
  if (positions.length === 0) return null;
  return (
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <lineBasicMaterial color={color} transparent opacity={0.82} />
    </lineSegments>
  );
}

function drapeLine(
  points: [number, number][],
  projector: TerrainProjector,
  exaggeration: number,
  lift: number,
): THREE.Vector3[] {
  if (points.length < 2) return [];
  const coordinates = points.map(([latitude, longitude]) => ({
    latitude,
    longitude,
  }));
  const sampled: Array<{ latitude: number; longitude: number }> = [];
  for (let index = 0; index < coordinates.length - 1; index += 1) {
    const start = coordinates[index];
    const end = coordinates[index + 1];
    const [startX, startZ] = projector.toXZ(start);
    const [endX, endZ] = projector.toXZ(end);
    const steps = Math.max(
      1,
      Math.min(8, Math.ceil(Math.hypot(endX - startX, endZ - startZ) / 0.35)),
    );
    for (let step = 0; step < steps; step += 1) {
      const fraction = step / steps;
      sampled.push({
        latitude: start.latitude + (end.latitude - start.latitude) * fraction,
        longitude:
          start.longitude + (end.longitude - start.longitude) * fraction,
      });
    }
  }
  sampled.push(coordinates.at(-1)!);
  return sampled.map((coordinate) => {
    const [x, z] = projector.toXZ(coordinate);
    const y =
      projector.heightOf(
        projector.elevationAt(coordinate),
        exaggeration,
      ) + lift;
    return new THREE.Vector3(x, y, z);
  });
}

/** Quiet, offline cartographic context draped directly over basin terrain. */
export function MapContextLayers({
  projector,
  exaggeration,
  layers,
}: MapContextLayersProps) {
  const roadLayers = useFieldStore((state) => state.roadLayers);
  const projected = useMemo(() => {
    if (!roadLayers) {
      return {
        majorRoads: new Float32Array(),
        minorRoads: new Float32Array(),
        coastline: new Float32Array(),
        places: [] as ProjectedPlace[],
      };
    }
    const roads = roadLayers.roads
      .filter((road) => road.points.length >= 2)
      .map((road) => ({
        class: road.class,
        points: drapeLine(road.points, projector, exaggeration, 0.02),
      }));
    const coastline = roadLayers.coastline
      .filter((line) => line.length >= 2)
      .map((line) => drapeLine(line, projector, exaggeration, 0.02));
    const places: ProjectedPlace[] = roadLayers.places.map((place, index) => {
      const coordinate = { latitude: place.lat, longitude: place.lon };
      const [x, z] = projector.toXZ(coordinate);
      const y =
        projector.heightOf(
          projector.elevationAt(coordinate),
          exaggeration,
        ) + 0.28;
      return {
        key: `place-${place.kind}-${place.name}-${index}`,
        name: place.name,
        position: new THREE.Vector3(x, y, z),
      };
    });
    return {
      majorRoads: lineSegmentPositions(
        roads.filter((road) => road.class === "major").map((road) => road.points),
      ),
      minorRoads: lineSegmentPositions(
        roads.filter((road) => road.class !== "major").map((road) => road.points),
      ),
      coastline: lineSegmentPositions(coastline),
      places,
    };
  }, [exaggeration, projector, roadLayers]);

  if (!roadLayers) return null;
  return (
    <group>
      {layers.roads ? (
        <>
          <SegmentLayer positions={projected.minorRoads} color="#5a616b" />
          <SegmentLayer positions={projected.majorRoads} color="#9aa0a8" />
        </>
      ) : null}
      {layers.coastline ? (
        <SegmentLayer positions={projected.coastline} color="#4e86a0" />
      ) : null}
      {layers.places && projected.places.map((place) => (
        <Html
          key={place.key}
          center
          position={place.position}
          distanceFactor={4}
          zIndexRange={[8, 0]}
        >
          <span className="scene-label">{place.name}</span>
        </Html>
      ))}
    </group>
  );
}
