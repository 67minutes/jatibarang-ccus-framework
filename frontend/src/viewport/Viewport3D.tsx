import { useEffect, useMemo, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { useWorkspaceStore } from "../state/workspace.store";
import { useCursorStore } from "../state/cursor.store";
import { selectPlan } from "../layout/ProjectTree";
import { collectSceneObjects, nodeCoordinateMap, type Scene } from "./scene";
import {
  loadTerrain,
  makeProjector,
  TERRAIN_SIZE,
  type TerrainProjector,
} from "./terrain";
import { ReservoirGrid } from "./ReservoirGrid";
import type { Coordinate } from "../api/types";
import "./viewport.css";

/**
 * The 3D field-twin viewport (design §5): monochrome SRTM terrain with the
 * study's sources, wells, and network. Read-only scene; a crash here is caught
 * by the surrounding error boundary, which swaps in the 2D map (design §5.2).
 */
export function Viewport3D() {
  const [projector, setProjector] = useState<TerrainProjector | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    loadTerrain()
      .then((data) => alive && setProjector(makeProjector(data)))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  // Surface a terrain-load failure to the error boundary -> 2D fallback.
  if (failed) throw new Error("terrain unavailable for 3D viewport");
  if (!projector) {
    return (
      <div className="viewport-empty">
        <div className="viewport-empty-dim">Loading terrain…</div>
      </div>
    );
  }
  return (
    <div className="viewport-3d">
      <Canvas
        camera={{ position: [0, 14, 20], fov: 42, near: 0.1, far: 400 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true }}
      >
        <color attach="background" args={["#0e1013"]} />
        <hemisphereLight args={["#c9ced6", "#0a0c0f", 0.9]} />
        <directionalLight position={[12, 20, 8]} intensity={1.1} />
        <SceneContent projector={projector} />
        <CameraRig />
        <OrbitControls
          enablePan
          maxPolarAngle={Math.PI / 2.05}
          minDistance={4}
          maxDistance={80}
        />
      </Canvas>
      <div className="viewport-legend">
        <span><i className="lg-source" /> source</span>
        <span><i className="lg-well" /> well</span>
        <span><i className="lg-pipe" /> pipeline</span>
        <span><i className="lg-truck" /> trucking</span>
      </div>
      <div className="viewport-mode-tag">3D · terrain</div>
    </div>
  );
}

function SceneContent({ projector }: { projector: TerrainProjector }) {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const layers = useWorkspaceStore((s) => s.layers);

  const plan = activeEntry ? selectPlan(activeEntry.result, carbonPriceId) : null;
  const scene = useMemo<Scene | null>(
    () => (activeEntry ? collectSceneObjects(activeEntry.request, plan) : null),
    [activeEntry, plan],
  );

  // Locate the selected well to anchor the reservoir cutaway beneath it.
  const selection = useSelectionStore((s) => s.selection);
  const wellSpot = useMemo(() => {
    if (!activeEntry || selection.kind !== "well" || !selection.id) return null;
    const coord = nodeCoordinateMap(activeEntry.request).get(selection.id);
    if (!coord) return null;
    const [x, z] = projector.toXZ(coord);
    return { xz: [x, z] as [number, number], groundY: projector.heightOf(projector.elevationAt(coord), exaggeration) };
  }, [activeEntry, selection, projector, exaggeration]);

  return (
    <group>
      <Terrain projector={projector} exaggeration={exaggeration} />
      {scene && (
        <SceneObjects projector={projector} scene={scene} exaggeration={exaggeration} layers={layers} />
      )}
      {wellSpot && <ReservoirGrid position={wellSpot.xz} groundY={wellSpot.groundY} />}
    </group>
  );
}

function Terrain({
  projector,
  exaggeration,
}: {
  projector: TerrainProjector;
  exaggeration: number;
}) {
  const { data } = projector;
  const setReadout = useCursorStore((s) => s.setReadout);

  const geometry = useMemo(() => {
    const { width, height, elevations, minElev, maxElev } = data;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(width * height * 3);
    const colors = new Float32Array(width * height * 3);
    const span = Math.max(1, maxElev - minElev);
    for (let j = 0; j < height; j++) {
      for (let i = 0; i < width; i++) {
        const k = j * width + i;
        const x = (i / (width - 1) - 0.5) * 2 * TERRAIN_SIZE;
        const z = (j / (height - 1) - 0.5) * 2 * TERRAIN_SIZE;
        const y = projector.heightOf(elevations[k], exaggeration);
        positions[k * 3] = x;
        positions[k * 3 + 1] = y;
        positions[k * 3 + 2] = z;
        // Monochrome elevation ramp (dark low -> light high).
        const t = (elevations[k] - minElev) / span;
        const shade = 0.16 + 0.5 * t;
        colors[k * 3] = shade;
        colors[k * 3 + 1] = shade + 0.02;
        colors[k * 3 + 2] = shade + 0.05;
      }
    }
    const indices: number[] = [];
    for (let j = 0; j < height - 1; j++) {
      for (let i = 0; i < width - 1; i++) {
        const a = j * width + i;
        const b = a + 1;
        const c = a + width;
        const d = c + 1;
        indices.push(a, c, b, b, c, d);
      }
    }
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    return geo;
  }, [data, exaggeration, projector]);

  const onMove = (e: { point: THREE.Vector3 }) => {
    const { extent, width, height } = data;
    // Inverse projection from scene x/z back to lon/lat.
    const u = e.point.x / (2 * TERRAIN_SIZE) + 0.5;
    const v = -e.point.z / (2 * TERRAIN_SIZE) + 0.5;
    const longitude = extent.minLon + u * (extent.maxLon - extent.minLon);
    const latitude = extent.minLat + v * (extent.maxLat - extent.minLat);
    const coord: Coordinate = { latitude, longitude };
    setReadout({
      i: Math.round(u * (width - 1)),
      j: Math.round((1 - v) * (height - 1)),
      latitude,
      longitude,
      elevation_m: projector.elevationAt(coord),
    });
  };

  return (
    <mesh
      geometry={geometry}
      onPointerMove={onMove}
      onPointerOut={() => setReadout(null)}
    >
      <meshStandardMaterial vertexColors flatShading roughness={0.95} metalness={0} />
    </mesh>
  );
}

function SceneObjects({
  projector,
  scene,
  exaggeration,
  layers,
}: {
  projector: TerrainProjector;
  scene: Scene;
  exaggeration: number;
  layers: { routes: boolean; boosters: boolean; labels: boolean };
}) {
  const select = useSelectionStore((s) => s.select);
  const selection = useSelectionStore((s) => s.selection);

  const yAt = (c: Coordinate, lift: number) =>
    projector.heightOf(projector.elevationAt(c), exaggeration) + lift;

  return (
    <group>
      {/* Routes: terrain-following polylines. */}
      {layers.routes &&
        scene.routes.map((route) => {
          const pts = samplePath(route.path).map((c) => {
            const [x, z] = projector.toXZ(c);
            return new THREE.Vector3(x, yAt(c, 0.18), z);
          });
          return (
            <Line
              key={route.id}
              points={pts}
              color={route.mode === "trucking" ? "#c9922e" : "#d1352b"}
              lineWidth={route.mode === "trucking" ? 1.6 : 2.4}
              dashed={route.mode === "trucking"}
              dashSize={0.4}
              gapSize={0.3}
            />
          );
        })}

      {/* Sources and wells. */}
      {scene.nodes.map((node) => {
        const [x, z] = projector.toXZ(node.location);
        const y = yAt(node.location, 0);
        const selected = selection.id === node.id;
        return (
          <group key={node.id} position={[x, y, z]}>
            {node.kind === "source" ? (
              <mesh
                position={[0, 0.35, 0]}
                onClick={(e) => {
                  e.stopPropagation();
                  select({ kind: "source", id: node.id });
                }}
              >
                <boxGeometry args={[0.5, 0.7, 0.5]} />
                <meshStandardMaterial color={selected ? "#e4463b" : "#4a7fb0"} />
              </mesh>
            ) : (
              <mesh
                position={[0, 0.4, 0]}
                onClick={(e) => {
                  e.stopPropagation();
                  select({ kind: "well", id: node.id });
                }}
              >
                <cylinderGeometry args={[0.12, 0.12, 0.8, 10]} />
                <meshStandardMaterial
                  color={selected ? "#e4463b" : node.dim ? "#5a6068" : "#cfd4da"}
                  emissive={selected ? "#7a2420" : "#000000"}
                />
              </mesh>
            )}
          </group>
        );
      })}

      {/* Boosters. */}
      {layers.boosters &&
        scene.boosters.map((b) => {
          const [x, z] = projector.toXZ(b.location);
          const y = yAt(b.location, 0.3);
          return (
            <mesh key={b.id} position={[x, y, z]}>
              <octahedronGeometry args={[0.28]} />
              <meshStandardMaterial color="#c9922e" />
            </mesh>
          );
        })}
    </group>
  );
}

/** Subdivide each segment so routes drape over terrain rather than cut through. */
function samplePath(path: Coordinate[]): Coordinate[] {
  const out: Coordinate[] = [];
  const steps = 24;
  for (let s = 0; s < path.length - 1; s++) {
    const a = path[s];
    const b = path[s + 1];
    for (let t = 0; t <= steps; t++) {
      const f = t / steps;
      out.push({
        latitude: a.latitude + (b.latitude - a.latitude) * f,
        longitude: a.longitude + (b.longitude - a.longitude) * f,
      });
    }
  }
  return out;
}

/** Handles the View ▸ Reset Camera command (dispatched as a window event). */
function CameraRig() {
  const { camera } = useThree();
  useEffect(() => {
    const handler = () => {
      camera.position.set(0, 14, 20);
      camera.lookAt(0, 0, 0);
    };
    window.addEventListener("viewport:reset-camera", handler);
    return () => window.removeEventListener("viewport:reset-camera", handler);
  }, [camera]);
  return null;
}
