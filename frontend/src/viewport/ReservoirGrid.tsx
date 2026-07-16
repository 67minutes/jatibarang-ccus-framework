import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { useWorkspaceStore } from "../state/workspace.store";
import { gridToInstances, type PlumeFrame } from "./grid";
import {
  frameAtStep,
  framesFromPrediction,
  loadDemoPlume,
} from "./plume";
import type { CellField } from "../api/types";

/**
 * The SECARB-style extruded reservoir grid (design §5.1): a subsurface cutaway
 * of 64×64 prisms beneath the selected well. Height encodes one per-cell field,
 * color another (binned). Animates across the timeline via the workspace scrubber.
 *
 * `position`/`groundY` place the cutaway just under the terrain at the well.
 */
export function ReservoirGrid({
  position,
  groundY,
}: {
  position: [number, number];
  groundY: number;
}) {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const selection = useSelectionStore((s) => s.selection);
  const colorField = useWorkspaceStore((s) => s.colorField);
  const heightField = useWorkspaceStore((s) => s.heightField);
  const step = useWorkspaceStore((s) => s.timelineStep);
  const playing = useWorkspaceStore((s) => s.timelinePlaying);
  const setStep = useWorkspaceStore((s) => s.setTimelineStep);

  const [demoFrames, setDemoFrames] = useState<PlumeFrame[] | null>(null);

  // Resolve frames: real detailed prediction fields, else the bundled demo plume.
  const realFrames = useMemo(() => {
    if (!activeEntry || selection.kind !== "well") return [];
    const scenarioId = selection.scenarioId;
    const detailed = scenarioId ? activeEntry.result.detailed_predictions[scenarioId] : undefined;
    return detailed ? framesFromPrediction(detailed) : [];
  }, [activeEntry, selection]);

  useEffect(() => {
    if (realFrames.length === 0) loadDemoPlume().then((p) => setDemoFrames(p?.frames ?? null));
  }, [realFrames.length]);

  const frames = realFrames.length > 0 ? realFrames : demoFrames ?? [];

  // Advance the timeline while playing.
  const acc = useRef(0);
  useFrame((_, delta) => {
    if (!playing || frames.length === 0) return;
    acc.current += delta;
    if (acc.current > 0.18) {
      acc.current = 0;
      setStep((step + 1) % frames.length);
    }
  });

  const frame = frameAtStep(frames, step);
  if (selection.kind !== "well" || !frame) return null;

  // Float the reservoir cutaway above the well as an extruded data panel, with a
  // thin stem connecting it to the wellhead so the association is clear. (An
  // opaque terrain mesh occludes a true subsurface placement.)
  const baseY = groundY + 3.4;
  return (
    <group position={[position[0], baseY, position[1]]}>
      <mesh position={[0, -(baseY - groundY) / 2, 0]}>
        <cylinderGeometry args={[0.03, 0.03, baseY - groundY, 6]} />
        <meshStandardMaterial color="#6b7178" />
      </mesh>
      <mesh position={[0, -0.06, 0]}>
        <boxGeometry args={[6.1, 0.08, 6.1]} />
        <meshStandardMaterial color="#14161a" />
      </mesh>
      <PrismField frame={frame} heightField={heightField} colorField={colorField} />
    </group>
  );
}

function PrismField({
  frame,
  heightField,
  colorField,
}: {
  frame: PlumeFrame;
  heightField: CellField;
  colorField: CellField;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const instances = useMemo(
    () => gridToInstances(frame, { heightField, colorField, footprint: 6, maxHeight: 2.6 }),
    [frame, heightField, colorField],
  );

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    for (let k = 0; k < instances.count; k++) {
      dummy.position.set(
        instances.positions[k * 3],
        instances.positions[k * 3 + 1],
        instances.positions[k * 3 + 2],
      );
      dummy.scale.set(instances.cellSize * 0.92, instances.heights[k], instances.cellSize * 0.92);
      dummy.updateMatrix();
      mesh.setMatrixAt(k, dummy.matrix);
      color.setRGB(
        instances.colors[k * 3],
        instances.colors[k * 3 + 1],
        instances.colors[k * 3 + 2],
      );
      mesh.setColorAt(k, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [instances]);

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, instances.count]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial roughness={0.7} metalness={0.05} />
    </instancedMesh>
  );
}
