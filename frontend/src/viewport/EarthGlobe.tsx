import { useEffect, useMemo, useState } from "react";
import { Html, Line } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { RegisteredTerrain } from "../api/client";

const DEG2RAD = Math.PI / 180;
const GLOBE_RADIUS = 10;

export function latLonToVec3(
  lat: number,
  lon: number,
  radius: number,
): [number, number, number] {
  const phi = (90 - lat) * DEG2RAD;
  const theta = (lon + 180) * DEG2RAD;
  return [
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  ];
}

interface CoastlineBundle {
  lines: [number, number][][];
}

interface EarthGlobeProps {
  terrains: RegisteredTerrain[];
  activeTerrainId: string | null;
  onDive: (terrainId: string) => void;
}

function graticuleLines(): Array<{
  key: string;
  points: [number, number, number][];
}> {
  const lines: Array<{
    key: string;
    points: [number, number, number][];
  }> = [];
  for (let lon = -180; lon < 180; lon += 30) {
    lines.push({
      key: `meridian-${lon}`,
      points: Array.from({ length: 49 }, (_, index) =>
        latLonToVec3(-90 + index * 3.75, lon, GLOBE_RADIUS * 1.001),
      ),
    });
  }
  for (let lat = -75; lat <= 75; lat += 15) {
    lines.push({
      key: `parallel-${lat}`,
      points: Array.from({ length: 97 }, (_, index) =>
        latLonToVec3(lat, -180 + index * 3.75, GLOBE_RADIUS * 1.001),
      ),
    });
  }
  return lines;
}

function footprintPoints(
  terrain: RegisteredTerrain,
): [number, number, number][] {
  const { minLat, maxLat, minLon, maxLon } = terrain.extent;
  const coordinates: Array<[number, number]> = [];
  const segments = 12;
  for (let index = 0; index < segments; index += 1) {
    const fraction = index / segments;
    coordinates.push([minLat, minLon + (maxLon - minLon) * fraction]);
  }
  for (let index = 0; index < segments; index += 1) {
    const fraction = index / segments;
    coordinates.push([minLat + (maxLat - minLat) * fraction, maxLon]);
  }
  for (let index = 0; index < segments; index += 1) {
    const fraction = index / segments;
    coordinates.push([maxLat, maxLon - (maxLon - minLon) * fraction]);
  }
  for (let index = 0; index <= segments; index += 1) {
    const fraction = index / segments;
    coordinates.push([maxLat - (maxLat - minLat) * fraction, minLon]);
  }
  return coordinates.map(([lat, lon]) =>
    latLonToVec3(lat, lon, GLOBE_RADIUS * 1.004),
  );
}

export function EarthGlobe({
  terrains,
  activeTerrainId,
  onDive,
}: EarthGlobeProps) {
  const [texture, setTexture] = useState<THREE.Texture | null>(null);
  const [coastlines, setCoastlines] = useState<CoastlineBundle | null>(null);
  const graticule = useMemo(graticuleLines, []);

  useEffect(() => {
    let disposed = false;
    const loader = new THREE.TextureLoader();
    const loaded = loader.load(
      "/earth/blue_marble_2048.jpg",
      (next) => {
        if (disposed) {
          next.dispose();
          return;
        }
        next.colorSpace = THREE.SRGBColorSpace;
        setTexture(next);
      },
      undefined,
      () => {
        if (!disposed) setTexture(null);
      },
    );
    return () => {
      disposed = true;
      loaded.dispose();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void fetch("/earth/ne_50m_coastline.json")
      .then((response) => {
        if (!response.ok) throw new Error("coastline asset unavailable");
        return response.json() as Promise<CoastlineBundle>;
      })
      .then((bundle) => {
        if (!cancelled) setCoastlines(bundle);
      })
      .catch(() => {
        if (!cancelled) setCoastlines(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const dive = (event: ThreeEvent<MouseEvent>, terrainId: string) => {
    event.stopPropagation();
    onDive(terrainId);
  };

  return (
    <group>
      <mesh>
        <sphereGeometry args={[GLOBE_RADIUS, 64, 48]} />
        <meshStandardMaterial
          map={texture ?? undefined}
          color={texture ? "#ffffff" : "#123a52"}
          roughness={0.9}
          metalness={0}
        />
      </mesh>
      {graticule.map((line) => (
        <Line
          key={line.key}
          points={line.points}
          color="#2c4a58"
          lineWidth={0.4}
          transparent
          opacity={0.72}
        />
      ))}
      {coastlines?.lines.map((line, index) => (
        <Line
          key={`coastline-${index}`}
          points={line.map(([lon, lat]) =>
            latLonToVec3(lat, lon, GLOBE_RADIUS * 1.002),
          )}
          color="#9fd0e0"
          lineWidth={0.6}
          transparent
          opacity={0.78}
        />
      ))}
      {terrains.map((terrain) => {
        const active = terrain.terrain_id === activeTerrainId;
        const centerLat = (terrain.extent.minLat + terrain.extent.maxLat) / 2;
        const centerLon = (terrain.extent.minLon + terrain.extent.maxLon) / 2;
        return (
          <group key={terrain.terrain_id}>
            <Line
              points={footprintPoints(terrain)}
              color={active ? "#e8c268" : "#7d8894"}
              lineWidth={active ? 2.4 : 1.4}
              onDoubleClick={(event) => dive(event, terrain.terrain_id)}
            />
            {active ? (
              <Html
                center
                position={latLonToVec3(
                  centerLat,
                  centerLon,
                  GLOBE_RADIUS * 1.045,
                )}
                distanceFactor={10}
                zIndexRange={[6, 0]}
              >
                <span className="scene-label">
                  {terrain.terrain_id.replace(/^terrain-/, "").slice(0, 8)}
                </span>
              </Html>
            ) : null}
          </group>
        );
      })}
    </group>
  );
}
