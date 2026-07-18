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
  fieldWindowBounds,
  makeProjector,
  terrainColor,
  TERRAIN_SIZE,
  xzToCoordinate,
  type TerrainData,
  type TerrainProjector,
} from "./terrain";
import { useFieldStore, type SceneLevel } from "../state/field.store";
import {
  ReservoirGrid,
  reservoirVisualizationFromImport,
} from "./ReservoirGrid";
import type { CellField, Coordinate, PredictionResult, ReservoirVisualization } from "../api/types";
import { finiteRange, type StaticReservoirField } from "./reservoirGeometry";
import { FieldOutline, pointInField } from "./FieldOutline";
import {
  SceneContextMenu,
  type SceneContextTarget,
} from "./SceneContextMenu";
import { SourceDialog, type SourceDialogValue } from "./SourceDialog";
import { InfluenceZones, influenceEntries } from "./InfluenceZones";
import {
  getTerrainWindow,
  listTerrains,
  type RegisteredTerrain,
} from "../api/client";
import { scientificDisplayText } from "../ui/presentation";
import { useUiStore } from "../state/ui.store";
import { compassRotationDeg, useCameraStore } from "../state/camera.store";
import { MapContextLayers } from "./MapContextLayers";
import { EarthGlobe } from "./EarthGlobe";
import "./viewport.css";

const DEG2RAD = Math.PI / 180;

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
  const level = useFieldStore((state) => state.level);
  const wells = useFieldStore((state) => state.wells);
  const sources = useFieldStore((state) => state.sources);
  const modal = useUiStore((state) => state.modal);
  const activeEntry = useLedgerStore((state) =>
    state.entryById(state.activeEntryId),
  );
  const readOnlySummary =
    activeEntry?.requestPayloadMode === "artifact_referenced";
  const selection = useSelectionStore((state) => state.selection);
  const select = useSelectionStore((state) => state.select);
  const clearSelection = useSelectionStore((state) => state.clear);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [contextTarget, setContextTarget] = useState<SceneContextTarget | null>(null);
  const [sourceEditor, setSourceEditor] = useState<SourceEditorState | null>(null);
  const [fieldWindow, setFieldWindow] = useState<TerrainData | null>(null);
  const [fieldWindowLoading, setFieldWindowLoading] = useState(false);
  const [terrains, setTerrains] = useState<RegisteredTerrain[]>([]);
  const fieldReady = level === "field" && fieldWindow !== null;
  const sceneLevel: SceneLevel = fieldReady ? "field" : "basin";
  const terrainData = fieldReady ? fieldWindow : terrainOverview;
  const projector = useMemo(
    () => (terrainData ? makeProjector(terrainData) : null),
    [terrainData],
  );

  useEffect(() => {
    if (!readOnlySummary) return;
    setContextTarget(null);
    setSourceEditor(null);
  }, [readOnlySummary]);

  useEffect(() => {
    let cancelled = false;
    void listTerrains()
      .then((records) => {
        if (!cancelled) setTerrains(records);
      })
      .catch(() => {
        if (!cancelled) setTerrains([]);
      });
    return () => {
      cancelled = true;
    };
  }, [terrain?.terrain_id]);

  useEffect(() => {
    if (level !== "field") {
      setFieldWindow(null);
      setFieldWindowLoading(false);
      return;
    }
    if (!terrain || !placement || !reservoir) return;

    let cancelled = false;
    setFieldWindow(null);
    setFieldWindowLoading(true);
    const bounds = fieldWindowBounds(
      { latitude: placement.center_lat, longitude: placement.center_lon },
      reservoir,
    );
    void getTerrainWindow(terrain.terrain_id, bounds, 768)
      .then((windowData) => {
        if (cancelled) return;
        setFieldWindow(windowData);
        setFieldWindowLoading(false);
        useUiStore.getState().dismissBanner("terrain-window-failed");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setFieldWindowLoading(false);
        useUiStore.getState().pushBanner({
          id: "terrain-window-failed",
          severity: "warning",
          message: `Field terrain window could not be loaded: ${
            error instanceof Error ? error.message : "unknown error"
          }`,
        });
        useFieldStore.getState().exitField();
      });
    return () => {
      cancelled = true;
    };
  }, [level, placement, reservoir, terrain]);

  useEffect(() => {
    const exitOnEscape = (event: KeyboardEvent) => {
      if (
        event.key !== "Escape" ||
        modal ||
        contextTarget ||
        sourceEditor ||
        event.defaultPrevented
      ) {
        return;
      }
      if (level === "field") {
        event.preventDefault();
        event.stopImmediatePropagation();
        useFieldStore.getState().exitField();
      } else if (level === "basin" && selection.kind === "none") {
        event.preventDefault();
        event.stopImmediatePropagation();
        useFieldStore.getState().exitBasin();
      }
    };
    window.addEventListener("keydown", exitOnEscape, true);
    return () => window.removeEventListener("keydown", exitOnEscape, true);
  }, [contextTarget, level, modal, selection.kind, sourceEditor]);

  const openContext = (
    event: ThreeEvent<MouseEvent>,
    request: SceneContextRequest,
  ) => {
    event.stopPropagation();
    event.nativeEvent.preventDefault();
    if (readOnlySummary && request.kind !== "outline") return;
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
    if (readOnlySummary) {
      setSourceEditor(null);
      return;
    }
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

  const handleDive = (terrainId: string) => {
    if (terrain?.terrain_id === terrainId) {
      useFieldStore.getState().enterBasin();
      return;
    }
    if (!terrain) {
      const ui = useUiStore.getState();
      ui.setNewStudyTerrainId(terrainId);
      ui.openModal("newStudy");
    }
  };

  if (level === "earth") {
    return (
      <div ref={wrapperRef} className="viewport-3d viewport-earth">
        <Canvas
          camera={{ position: [0, 8, 26], fov: 40, near: 0.1, far: 200 }}
          dpr={[1, 1.75]}
          gl={{
            antialias: true,
            preserveDrawingBuffer: true,
            powerPreference: "high-performance",
          }}
          onCreated={({ gl }) => {
            gl.toneMapping = THREE.ACESFilmicToneMapping;
            gl.toneMappingExposure = 1.02;
            gl.outputColorSpace = THREE.SRGBColorSpace;
          }}
        >
          <color attach="background" args={["#050a0d"]} />
          <ambientLight intensity={0.5} />
          <directionalLight
            position={[-12, 9, 16]}
            color="#fff1d6"
            intensity={2.2}
          />
          <directionalLight
            position={[10, -5, -12]}
            color="#315b72"
            intensity={0.55}
          />
          <EarthGlobe
            terrains={terrains}
            activeTerrainId={terrain?.terrain_id ?? null}
            onDive={handleDive}
          />
          <OrbitControls
            makeDefault
            target={[0, 0, 0]}
            enableDamping
            dampingFactor={0.07}
            enablePan={false}
            minDistance={13}
            maxDistance={40}
          />
        </Canvas>
        {terrains.length === 0 && !terrain ? (
          <div className="viewport-empty-hint viewport-earth-hint">
            <strong>No study loaded</strong>
            <span>New Study — Ctrl+N · Open Study — Ctrl+O</span>
          </div>
        ) : null}
        <div className="viewport-mode-tag">3D {"\u00b7"} earth</div>
      </div>
    );
  }

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
          <span>
            Create a new study and re-import the terrain to restore this scene.
          </span>
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
        <SceneContent
          projector={projector}
          level={sceneLevel}
          onContext={openContext}
        />
        <CameraRig projector={projector} level={sceneLevel} />
      </Canvas>
      {level === "field" && placement && reservoir ? (
          <button
            type="button"
            className="field-breadcrumb"
            onClick={() => useFieldStore.getState().exitField()}
          >
            {"\u25c2 Basin"}
          </button>
      ) : level === "basin" ? (
        <>
          <button
            type="button"
            className="field-breadcrumb"
            onClick={() => useFieldStore.getState().exitBasin()}
          >
            {"\u25c2 Earth"}
          </button>
          {placement && reservoir ? (
          <button
            type="button"
            className="field-breadcrumb field-entry"
            onClick={() => useFieldStore.getState().enterField()}
            aria-label="Enter field view"
            title="Open the high-resolution field view"
          >
            {"Field \u25b8"}
          </button>
          ) : null}
        </>
      ) : null}
      {level === "field" && !fieldReady ? (
        <div className="field-window-loading" role="status">
          <span className="field-window-spinner" aria-hidden="true" />
          <span>
            {fieldWindowLoading
              ? "Loading high-resolution field terrain\u2026"
              : "Preparing field terrain\u2026"}
          </span>
        </div>
      ) : null}
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
            !readOnlySummary &&
            setSourceEditor({ lat: contextTarget.lat, lon: contextTarget.lon })
          }
          onAddWell={() => {
            if (readOnlySummary) return;
            const created = useFieldStore
              .getState()
              .addWell(contextTarget.lat, contextTarget.lon);
            select({ kind: "well", id: created.id });
          }}
          onRenameWell={(name) => {
            if (readOnlySummary) return;
            if (contextTarget.targetId) {
              useFieldStore.getState().renameWell(contextTarget.targetId, name);
            }
          }}
          onRemoveWell={() => {
            if (readOnlySummary) return;
            if (!contextTarget.targetId) return;
            useFieldStore.getState().removeWell(contextTarget.targetId);
            if (selection.id === contextTarget.targetId) clearSelection();
          }}
          onEditSource={() => {
            if (readOnlySummary) return;
            if (!contextSource) return;
            setSourceEditor({
              sourceId: contextSource.id,
              lat: contextSource.lat,
              lon: contextSource.lon,
            });
          }}
          onRemoveSource={() => {
            if (readOnlySummary) return;
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
      <ViewportNavigationHud projector={projector} level={sceneLevel} />
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
      <div className="viewport-mode-tag">3D {"\u00b7"} {sceneLevel}</div>
    </div>
  );
}

function SceneContent({
  projector,
  level,
  onContext,
}: {
  projector: TerrainProjector;
  level: SceneLevel;
  onContext: (
    event: ThreeEvent<MouseEvent>,
    request: SceneContextRequest,
  ) => void;
}) {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const readOnlySummary =
    activeEntry?.requestPayloadMode === "artifact_referenced";
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const layers = useWorkspaceStore((s) => s.layers);
  const activeTool = useWorkspaceStore((s) => s.activeTool);
  const placement = useFieldStore((s) => s.placement);
  const reservoir = useFieldStore((s) => s.reservoir);
  const reservoirRuntime = useFieldStore((s) => s.reservoirRuntime);
  const fieldWells = useFieldStore((s) => s.wells);
  const importedReservoir = useMemo(
    () => reservoirVisualizationFromImport(reservoirRuntime),
    [reservoirRuntime],
  );

  const plan = activeEntry ? selectPlan(activeEntry.result, carbonPriceId) : null;
  const scene = useMemo<Scene | null>(
    () => (activeEntry ? collectSceneObjects(activeEntry.request, plan) : null),
    [activeEntry, plan],
  );
  const influence = useMemo(
    () =>
      activeEntry
        ? influenceEntries(activeEntry.result, plan, fieldWells)
        : [],
    [activeEntry, fieldWells, plan],
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

  const fieldSpot = useMemo(() => {
    if (level !== "field" || !placement || !reservoir) return null;
    const coordinate = {
      latitude: placement.center_lat,
      longitude: placement.center_lon,
    };
    const [x, z] = projector.toXZ(coordinate);
    return {
      xz: [x, z] as [number, number],
      groundY: projector.heightOf(
        projector.elevationAt(coordinate),
        exaggeration,
      ),
      rotation: [0, -placement.rotation_deg * DEG2RAD, 0] as [
        number,
        number,
        number,
      ],
    };
  }, [exaggeration, level, placement, projector, reservoir]);

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
      {level === "basin" &&
      (layers.roads || layers.coastline || layers.places) ? (
        <MapContextLayers
          projector={projector}
          exaggeration={exaggeration}
          layers={layers}
        />
      ) : null}
      {level === "basin" && placement && reservoir ? (
        <FieldOutline
          projector={projector}
          placement={placement}
          reservoir={reservoir}
          interactive={activeTool === "select" && !readOnlySummary}
          onContextMenu={(event) =>
            onContext(event, {
              kind: "outline",
              lat: placement.center_lat,
              lon: placement.center_lon,
            })
          }
        />
      ) : null}
      {layers.influence && influence.length > 0 ? (
        <InfluenceZones
          projector={projector}
          entries={influence}
          exaggeration={exaggeration}
        />
      ) : null}
      <FieldObjects
        projector={projector}
        exaggeration={exaggeration}
        layers={layers}
        onContext={onContext}
      />
      {level === "basin" && scene && (
        <SceneObjects
          projector={projector}
          scene={scene}
          exaggeration={exaggeration}
          layers={layers}
          showNodes={!placement}
        />
      )}
      {level === "basin" && wellSpot && (
        <ReservoirGrid
          position={wellSpot.xz}
          groundY={wellSpot.groundY}
          metresPerSceneUnit={projector.metresPerSceneUnit}
        />
      )}
      {fieldSpot && (
        <ReservoirGrid
          position={fieldSpot.xz}
          groundY={fieldSpot.groundY}
          metresPerSceneUnit={projector.metresPerSceneUnit}
          rotation={fieldSpot.rotation}
          fallbackReservoir={importedReservoir}
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

function ViewportNavigationHud({
  projector,
  level,
}: {
  projector: TerrainProjector;
  level: SceneLevel;
}) {
  const azimuthDeg = useCameraStore((state) => state.azimuthDeg);
  const { extent, minElev, maxElev } = projector.data;
  const placement = useFieldStore((state) => state.placement);
  const centerLat = (extent.minLat + extent.maxLat) / 2;
  const centerLon = (extent.minLon + extent.maxLon) / 2;
  return (
    <div
      className={`viewport-navigation-hud${level === "field" ? " viewport-navigation-hud-field" : ""}`}
      aria-hidden
    >
      <div
        className="viewport-compass"
        style={{ transform: `rotate(${azimuthDeg}deg)` }}
      >
        <span>N</span><i />
      </div>
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
  ["roads", "Roads"],
  ["coastline", "Coastline"],
  ["places", "Place labels"],
  ["wells", "Wells"],
  ["labels", "Labels"],
  ["routes", "Routes"],
  ["boosters", "Boosters"],
  ["influence", "Influence zones"],
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
  const level = useFieldStore((state) => state.level);
  const reservoirRuntime = useFieldStore((state) => state.reservoirRuntime);
  const importedReservoir = useMemo(
    () => reservoirVisualizationFromImport(reservoirRuntime),
    [reservoirRuntime],
  );
  const selectedWell = selection.kind === "well" && Boolean(selection.id);
  const detailKeys = activeEntry && selectedWell
    ? Object.keys(activeEntry.result.detailed_reservoirs ?? {})
    : [];
  const scenarioId = selectedWell
    ? selection.scenarioId
      ?? detailKeys.find((id) => id === selection.id || id.startsWith(`${selection.id}--`))
      ?? null
    : null;
  const detailedReservoir = scenarioId
    ? activeEntry?.result.detailed_reservoirs?.[scenarioId] ?? null
    : null;
  if (detailedReservoir) {
    return {
      reservoir: detailedReservoir,
      prediction: scenarioId
        ? activeEntry?.result.detailed_predictions?.[scenarioId] ?? null
        : null,
      selectedWell,
    };
  }
  return {
    reservoir: level === "field" ? importedReservoir : null,
    prediction: null,
    selectedWell,
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
        {formatLegend(reservoir.grid.length_x_m)} × {formatLegend(reservoir.grid.length_y_m)} × {formatLegend(reservoir.grid.thickness_m)} m local proxy · static source: {scientificDisplayText(
          String(
            reservoir.provenance.geometry_source_class ??
              "declared reservoir input",
          ).replaceAll("_", " "),
        )}
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
  const level = useFieldStore((state) => state.level);
  const readOnlySummary = useLedgerStore(
    (state) =>
      state.entryById(state.activeEntryId)?.requestPayloadMode ===
      "artifact_referenced",
  );
  if (level === "field" && !reservoir) {
    return (
      <div className="reservoir-unavailable" role="status">
        <strong>Reservoir model unavailable</strong>
        <span>
          Create a new study and re-import the MRST model to restore the field
          grid.
        </span>
      </div>
    );
  }
  if (!selectedWell || reservoir) return null;
  return (
    <div className="reservoir-unavailable" role="status">
      <strong>Detailed reservoir not retained</strong>
      <span>
        {readOnlySummary
          ? "This saved result summary omits cell fields. Create a new study and re-import the reservoir to regenerate them."
          : "Choose a shortlisted scenario or rerun with detailed fields enabled."}
      </span>
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

interface CameraDestination {
  fromPosition: THREE.Vector3;
  fromTarget: THREE.Vector3;
  position: THREE.Vector3;
  target: THREE.Vector3;
  elapsed: number;
  duration: number;
}

/** Handles level transitions and the View > Reset Camera command. */
function CameraRig({
  projector,
  level,
}: {
  projector: TerrainProjector;
  level: SceneLevel;
}) {
  const { camera } = useThree();
  const controls = useRef<OrbitControlsImpl>(null);
  const destination = useRef<CameraDestination | null>(null);
  const lastAzimuth = useRef(0);
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const selection = useSelectionStore((s) => s.selection);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const motion = useWorkspaceStore((s) => s.cameraMotion);
  const placement = useFieldStore((state) => state.placement);
  const reservoir = useFieldStore((state) => state.reservoir);

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

  const fieldTarget = useMemo(() => {
    if (level !== "field" || !placement) return null;
    const coordinate = {
      latitude: placement.center_lat,
      longitude: placement.center_lon,
    };
    const [x, z] = projector.toXZ(coordinate);
    const y = projector.heightOf(projector.elevationAt(coordinate), exaggeration);
    return new THREE.Vector3(x, y + 0.08, z);
  }, [exaggeration, level, placement, projector]);

  const fieldOffset = useMemo(() => {
    const span = reservoir
      ? Math.max(reservoir.length_x_m, reservoir.length_y_m) /
        projector.metresPerSceneUnit
      : 3;
    return new THREE.Vector3(
      Math.max(3.8, span * 1.15),
      Math.max(3.2, span * 0.9),
      Math.max(5.2, span * 1.6),
    );
  }, [projector.metresPerSceneUnit, reservoir]);

  useEffect(() => {
    const move = (position: THREE.Vector3, target: THREE.Vector3) => {
      if (!motion) {
        destination.current = null;
        camera.position.copy(position);
        controls.current?.target.copy(target);
        controls.current?.update();
        return;
      }
      destination.current = {
        fromPosition: camera.position.clone(),
        fromTarget:
          controls.current?.target.clone() ?? new THREE.Vector3(0, 0.35, 0),
        position,
        target,
        elapsed: 0,
        duration: 0.6,
      };
    };
    const reset = () => {
      if (level === "field" && fieldTarget) {
        move(fieldTarget.clone().add(fieldOffset), fieldTarget.clone());
      } else {
        move(
          new THREE.Vector3(0, 12.5, 22),
          new THREE.Vector3(0, 0.35, 0),
        );
      }
    };
    const frame = () => {
      if (level === "field" && fieldTarget) return reset();
      if (!selectedTarget) return reset();
      const offset = selectedHasReservoir
        ? new THREE.Vector3(1.25, 1.05, 1.7)
        : new THREE.Vector3(4.8, 5.4, 7.2);
      move(selectedTarget.clone().add(offset), selectedTarget.clone());
    };
    window.addEventListener("viewport:reset-camera", reset);
    window.addEventListener("viewport:frame-selection", frame);
    if (level === "field" || selectedTarget) frame();
    else reset();
    return () => {
      window.removeEventListener("viewport:reset-camera", reset);
      window.removeEventListener("viewport:frame-selection", frame);
    };
  }, [camera, fieldOffset, fieldTarget, level, motion, selectedHasReservoir, selectedTarget]);

  useFrame((_, delta) => {
    if (controls.current) {
      const azimuth = Math.round(
        compassRotationDeg(controls.current.getAzimuthalAngle()),
      );
      if (azimuth !== lastAzimuth.current) {
        lastAzimuth.current = azimuth;
        useCameraStore.getState().setAzimuthDeg(azimuth);
      }
    }
    const next = destination.current;
    if (!next || !controls.current) return;
    next.elapsed = Math.min(next.duration, next.elapsed + delta);
    const progress = next.elapsed / next.duration;
    const eased = progress * progress * (3 - 2 * progress);
    camera.position.lerpVectors(next.fromPosition, next.position, eased);
    controls.current.target.lerpVectors(next.fromTarget, next.target, eased);
    controls.current.update();
    if (progress >= 1) destination.current = null;
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
