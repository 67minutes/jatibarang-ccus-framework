import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import type {
  CellField,
  Grid2D,
  PredictionResult,
  ReservoirVisualization,
} from "../api/types";
import type { ReservoirImportResponse } from "../api/client";
import { useWorkspaceStore } from "../state/workspace.store";
import { frameAtStep, framesFromPrediction } from "./plume";
import { gridToInstances, type PlumeFrame } from "./grid";
import {
  buildReservoirGridLines,
  buildReservoirMesh,
  cellFromFaceIndex,
  dynamicColors,
  dynamicValues,
  finiteRange,
  staticColors,
  type DynamicReservoirField,
  type MeshArrays,
  type PhysicalGrid,
  type StaticReservoirField,
} from "./reservoirGeometry";

interface Props {
  position: [number, number];
  groundY: number;
  metresPerSceneUnit: number;
  rotation?: [number, number, number];
  /** Static geology for this plate — retained detailed fields or relinked import. */
  reservoir: ReservoirVisualization;
  /** Retained detailed prediction driving plume playback, when available. */
  prediction?: PredictionResult | null;
}

const STATIC_FIELD_SPECS = {
  permeability_md: ["Permeability", "mD", "log10"],
  porosity_fraction: ["Porosity", "fraction", "linear"],
  structure_m: ["Relative structure", "m", "linear"],
  fracture_proxy: ["Fracture proxy", "fraction", "linear"],
  barrier: ["Barrier", "fraction", "binary"],
  facies: ["Facies", "code", "categorical"],
  well_mask: ["Well mask", "fraction", "binary"],
  completion_mask: ["Completion mask", "fraction", "binary"],
} as const;

function importedGrid(value: unknown): Grid2D | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { shape?: unknown; values?: unknown };
  if (
    !Array.isArray(candidate.shape) ||
    candidate.shape.length !== 2 ||
    candidate.shape[0] !== 64 ||
    candidate.shape[1] !== 64 ||
    !Array.isArray(candidate.values) ||
    candidate.values.length !== 64 * 64 ||
    candidate.values.some(
      (item) => typeof item !== "number" || !Number.isFinite(item),
    )
  ) {
    return null;
  }
  return { shape: [64, 64], values: candidate.values as number[] };
}

function finitePositive(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : null;
}

function seedBaseline(
  seed: Record<string, unknown>,
): ReservoirVisualization["baseline_state"] {
  const frames = seed.frames;
  if (!Array.isArray(frames) || frames.length === 0) return null;
  const last = frames[frames.length - 1];
  if (!last || typeof last !== "object") return null;
  const state = last as Record<string, unknown>;
  const pressure = importedGrid(state.pressure_bar);
  const gas = importedGrid(state.gas_saturation);
  const zCo2 = importedGrid(state.z_co2);
  if (!pressure || !gas || !zCo2) return null;
  return {
    pressure_bar: pressure,
    gas_saturation: gas,
    z_co2: zCo2,
    oil_saturation: null,
  };
}

/**
 * Convert an imported MRST model to the same static contract used by retained
 * screening results. Invalid or incomplete imports stay unavailable; the
 * viewport never manufactures a demo grid in their place.
 */
export function reservoirVisualizationFromImport(
  imported: ReservoirImportResponse | null,
): ReservoirVisualization | null {
  if (!imported || !imported.geology || typeof imported.geology !== "object") {
    return null;
  }
  const geology = imported.geology as Record<string, unknown>;
  const permeability = importedGrid(geology.permeability_md);
  const porosity = importedGrid(geology.porosity_fraction);
  const structure = importedGrid(geology.structure_m);
  const fractures = importedGrid(geology.fracture_proxy);
  const barriers = importedGrid(geology.barrier);
  const facies = importedGrid(geology.facies);
  const wellMask = importedGrid(geology.well_mask);
  const completionMask = importedGrid(geology.completion_mask);
  const lengthX = finitePositive(geology.length_x_m);
  const lengthY = finitePositive(geology.length_y_m);
  const thickness = finitePositive(geology.thickness_m);
  if (
    !permeability ||
    !porosity ||
    !structure ||
    !fractures ||
    !barriers ||
    !facies ||
    !wellMask ||
    !completionMask ||
    !lengthX ||
    !lengthY ||
    !thickness
  ) {
    return null;
  }

  const staticFields = {
    permeability_md: permeability,
    porosity_fraction: porosity,
    structure_m: structure,
    fracture_proxy: fractures,
    barrier: barriers,
    facies,
    well_mask: wellMask,
    completion_mask: completionMask,
  };
  const metadata: ReservoirVisualization["field_metadata"] = {};
  for (const [name, [label, unit, scale]] of Object.entries(
    STATIC_FIELD_SPECS,
  )) {
    const grid = staticFields[name as keyof typeof staticFields];
    const [minimum, maximum] = finiteRange(grid.values);
    metadata[name] = {
      label,
      unit,
      minimum,
      maximum,
      scale,
      source_class: "mrst_derived_geology",
    };
  }

  const baseline = seedBaseline(imported.native_seed);
  const baselineSourceClass =
    typeof imported.native_seed.source_class === "string"
      ? imported.native_seed.source_class
      : "mrst_ground_truth";
  if (baseline) {
    for (const [name, label, unit] of [
      ["pressure_bar", "Pressure", "bar"],
      ["gas_saturation", "Gas saturation", "fraction"],
      ["z_co2", "CO2 composition", "fraction"],
    ] as const) {
      const [minimum, maximum] = finiteRange(baseline[name].values);
      metadata[name] = {
        label,
        unit,
        minimum,
        maximum,
        scale: "linear",
        source_class: baselineSourceClass,
      };
    }
  }

  return {
    scenario_id: `imported:${imported.model_id}`,
    geology_id: imported.model_id,
    grid: {
      nx: 64,
      ny: 64,
      nz: 1,
      length_x_m: lengthX,
      length_y_m: lengthY,
      thickness_m: thickness,
    },
    static_fields: staticFields,
    baseline_state: baseline,
    field_metadata: metadata,
    provenance: {
      coordinate_reference: "local_proxy_grid",
      geometry_source_class: "mrst_derived_geology",
      geometry_source_id: imported.sha256,
      baseline_source_class: baselineSourceClass,
      baseline_source_id:
        typeof imported.native_seed.source_id === "string"
          ? imported.native_seed.source_id
          : imported.native_fingerprint,
      baseline_frame_index: baseline ? 7 : null,
      baseline_semantics: baseline ? "final_warm_start_frame" : "unavailable",
      vertical_layers: 1,
      surveyed_orientation: false,
    },
  };
}

/**
 * A simulator-style local reservoir model. The mesh uses the real 900 x 600 x
 * 6 m single-layer contract and the MRST structure surface; no fake K-layers
 * or surveyed depth are implied. The old response columns remain opt-in.
 */
export function ReservoirGrid({
  position,
  groundY,
  metresPerSceneUnit,
  rotation = [0, 0, 0],
  reservoir,
  prediction = null,
}: Props) {
  const layers = useWorkspaceStore((state) => state.layers);
  const staticField = useWorkspaceStore((state) => state.reservoirStaticField);
  const dynamicField = useWorkspaceStore((state) => state.colorField);
  const verticalExaggeration = useWorkspaceStore((state) => state.reservoirVerticalExaggeration);
  const dynamicOpacity = useWorkspaceStore((state) => state.dynamicOpacity);
  const plumeThreshold = useWorkspaceStore((state) => state.plumeThreshold);
  const step = useWorkspaceStore((state) => state.timelineStep);
  const playing = useWorkspaceStore((state) => state.timelinePlaying);
  const setStep = useWorkspaceStore((state) => state.setTimelineStep);
  const setFrameCount = useWorkspaceStore((state) => state.setTimelineFrameCount);

  const frames = useMemo(
    () => (prediction ? framesFromPrediction(prediction) : []),
    [prediction],
  );

  useEffect(() => {
    setFrameCount(frames.length);
    return () => setFrameCount(0);
  }, [frames.length, setFrameCount]);

  const accumulator = useRef(0);
  useFrame((_, delta) => {
    if (!playing || frames.length === 0) return;
    accumulator.current += delta;
    if (accumulator.current > 0.18) {
      accumulator.current = 0;
      setStep((step + 1) % frames.length);
    }
  });

  if (!reservoir || !layers.reservoir) return null;

  const frame = frameAtStep(frames, step);
  const scale = 1 / metresPerSceneUnit;
  // The local datum is lifted only enough to avoid terrain z-fighting. A leader
  // identifies that this is a local model, not its surveyed subsea elevation.
  const datumY = groundY + 0.035;

  return (
    <group
      position={[position[0], datumY, position[1]]}
      rotation={rotation}
      scale={[scale, scale * verticalExaggeration, scale]}
    >
      <LocalDatumLeader groundOffsetMetres={(datumY - groundY) / (scale * verticalExaggeration)} />
      <StaticReservoir
        reservoir={reservoir}
        field={staticField}
        showFill={layers.propertyFill}
        showGrid={layers.reservoirGrid}
        dynamicField={dynamicField}
        frame={frame}
      />
      {layers.facies && <FaciesOverlay reservoir={reservoir} />}
      {layers.barriers && <MaskOverlay reservoir={reservoir} field="barrier" color={[0.82, 0.28, 0.18]} />}
      {layers.fractures && <MaskOverlay reservoir={reservoir} field="fracture_proxy" color={[0.22, 0.78, 0.86]} threshold={0.35} />}
      {layers.dynamicResponse && frame && (
        <DynamicOverlay
          reservoir={reservoir}
          frame={frame}
          field={dynamicField}
          opacity={dynamicOpacity}
          plumeThreshold={plumeThreshold}
        />
      )}
      <WellAndCompletions reservoir={reservoir} />
      {layers.responseColumns && frame && (
        <ResponseColumns frame={frame} colorField={dynamicField} />
      )}
    </group>
  );
}

function physicalGrid(reservoir: ReservoirVisualization): PhysicalGrid {
  return {
    nx: reservoir.grid.nx,
    ny: reservoir.grid.ny,
    nz: reservoir.grid.nz,
    length_x_m: reservoir.grid.length_x_m,
    length_y_m: reservoir.grid.length_y_m,
    thickness_m: reservoir.grid.thickness_m,
  };
}

function values(reservoir: ReservoirVisualization, field: StaticReservoirField): number[] {
  return reservoir.static_fields[field].values;
}

function bufferGeometry(mesh: MeshArrays): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(mesh.positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(mesh.colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function StaticReservoir({
  reservoir,
  field,
  showFill,
  showGrid,
  dynamicField,
  frame,
}: {
  reservoir: ReservoirVisualization;
  field: StaticReservoirField;
  showFill: boolean;
  showGrid: boolean;
  dynamicField: CellField;
  frame: PlumeFrame | null;
}) {
  const activeTool = useWorkspaceStore((state) => state.activeTool);
  const setGridProbe = useWorkspaceStore((state) => state.setGridProbe);
  const rawValues = values(reservoir, field);
  const meshData = useMemo(() => {
    const colors = showFill
      ? staticColors(rawValues, field)
      : new Float32Array(rawValues.length * 3).fill(0.29);
    return buildReservoirMesh(
      physicalGrid(reservoir),
      reservoir.static_fields.structure_m.values,
      colors,
    );
  }, [field, rawValues, reservoir, showFill]);
  const geometry = useMemo(() => bufferGeometry(meshData), [meshData]);
  const lineData = useMemo(
    () => buildReservoirGridLines(physicalGrid(reservoir), reservoir.static_fields.structure_m.values),
    [reservoir],
  );
  const lineGeometry = useMemo(() => {
    const value = new THREE.BufferGeometry();
    value.setAttribute("position", new THREE.BufferAttribute(lineData.positions, 3));
    return value;
  }, [lineData]);

  useEffect(() => () => {
    geometry.dispose();
    lineGeometry.dispose();
  }, [geometry, lineGeometry]);

  const probe = (event: ThreeEvent<PointerEvent>) => {
    if (activeTool !== "probe") return;
    const index = cellFromFaceIndex(event.faceIndex ?? undefined, meshData.trianglesPerCell);
    if (index == null) return;
    event.stopPropagation();
    const dynamic = frame?.[dynamicField]?.[index];
    setGridProbe({
      i: index % reservoir.grid.nx,
      j: Math.floor(index / reservoir.grid.nx),
      colorField: dynamicField,
      colorValue: dynamic ?? Number.NaN,
      heightField: dynamicField,
      heightValue: dynamic ?? Number.NaN,
      staticField: field,
      staticValue: rawValues[index],
      porosity: reservoir.static_fields.porosity_fraction.values[index],
      facies: reservoir.static_fields.facies.values[index],
      structure_m: reservoir.static_fields.structure_m.values[index],
      barrier: reservoir.static_fields.barrier.values[index],
      fracture: reservoir.static_fields.fracture_proxy.values[index],
    });
  };

  return (
    <group>
      <mesh
        geometry={geometry}
        castShadow
        receiveShadow
        onPointerMove={probe}
        onPointerOut={() => activeTool === "probe" && setGridProbe(null)}
      >
        <meshStandardMaterial vertexColors roughness={0.72} metalness={0.03} side={THREE.DoubleSide} />
      </mesh>
      {showGrid && (
        <lineSegments geometry={lineGeometry}>
          <lineBasicMaterial color="#0b161a" transparent opacity={0.72} />
        </lineSegments>
      )}
    </group>
  );
}

function FaciesOverlay({ reservoir }: { reservoir: ReservoirVisualization }) {
  const raw = reservoir.static_fields.facies.values;
  const mesh = useMemo(
    () => buildReservoirMesh(
      physicalGrid(reservoir),
      reservoir.static_fields.structure_m.values,
      staticColors(raw, "facies"),
      undefined,
      true,
    ),
    [raw, reservoir],
  );
  return <ColoredMesh mesh={mesh} opacity={0.24} lift={0.035} />;
}

function MaskOverlay({
  reservoir,
  field,
  color,
  threshold = 0.5,
}: {
  reservoir: ReservoirVisualization;
  field: "barrier" | "fracture_proxy";
  color: [number, number, number];
  threshold?: number;
}) {
  const mask = reservoir.static_fields[field].values;
  const colors = useMemo(() => {
    const output = new Float32Array(mask.length * 3);
    for (let index = 0; index < mask.length; index++) output.set(color, index * 3);
    return output;
  }, [color, mask.length]);
  const mesh = useMemo(
    () => buildReservoirMesh(
      physicalGrid(reservoir),
      reservoir.static_fields.structure_m.values,
      colors,
      (index) => mask[index] >= threshold,
      true,
    ),
    [colors, mask, reservoir, threshold],
  );
  return <ColoredMesh mesh={mesh} opacity={field === "barrier" ? 0.72 : 0.58} lift={field === "barrier" ? 0.07 : 0.11} />;
}

function DynamicOverlay({
  reservoir,
  frame,
  field,
  opacity,
  plumeThreshold,
}: {
  reservoir: ReservoirVisualization;
  frame: PlumeFrame;
  field: DynamicReservoirField;
  opacity: number;
  plumeThreshold: number;
}) {
  const current = frame[field];
  const baseline = baselineField(reservoir, field)?.values;
  if (!current || ((field === "pressure_bar" || field === "oil_saturation") && !baseline)) return null;
  const transformed = dynamicValues(field, current, baseline);
  const metadata = reservoir.field_metadata[field];
  const range: [number, number] | undefined = metadata
    ? [metadata.minimum, metadata.maximum]
    : finiteRange(transformed);
  const colors = dynamicColors(transformed, field, range);
  const isPlume = field === "gas_saturation" || field === "z_co2";
  const mesh = buildReservoirMesh(
    physicalGrid(reservoir),
    reservoir.static_fields.structure_m.values,
    colors,
    isPlume ? (index) => transformed[index] >= plumeThreshold : undefined,
    !isPlume,
  );
  return <ColoredMesh mesh={mesh} opacity={opacity} lift={isPlume ? 0.09 : 0.15} />;
}

function baselineField(reservoir: ReservoirVisualization, field: DynamicReservoirField): Grid2D | undefined {
  const baseline = reservoir.baseline_state;
  if (!baseline) return undefined;
  if (field === "oil_saturation") return baseline.oil_saturation ?? undefined;
  return baseline[field];
}

function ColoredMesh({ mesh, opacity, lift }: { mesh: MeshArrays; opacity: number; lift: number }) {
  const geometry = useMemo(() => bufferGeometry(mesh), [mesh]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} position={[0, lift, 0]} renderOrder={3}>
      <meshStandardMaterial
        vertexColors
        transparent
        opacity={opacity}
        roughness={0.48}
        metalness={0.01}
        depthWrite={opacity > 0.7}
        polygonOffset
        polygonOffsetFactor={-1}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function WellAndCompletions({ reservoir }: { reservoir: ReservoirVisualization }) {
  const grid = physicalGrid(reservoir);
  const structure = reservoir.static_fields.structure_m.values;
  const path = maskPoints(reservoir.static_fields.well_mask.values, grid, structure, -grid.thickness_m * 0.45);
  const completions = maskPoints(reservoir.static_fields.completion_mask.values, grid, structure, -grid.thickness_m * 0.45);
  return (
    <group>
      {path.length >= 2 && <Line points={path} color="#f2eee3" lineWidth={2.2} />}
      {completions.map((point, index) => (
        <mesh key={index} position={point}>
          <sphereGeometry args={[Math.min(grid.length_x_m / grid.nx, grid.length_y_m / grid.ny) * 0.22, 8, 8]} />
          <meshStandardMaterial color="#f0a23a" emissive="#6b3210" emissiveIntensity={0.55} />
        </mesh>
      ))}
    </group>
  );
}

function maskPoints(mask: number[], grid: PhysicalGrid, structure: number[], yOffset: number): [number, number, number][] {
  const points: Array<{ i: number; j: number; p: [number, number, number] }> = [];
  for (let index = 0; index < mask.length; index++) {
    if (mask[index] < 0.5) continue;
    const i = index % grid.nx;
    const j = Math.floor(index / grid.nx);
    points.push({
      i,
      j,
      p: [
        ((i + 0.5) / grid.nx - 0.5) * grid.length_x_m,
        structure[index] + yOffset,
        ((j + 0.5) / grid.ny - 0.5) * grid.length_y_m,
      ],
    });
  }
  const spanI = Math.max(...points.map((item) => item.i), 0) - Math.min(...points.map((item) => item.i), 0);
  const spanJ = Math.max(...points.map((item) => item.j), 0) - Math.min(...points.map((item) => item.j), 0);
  points.sort((a, b) => spanI >= spanJ ? a.i - b.i || a.j - b.j : a.j - b.j || a.i - b.i);
  return points.map((item) => item.p);
}

function ResponseColumns({ frame, colorField }: { frame: PlumeFrame; colorField: CellField }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const instances = useMemo(
    () => frame[colorField]
      ? gridToInstances(frame, {
          heightField: colorField,
          colorField,
          footprintX: 900,
          footprintZ: 600,
          maxHeight: 150,
        })
      : null,
    [colorField, frame],
  );
  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh || !instances) return;
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    for (let index = 0; index < instances.count; index++) {
      dummy.position.set(instances.positions[index * 3], instances.positions[index * 3 + 1] + 0.2, instances.positions[index * 3 + 2]);
      dummy.scale.set(instances.cellSizeX * 0.88, instances.heights[index], instances.cellSizeZ * 0.88);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
      color.setRGB(instances.colors[index * 3], instances.colors[index * 3 + 1], instances.colors[index * 3 + 2]);
      mesh.setColorAt(index, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [instances]);
  if (!instances) return null;
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, instances.count]} renderOrder={4}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial transparent opacity={0.52} roughness={0.45} />
    </instancedMesh>
  );
}

function LocalDatumLeader({ groundOffsetMetres }: { groundOffsetMetres: number }) {
  if (groundOffsetMetres <= 0) return null;
  return (
    <mesh position={[0, -groundOffsetMetres / 2, 0]}>
      <cylinderGeometry args={[1.8, 2.8, groundOffsetMetres, 8]} />
      <meshStandardMaterial color="#5f8f98" emissive="#173238" emissiveIntensity={0.35} />
    </mesh>
  );
}
