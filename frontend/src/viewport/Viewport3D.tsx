import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { useWorkspaceStore, type LayerVisibility } from "../state/workspace.store";
import { useCursorStore } from "../state/cursor.store";
import { selectPlan } from "../layout/ProjectTree";
import { collectSceneObjects, nodeCoordinateMap, type Scene } from "./scene";
import {
  makeProjector,
  terrainColor,
  TERRAIN_SIZE,
  xzToCoordinate,
  type TerrainProjector,
} from "./terrain";
import { useFieldStore } from "../state/field.store";
import { ReservoirGrid } from "./ReservoirGrid";
import type { CellField, Coordinate, PredictionResult, ReservoirVisualization } from "../api/types";
import { finiteRange, type StaticReservoirField } from "./reservoirGeometry";
import { FieldOutline, pointInField } from "./FieldOutline";
import {
  SceneContextMenu,
  type SceneContextTarget,
} from "./SceneContextMenu";
import { SourceDialog, type SourceDialogValue } from "./SourceDialog";
import "./viewport.css";

type SceneContextRequest = Omit<SceneContextTarget, "x" | "y">;

interface SourceEditorState {
  lat: number;
  lon: number;
  sourceId?: string;
}

/**
 * The 3D field-twin viewport (design §5): monochrome SRTM terrain with the
 * study's sources, wells, and network. Read-only scene; a crash here is caught
 * by the surrounding error boundary, which swaps in the 2D map (design §5.2).
 */
export function Viewport3D() {
  const terrain = useFieldStore((state) => state.terrain);
  const terrainOverview = useFieldStore((state) => state.overviewData);
  const placement = useFieldStore((state) => state.placement);
  const reservoir = useFieldStore((state) => state.reservoir);
  const wells = useFieldStore((state) => state.wells);
  const sources = useFieldStore((state) => state.sources);
  const selection = useSelectionStore((state) => state.selection);
  const select = useSelectionStore((state) => state.select);
  const clearSelection = useSelectionStore((state) => state.clear);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [contextTarget, setContextTarget] = useState<SceneContextTarget | null>(null);
  const [sourceEditor, setSourceEditor] = useState<SourceEditorState | null>(null);
  const projector = useMemo(
    () => (terrainOverview ? makeProjector(terrainOverview) : null),
    [terrainOverview],
  );

  const openContext = (
    event: ThreeEvent<MouseEvent>,
    request: SceneContextRequest,
  ) => {
    event.stopPropagation();
    event.nativeEvent.preventDefault();
    const bounds = wrapperRef.current?.getBoundingClientRect();
    setContextTarget({
      ...request,
      x: event.nativeEvent.clientX - (bounds?.left ?? 0),
      y: event.nativeEvent.clientY - (bounds?.top ?? 0),
    });
  };

  const contextWell = contextTarget?.targetId
    ? wells.find((well) => well.id === contextTarget.targetId)
    : undefined;
  const contextSource = contextTarget?.targetId
    ? sources.find((source) => source.id === contextTarget.targetId)
    : undefined;
  const sourceBeingEdited = sourceEditor?.sourceId
    ? sources.find((source) => source.id === sourceEditor.sourceId)
    : undefined;

  const saveSource = (value: SourceDialogValue) => {
    const field = useFieldStore.getState();
    if (sourceEditor?.sourceId) {
      field.updateSource(sourceEditor.sourceId, value);
      select({ kind: "source", id: sourceEditor.sourceId });
    } else {
      const created = field.addSource(value);
      select({ kind: "source", id: created.id });
    }
    setSourceEditor(null);
  };

  if (!terrain) {
    return (
      <div className="viewport-empty">
        <div className="viewport-empty-hint">
          <strong>No study loaded</strong>
          <span>New Study — Ctrl+N · Open Study — Ctrl+O</span>
        </div>
      </div>
    );
  }
  if (!projector) {
    return (
      <div className="viewport-empty">
        <div className="viewport-empty-hint">
          <strong>Terrain overview unavailable</strong>
          <span>Re-import or relink the registered terrain for this study.</span>
        </div>
      </div>
    );
  }
  return (
    <div
      ref={wrapperRef}
      className="viewport-3d"
      onContextMenu={(event) => event.preventDefault()}
    >
      <Canvas
        camera={{ position: [0, 12.5, 22], fov: 40, near: 0.1, far: 400 }}
        dpr={[1, 1.75]}
        shadows
        gl={{ antialias: true, preserveDrawingBuffer: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.08;
          gl.outputColorSpace = THREE.SRGBColorSpace;
        }}
      >
        <color attach="background" args={["#081014"]} />
        <fog attach="fog" args={["#081014", 26, 52]} />
        <ambientLight intensity={0.18} />
        <hemisphereLight args={["#b8d4dc", "#14241f", 1.15]} />
        <directionalLight
          castShadow
          position={[-10, 18, 12]}
          color="#ffe4bd"
          intensity={2.25}
          shadow-mapSize-width={1536}
          shadow-mapSize-height={1536}
          shadow-camera-left={-14}
          shadow-camera-right={14}
          shadow-camera-top={14}
          shadow-camera-bottom={-14}
        />
        <directionalLight position={[14, 8, -12]} color="#74aabd" intensity={0.85} />
        <SceneContent projector={projector} onContext={openContext} />
        <CameraRig projector={projector} />
      </Canvas>
      {contextTarget ? (
        <SceneContextMenu
          target={contextTarget}
          canAddCandidateWell={Boolean(
            placement &&
              reservoir &&
              pointInField(
                contextTarget.lat,
                contextTarget.lon,
                placement,
                reservoir,
              ),
          )}
          wellName={contextWell?.name}
          canRemoveWell={contextWell?.kind === "placed"}
          onAddSource={() =>
            setSourceEditor({ lat: contextTarget.lat, lon: contextTarget.lon })
          }
          onAddWell={() => {
            const created = useFieldStore
              .getState()
              .addWell(contextTarget.lat, contextTarget.lon);
            select({ kind: "well", id: created.id });
          }}
          onRenameWell={(name) => {
            if (contextTarget.targetId) {
              useFieldStore.getState().renameWell(contextTarget.targetId, name);
            }
          }}
          onRemoveWell={() => {
            if (!contextTarget.targetId) return;
            useFieldStore.getState().removeWell(contextTarget.targetId);
            if (selection.id === contextTarget.targetId) clearSelection();
          }}
          onEditSource={() => {
            if (!contextSource) return;
            setSourceEditor({
              sourceId: contextSource.id,
              lat: contextSource.lat,
              lon: contextSource.lon,
            });
          }}
          onRemoveSource={() => {
            if (!contextTarget.targetId) return;
            useFieldStore.getState().removeSource(contextTarget.targetId);
            if (selection.id === contextTarget.targetId) clearSelection();
          }}
          onEnterField={() => useFieldStore.getState().enterField()}
          onClose={() => setContextTarget(null)}
        />
      ) : null}
      {sourceEditor ? (
        <SourceDialog
          initial={sourceBeingEdited}
          lat={sourceEditor.lat}
          lon={sourceEditor.lon}
          onSave={saveSource}
          onClose={() => setSourceEditor(null)}
        />
      ) : null}
      <ViewportNavigationHud projector={projector} />
      <LayerManager />
      <FieldLegend />
      <ReservoirAvailability />
      <ViewportTimeline />
      <ViewportToolStatus />
      <div className="viewport-legend">
        <span><i className="lg-source" /> source</span>
        <span><i className="lg-well" /> well</span>
        <span><i className="lg-pipe" /> pipeline</span>
        <span><i className="lg-truck" /> trucking</span>
      </div>
      <div className="viewport-mode-tag">3D · basin</div>
    </div>
  );
}

function SceneContent({
  projector,
  onContext,
}: {
  projector: TerrainProjector;
  onContext: (
    event: ThreeEvent<MouseEvent>,
    request: SceneContextRequest,
  ) => void;
}) {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const layers = useWorkspaceStore((s) => s.layers);
  const activeTool = useWorkspaceStore((s) => s.activeTool);
  const placement = useFieldStore((s) => s.placement);
  const reservoir = useFieldStore((s) => s.reservoir);

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
      {layers.terrain && (
        <Terrain
          projector={projector}
          exaggeration={exaggeration}
          onContextMenu={(event, coordinate) =>
            onContext(event, {
              kind: "terrain",
              lat: coordinate.latitude,
              lon: coordinate.longitude,
            })
          }
        />
      )}
      {placement && reservoir ? (
        <FieldOutline
          projector={projector}
          placement={placement}
          reservoir={reservoir}
          interactive={activeTool === "select"}
          onContextMenu={(event) =>
            onContext(event, {
              kind: "outline",
              lat: placement.center_lat,
              lon: placement.center_lon,
            })
          }
        />
      ) : null}
      <FieldObjects
        projector={projector}
        exaggeration={exaggeration}
        layers={layers}
        onContext={onContext}
      />
      {scene && (
        <SceneObjects
          projector={projector}
          scene={scene}
          exaggeration={exaggeration}
          layers={layers}
          showNodes={!placement}
        />
      )}
      {wellSpot && (
        <ReservoirGrid
          position={wellSpot.xz}
          groundY={wellSpot.groundY}
          metresPerSceneUnit={projector.metresPerSceneUnit}
        />
      )}
      <MeasurementOverlay projector={projector} exaggeration={exaggeration} />
    </group>
  );
}

function Terrain({
  projector,
  exaggeration,
  onContextMenu,
}: {
  projector: TerrainProjector;
  exaggeration: number;
  onContextMenu: (
    event: ThreeEvent<MouseEvent>,
    coordinate: Coordinate,
  ) => void;
}) {
  const { data } = projector;
  const setReadout = useCursorStore((s) => s.setReadout);
  const palette = useWorkspaceStore((s) => s.terrainPalette);
  const activeTool = useWorkspaceStore((s) => s.activeTool);
  const addMeasurementPoint = useWorkspaceStore((s) => s.addMeasurementPoint);

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
        const t = (elevations[k] - minElev) / span;
        const [r, g, b] = terrainColor(t, palette);
        colors[k * 3] = r;
        colors[k * 3 + 1] = g;
        colors[k * 3 + 2] = b;
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
  }, [data, exaggeration, palette, projector]);

  const coordinateAtPoint = (point: THREE.Vector3): Coordinate =>
    xzToCoordinate(projector, point.x, point.z);

  const onMove = (e: ThreeEvent<PointerEvent>) => {
    const { width, height } = data;
    const coord = coordinateAtPoint(e.point);
    const u = e.point.x / (2 * TERRAIN_SIZE) + 0.5;
    const v = -e.point.z / (2 * TERRAIN_SIZE) + 0.5;
    setReadout({
      i: Math.round(u * (width - 1)),
      j: Math.round((1 - v) * (height - 1)),
      latitude: coord.latitude,
      longitude: coord.longitude,
      elevation_m: projector.elevationAt(coord),
    });
  };

  return (
    <group>
      <mesh
        geometry={geometry}
        castShadow
        receiveShadow
        onPointerMove={onMove}
        onPointerOut={() => setReadout(null)}
        onContextMenu={(event) =>
          onContextMenu(event, coordinateAtPoint(event.point))
        }
        onClick={(event) => {
          if (activeTool !== "measure") return;
          event.stopPropagation();
          const coord = coordinateAtPoint(event.point);
          addMeasurementPoint({
            ...coord,
            elevation_m: projector.elevationAt(coord),
          });
        }}
      >
        <meshStandardMaterial vertexColors flatShading roughness={0.82} metalness={0.03} />
      </mesh>
      <mesh position={[0, -0.19, 0]} receiveShadow>
        <boxGeometry args={[20.15, 0.34, 20.15]} />
        <meshStandardMaterial color="#07100f" roughness={0.92} />
      </mesh>
    </group>
  );
}

function FieldObjects({
  projector,
  exaggeration,
  layers,
  onContext,
}: {
  projector: TerrainProjector;
  exaggeration: number;
  layers: LayerVisibility;
  onContext: (
    event: ThreeEvent<MouseEvent>,
    request: SceneContextRequest,
  ) => void;
}) {
  const wells = useFieldStore((state) => state.wells);
  const sources = useFieldStore((state) => state.sources);
  const select = useSelectionStore((state) => state.select);
  const selection = useSelectionStore((state) => state.selection);

  if (!layers.wells) return null;

  const yAt = (latitude: number, longitude: number, lift: number) => {
    const coordinate = { latitude, longitude };
    return (
      projector.heightOf(projector.elevationAt(coordinate), exaggeration) + lift
    );
  };

  return (
    <group>
      {wells.map((well) => {
        const coordinate = { latitude: well.lat, longitude: well.lon };
        const [x, z] = projector.toXZ(coordinate);
        const y = yAt(well.lat, well.lon, 0);
        const selected = selection.kind === "well" && selection.id === well.id;
        return (
          <group key={well.id} position={[x, y, z]}>
            {(selected || well.kind === "native") && (
              <mesh position={[0, 0.018, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <torusGeometry
                  args={[selected ? 0.095 : 0.078, 0.012, 10, 28]}
                />
                <meshBasicMaterial color={selected ? "#ff6b57" : "#6ed4df"} />
              </mesh>
            )}
            <mesh
              castShadow
              position={[0, 0.12, 0]}
              onClick={(event) => {
                event.stopPropagation();
                select({ kind: "well", id: well.id });
              }}
              onContextMenu={(event) =>
                onContext(event, {
                  kind: "well",
                  targetId: well.id,
                  lat: well.lat,
                  lon: well.lon,
                })
              }
            >
              <cylinderGeometry args={[0.04, 0.04, 0.24, 10]} />
              <meshStandardMaterial
                color={selected ? "#e4463b" : well.kind === "native" ? "#f0e8d6" : "#cfd4da"}
                emissive={selected ? "#7a2420" : well.kind === "native" ? "#163b40" : "#000000"}
                emissiveIntensity={selected ? 0.6 : well.kind === "native" ? 0.3 : 0}
              />
            </mesh>
            {layers.labels ? (
              <Html center position={[0, 0.32, 0]} distanceFactor={3} zIndexRange={[10, 0]}>
                <span
                  className={`scene-label${selected ? " scene-label-selected" : ""}`}
                >
                  {well.name}
                </span>
              </Html>
            ) : null}
          </group>
        );
      })}
      {sources.map((source) => {
        const coordinate = { latitude: source.lat, longitude: source.lon };
        const [x, z] = projector.toXZ(coordinate);
        const y = yAt(source.lat, source.lon, 0);
        const selected = selection.kind === "source" && selection.id === source.id;
        return (
          <group key={source.id} position={[x, y, z]}>
            {selected ? (
              <mesh position={[0, 0.018, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.1, 0.012, 10, 28]} />
                <meshBasicMaterial color="#ff6b57" />
              </mesh>
            ) : null}
            <mesh
              castShadow
              position={[0, 0.09, 0]}
              onClick={(event) => {
                event.stopPropagation();
                select({ kind: "source", id: source.id });
              }}
              onContextMenu={(event) =>
                onContext(event, {
                  kind: "source",
                  targetId: source.id,
                  lat: source.lat,
                  lon: source.lon,
                })
              }
            >
              <boxGeometry args={[0.14, 0.18, 0.14]} />
              <meshStandardMaterial
                color={selected ? "#e4463b" : "#3e8eb0"}
                emissive={selected ? "#7a2420" : "#102d38"}
                emissiveIntensity={0.35}
              />
            </mesh>
            {layers.labels ? (
              <Html center position={[0, 0.31, 0]} distanceFactor={3} zIndexRange={[10, 0]}>
                <span
                  className={`scene-label${selected ? " scene-label-selected" : ""}`}
                >
                  {source.name}
                </span>
              </Html>
            ) : null}
          </group>
        );
      })}
    </group>
  );
}

function SceneObjects({
  projector,
  scene,
  exaggeration,
  layers,
  showNodes,
}: {
  projector: TerrainProjector;
  scene: Scene;
  exaggeration: number;
  layers: LayerVisibility;
  showNodes: boolean;
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
            return new THREE.Vector3(x, yAt(c, 0.025), z);
          });
          return (
            <Line
              key={route.id}
              points={pts}
              color={route.mode === "trucking" ? "#c9922e" : "#d1352b"}
              lineWidth={selection.id === route.id ? 4 : route.mode === "trucking" ? 1.8 : 2.8}
              dashed={route.mode === "trucking"}
              dashSize={0.4}
              gapSize={0.3}
              onClick={(event) => {
                event.stopPropagation();
                select({ kind: "route", id: route.id });
              }}
            />
          );
        })}

      {/* Sources and wells. */}
      {layers.wells && showNodes && scene.nodes.map((node) => {
        const [x, z] = projector.toXZ(node.location);
        const y = yAt(node.location, 0);
        const selected = selection.id === node.id;
        return (
          <group key={node.id} position={[x, y, z]}>
            {selected && (
              <mesh position={[0, 0.018, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.09, 0.012, 10, 28]} />
                <meshBasicMaterial color="#ff6b57" />
              </mesh>
            )}
            {node.kind === "source" ? (
              <mesh
                castShadow
                position={[0, 0.09, 0]}
                onClick={(e) => {
                  e.stopPropagation();
                  select({ kind: "source", id: node.id });
                }}
              >
                <boxGeometry args={[0.14, 0.18, 0.14]} />
                <meshStandardMaterial
                  color={selected ? "#e4463b" : "#3e8eb0"}
                  emissive={selected ? "#7a2420" : "#102d38"}
                  emissiveIntensity={0.35}
                />
              </mesh>
            ) : (
              <mesh
                castShadow
                position={[0, 0.12, 0]}
                onClick={(e) => {
                  e.stopPropagation();
                  select({ kind: "well", id: node.id });
                }}
              >
                <cylinderGeometry args={[0.04, 0.04, 0.24, 10]} />
                <meshStandardMaterial
                  color={selected ? "#e4463b" : node.dim ? "#5a6068" : "#cfd4da"}
                  emissive={selected ? "#7a2420" : "#000000"}
                  emissiveIntensity={selected ? 0.6 : 0}
                />
              </mesh>
            )}
            {layers.labels && (
              <Html center position={[0, 0.32, 0]} distanceFactor={3} zIndexRange={[10, 0]}>
                <span className={`scene-label${selected ? " scene-label-selected" : ""}`}>
                  {node.id}
                </span>
              </Html>
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
            <mesh key={b.id} position={[x, y, z]} castShadow>
              <octahedronGeometry args={[0.28]} />
              <meshStandardMaterial color="#c9922e" />
            </mesh>
          );
        })}
    </group>
  );
}

function MeasurementOverlay({
  projector,
  exaggeration,
}: {
  projector: TerrainProjector;
  exaggeration: number;
}) {
  const points = useWorkspaceStore((s) => s.measurementPoints);
  const vectors = points.map((point) => {
    const [x, z] = projector.toXZ(point);
    return new THREE.Vector3(x, projector.heightOf(point.elevation_m, exaggeration) + 0.22, z);
  });
  return (
    <group>
      {vectors.map((point, index) => (
        <mesh key={index} position={point}>
          <sphereGeometry args={[0.11, 14, 14]} />
          <meshStandardMaterial color="#65d0df" emissive="#17434b" emissiveIntensity={0.55} />
        </mesh>
      ))}
      {vectors.length === 2 && (
        <Line points={vectors} color="#65d0df" lineWidth={2.2} dashed dashSize={0.22} gapSize={0.12} />
      )}
    </group>
  );
}

function ViewportNavigationHud({ projector }: { projector: TerrainProjector }) {
  const { extent, minElev, maxElev } = projector.data;
  const placement = useFieldStore((state) => state.placement);
  const centerLat = (extent.minLat + extent.maxLat) / 2;
  const centerLon = (extent.minLon + extent.maxLon) / 2;
  return (
    <div className="viewport-navigation-hud" aria-hidden>
      <div className="viewport-compass"><span>N</span><i /></div>
      <div>
        <strong>{(placement?.name ?? "Basin overview").toUpperCase()}</strong>
        <span>{Math.abs(centerLat).toFixed(3)}{"\u00b0S \u00b7 "}{centerLon.toFixed(3)}{"\u00b0E"}</span>
        <span>terrain {minElev.toFixed(0)}{"\u2013"}{maxElev.toFixed(0)} m MSL</span>
      </div>
    </div>
  );
}

const LAYER_OPTIONS: Array<[keyof ReturnType<typeof useWorkspaceStore.getState>["layers"], string]> = [
  ["terrain", "Terrain"],
  ["wells", "Wells"],
  ["labels", "Labels"],
  ["routes", "Routes"],
  ["boosters", "Boosters"],
  ["reservoir", "Reservoir cells"],
  ["reservoirGrid", "Cell edges"],
  ["propertyFill", "Property fill"],
  ["facies", "Facies overlay"],
  ["barriers", "Barriers"],
  ["fractures", "Fractures"],
  ["dynamicResponse", "Dynamic response"],
  ["responseColumns", "SECARB columns"],
];

function LayerManager() {
  const layers = useWorkspaceStore((state) => state.layers);
  const toggleLayer = useWorkspaceStore((state) => state.toggleLayer);
  const staticField = useWorkspaceStore((state) => state.reservoirStaticField);
  const setStaticField = useWorkspaceStore((state) => state.setReservoirStaticField);
  const opacity = useWorkspaceStore((state) => state.dynamicOpacity);
  const setOpacity = useWorkspaceStore((state) => state.setDynamicOpacity);
  const threshold = useWorkspaceStore((state) => state.plumeThreshold);
  const setThreshold = useWorkspaceStore((state) => state.setPlumeThreshold);
  return (
    <details className="layer-manager">
      <summary>Layers</summary>
      <div className="layer-manager-body">
        <div className="layer-manager-grid">
          {LAYER_OPTIONS.map(([key, label]) => (
            <label key={key}>
              <input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <label className="layer-manager-control">
          <span>Static property</span>
          <select value={staticField} onChange={(event) => setStaticField(event.target.value as StaticReservoirField)}>
            <option value="permeability_md">Permeability</option>
            <option value="porosity_fraction">Porosity</option>
            <option value="facies">Facies</option>
          </select>
        </label>
        <label className="layer-manager-control">
          <span>Dynamic opacity <strong>{Math.round(opacity * 100)}%</strong></span>
          <input type="range" min="0.05" max="0.9" step="0.05" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} />
        </label>
        <label className="layer-manager-control">
          <span>Plume threshold <strong>{threshold.toFixed(2)}</strong></span>
          <input type="range" min="0" max="0.25" step="0.005" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
        </label>
      </div>
    </details>
  );
}

function useSelectedReservoir(): {
  reservoir: ReservoirVisualization | null;
  prediction: PredictionResult | null;
  selectedWell: boolean;
} {
  const activeEntry = useLedgerStore((state) => state.entryById(state.activeEntryId));
  const selection = useSelectionStore((state) => state.selection);
  if (!activeEntry || selection.kind !== "well" || !selection.id) {
    return { reservoir: null, prediction: null, selectedWell: false };
  }
  const detailKeys = Object.keys(activeEntry.result.detailed_reservoirs ?? {});
  const scenarioId = selection.scenarioId
    ?? detailKeys.find((id) => id === selection.id || id.startsWith(`${selection.id}--`))
    ?? null;
  return {
    reservoir: scenarioId ? activeEntry.result.detailed_reservoirs?.[scenarioId] ?? null : null,
    prediction: scenarioId ? activeEntry.result.detailed_predictions?.[scenarioId] ?? null : null,
    selectedWell: true,
  };
}

function FieldLegend() {
  const { reservoir, prediction } = useSelectedReservoir();
  const staticField = useWorkspaceStore((state) => state.reservoirStaticField);
  const dynamicField = useWorkspaceStore((state) => state.colorField);
  if (!reservoir) return null;
  const staticValues = reservoir.static_fields[staticField].values;
  const staticRange = staticField === "permeability_md"
    ? finiteRange(staticValues, (value) => Math.log10(Math.max(value, 1e-6)))
    : finiteRange(staticValues);
  const dynamicAvailable = Boolean(prediction?.fields?.some((frame) => frame[dynamicField]));
  const metadata = reservoir.field_metadata[dynamicField];
  return (
    <div className="field-legend">
      <div className="field-legend-title">
        <span>LOCAL RESERVOIR MODEL</span>
        <strong>64 × 64 × 1</strong>
      </div>
      <div className={`field-legend-ramp ramp-${staticField}`} />
      <div className="field-legend-scale">
        <span>{formatLegend(staticRange[0])}</span>
        <span>{staticLabel(staticField)}</span>
        <span>{formatLegend(staticRange[1])}</span>
      </div>
      <p>
        900 × 600 × 6 m local proxy · static source: {String(
          reservoir.provenance.geometry_source_class ?? "declared reservoir input",
        ).replaceAll("_", " ")}
      </p>
      <div className="field-legend-dynamic">
        <span>{dynamicLabel(dynamicField)}</span>
        <strong>{dynamicAvailable ? metadata ? `${formatLegend(metadata.minimum)}–${formatLegend(metadata.maximum)} ${metadata.unit}` : "available" : "unavailable"}</strong>
      </div>
    </div>
  );
}

function ReservoirAvailability() {
  const { reservoir, selectedWell } = useSelectedReservoir();
  if (!selectedWell || reservoir) return null;
  return (
    <div className="reservoir-unavailable" role="status">
      <strong>Detailed reservoir not retained</strong>
      <span>Choose a shortlisted scenario or rerun with detailed fields enabled.</span>
    </div>
  );
}

function ViewportTimeline() {
  const step = useWorkspaceStore((s) => s.timelineStep);
  const count = useWorkspaceStore((s) => s.timelineFrameCount);
  const playing = useWorkspaceStore((s) => s.timelinePlaying);
  const setStep = useWorkspaceStore((s) => s.setTimelineStep);
  const togglePlaying = useWorkspaceStore((s) => s.toggleTimelinePlaying);
  const ratio = count > 1 ? step / (count - 1) : 0;
  const phase = ratio < 0.34 ? "INJECT" : ratio < 0.5 ? "SOAK" : "PRODUCE";
  return (
    <div className="viewport-timeline">
      <button type="button" onClick={togglePlaying} disabled={count === 0} aria-label={playing ? "Pause plume timeline" : "Play plume timeline"}>
        {playing ? "\u275a\u275a" : "\u25b6"}
      </button>
      <button type="button" onClick={() => setStep(step - 1)} disabled={count === 0 || step <= 0} aria-label="Previous plume frame">{"\u2039"}</button>
      <div className="viewport-timeline-track">
        <div><strong>{count ? phase : "PLUME"}</strong><span>{count ? `frame ${step + 1} / ${count}` : "select a well"}</span></div>
        <input
          aria-label="Plume timeline"
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          value={Math.min(step, Math.max(0, count - 1))}
          disabled={count === 0}
          onChange={(event) => setStep(Number(event.target.value))}
        />
      </div>
      <button type="button" onClick={() => setStep(step + 1)} disabled={count === 0 || step >= count - 1} aria-label="Next plume frame">{"\u203a"}</button>
    </div>
  );
}

function ViewportToolStatus() {
  const tool = useWorkspaceStore((s) => s.activeTool);
  const probe = useWorkspaceStore((s) => s.gridProbe);
  const points = useWorkspaceStore((s) => s.measurementPoints);
  if (tool === "select") return null;

  let detail = "Drag to orbit, scroll to zoom, and right-drag to pan.";
  if (tool === "probe") {
    detail = probe
      ? [
          `cell ${probe.i},${probe.j}`,
          probe.staticField && probe.staticValue != null
            ? `${staticLabel(probe.staticField)} ${formatProbe(probe.staticValue)}`
            : null,
          Number.isFinite(probe.colorValue)
            ? `${dynamicLabel(probe.colorField)} ${formatProbe(probe.colorValue)}`
            : null,
          probe.porosity != null ? `ϕ ${probe.porosity.toFixed(3)}` : null,
          probe.facies != null ? `facies ${Math.round(probe.facies)}` : null,
        ].filter(Boolean).join(" · ")
      : "Hover the reservoir grid to inspect cell values.";
  } else if (tool === "measure") {
    detail = points.length === 0
      ? "Click the terrain to set the first point."
      : points.length === 1
        ? "Click a second point to complete the measurement."
        : `${surfaceDistance(points[0], points[1]).toFixed(2)} km terrain distance \u00b7 \u0394z ${(points[1].elevation_m - points[0].elevation_m).toFixed(1)} m`;
  } else if (tool === "elevation") {
    detail = "Select a route to inspect its elevation and pressure profile.";
  }
  return (
    <div className="viewport-tool-status">
      <strong>{tool.toUpperCase()}</strong>
      <span>{detail}</span>
    </div>
  );
}

function fieldLabel(field: string): string {
  return ({
    z_co2: "z_CO\u2082",
    gas_saturation: "gas saturation",
    pressure_bar: "pressure (bar)",
    oil_saturation: "oil saturation",
  } as Record<string, string>)[field] ?? field;
}

function staticLabel(field: StaticReservoirField): string {
  return ({
    permeability_md: "log permeability (mD)",
    porosity_fraction: "porosity",
    facies: "facies",
  } as Record<StaticReservoirField, string>)[field];
}

function dynamicLabel(field: CellField): string {
  if (field === "pressure_bar") return "Δ pressure (bar)";
  if (field === "oil_saturation") return "oil depletion (fraction)";
  return fieldLabel(field);
}

function formatLegend(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function formatProbe(value: number): string {
  return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(3);
}

function surfaceDistance(a: Coordinate & { elevation_m: number }, b: Coordinate & { elevation_m: number }): number {
  const radians = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * radians;
  const dLon = (b.longitude - a.longitude) * radians;
  const lat1 = a.latitude * radians;
  const lat2 = b.latitude * radians;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  const horizontalKm = 6371.0088 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  const verticalKm = (b.elevation_m - a.elevation_m) / 1000;
  return Math.hypot(horizontalKm, verticalKm);
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
function CameraRig({ projector }: { projector: TerrainProjector }) {
  const { camera } = useThree();
  const controls = useRef<OrbitControlsImpl>(null);
  const destination = useRef<{ position: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const selection = useSelectionStore((s) => s.selection);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const motion = useWorkspaceStore((s) => s.cameraMotion);

  const selectedHasReservoir = useMemo(() => {
    if (!activeEntry || selection.kind !== "well" || !selection.id) return false;
    const keys = Object.keys(activeEntry.result.detailed_reservoirs ?? {});
    return Boolean(selection.scenarioId && keys.includes(selection.scenarioId))
      || keys.some((id) => id === selection.id || id.startsWith(`${selection.id}--`));
  }, [activeEntry, selection]);

  const selectedTarget = useMemo(() => {
    if (!activeEntry || !selection.id) return null;
    const coord = nodeCoordinateMap(activeEntry.request).get(selection.id);
    if (!coord) return null;
    const [x, z] = projector.toXZ(coord);
    const y = projector.heightOf(projector.elevationAt(coord), exaggeration);
    return new THREE.Vector3(x, y + 0.08, z);
  }, [activeEntry, exaggeration, projector, selection.id]);

  useEffect(() => {
    const move = (position: THREE.Vector3, target: THREE.Vector3) => {
      if (!motion) {
        camera.position.copy(position);
        controls.current?.target.copy(target);
        controls.current?.update();
        return;
      }
      destination.current = { position, target };
    };
    const reset = () => move(new THREE.Vector3(0, 12.5, 22), new THREE.Vector3(0, 0.35, 0));
    const frame = () => {
      if (!selectedTarget) return reset();
      const offset = selectedHasReservoir
        // A selected detailed case should read like a simulator reservoir view,
        // not a small annotation on the regional terrain. The local grid keeps
        // its physical 900:600 proportions; only the camera framing changes.
        ? new THREE.Vector3(1.25, 1.05, 1.7)
        : new THREE.Vector3(4.8, 5.4, 7.2);
      move(selectedTarget.clone().add(offset), selectedTarget.clone());
    };
    window.addEventListener("viewport:reset-camera", reset);
    window.addEventListener("viewport:frame-selection", frame);
    return () => {
      window.removeEventListener("viewport:reset-camera", reset);
      window.removeEventListener("viewport:frame-selection", frame);
    };
  }, [camera, motion, selectedHasReservoir, selectedTarget]);

  useEffect(() => {
    if (selectedTarget) window.dispatchEvent(new CustomEvent("viewport:frame-selection"));
  }, [selectedTarget]);

  useFrame(() => {
    const next = destination.current;
    if (!next || !controls.current) return;
    camera.position.lerp(next.position, 0.12);
    controls.current.target.lerp(next.target, 0.12);
    controls.current.update();
    if (camera.position.distanceTo(next.position) < 0.015 && controls.current.target.distanceTo(next.target) < 0.015) {
      camera.position.copy(next.position);
      controls.current.target.copy(next.target);
      controls.current.update();
      destination.current = null;
    }
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      enablePan
      maxPolarAngle={Math.PI / 2.08}
      minPolarAngle={0.2}
      minDistance={1.4}
      maxDistance={58}
      target={[0, 0.35, 0]}
    />
  );
}
