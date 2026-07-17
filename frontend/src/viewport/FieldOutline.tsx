import { useEffect, useMemo, useRef } from "react";
import { Html, Line } from "@react-three/drei";
import { useThree, type ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import {
  useFieldStore,
  type FieldPlacement,
  type ReservoirRef,
} from "../state/field.store";
import { useWorkspaceStore } from "../state/workspace.store";
import { xzToCoordinate, type TerrainProjector } from "./terrain";

const METRES_PER_DEGREE_LATITUDE = 111_320;

/** True when a geographic point lies inside the placed, rotated field proxy. */
export function pointInField(
  lat: number,
  lon: number,
  placement: FieldPlacement,
  reservoir: ReservoirRef,
): boolean {
  const angle = (placement.rotation_deg * Math.PI) / 180;
  const north = (lat - placement.center_lat) * METRES_PER_DEGREE_LATITUDE;
  const east =
    (lon - placement.center_lon) *
    METRES_PER_DEGREE_LATITUDE *
    Math.cos((placement.center_lat * Math.PI) / 180);
  const localX = east * Math.cos(angle) + north * Math.sin(angle);
  const localY = -east * Math.sin(angle) + north * Math.cos(angle);
  const epsilon = 1e-6;
  return (
    Math.abs(localX) <= reservoir.length_x_m / 2 + epsilon &&
    Math.abs(localY) <= reservoir.length_y_m / 2 + epsilon
  );
}

export interface FieldOutlineProps {
  projector: TerrainProjector;
  placement: FieldPlacement;
  reservoir: ReservoirRef;
  interactive: boolean;
  onContextMenu?: (event: ThreeEvent<MouseEvent>) => void;
}

type DragMode = "move" | "rotate" | null;

interface CapturingEventTarget {
  setPointerCapture: (pointerId: number) => void;
  releasePointerCapture: (pointerId: number) => void;
}

function capturingTarget(event: ThreeEvent<PointerEvent>): CapturingEventTarget | null {
  const target = event.target as unknown as Partial<CapturingEventTarget> | null;
  return target &&
    typeof target.setPointerCapture === "function" &&
    typeof target.releasePointerCapture === "function"
    ? (target as CapturingEventTarget)
    : null;
}

/** Physical reservoir footprint placed on the basin terrain. */
export function FieldOutline({
  projector,
  placement,
  reservoir,
  interactive,
  onContextMenu,
}: FieldOutlineProps) {
  const exaggeration = useWorkspaceStore((state) => state.verticalExaggeration);
  const moveField = useFieldStore((state) => state.moveField);
  const rotateField = useFieldStore((state) => state.rotateField);
  const enterField = useFieldStore((state) => state.enterField);
  const controls = useThree((state) => state.controls) as
    | { enabled: boolean }
    | null;
  const dragMode = useRef<DragMode>(null);
  const activePointer = useRef<number | null>(null);
  const captureTarget = useRef<CapturingEventTarget | null>(null);
  const controlsWereEnabled = useRef<boolean | null>(null);
  const grabOffset = useRef({ x: 0, z: 0 });
  const dragPlane = useMemo(
    () => new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
    [],
  );
  const dragPoint = useMemo(() => new THREE.Vector3(), []);

  const center = useMemo(() => {
    const coordinate = {
      latitude: placement.center_lat,
      longitude: placement.center_lon,
    };
    const [x, z] = projector.toXZ(coordinate);
    const y =
      projector.heightOf(projector.elevationAt(coordinate), exaggeration) +
      0.035;
    return { x, y, z };
  }, [exaggeration, placement.center_lat, placement.center_lon, projector]);

  const width = reservoir.length_x_m / projector.metresPerSceneUnit;
  const depth = reservoir.length_y_m / projector.metresPerSceneUnit;
  const handleOffset = Math.max(0.08, Math.min(width, depth) * 0.15);
  const rotation = (placement.rotation_deg * Math.PI) / 180;
  const outlinePoints = useMemo(
    () => [
      [-width / 2, 0, -depth / 2] as [number, number, number],
      [width / 2, 0, -depth / 2] as [number, number, number],
      [width / 2, 0, depth / 2] as [number, number, number],
      [-width / 2, 0, depth / 2] as [number, number, number],
      [-width / 2, 0, -depth / 2] as [number, number, number],
    ],
    [depth, width],
  );

  const finishDrag = () => {
    const pointerId = activePointer.current;
    if (pointerId != null && captureTarget.current) {
      try {
        captureTarget.current.releasePointerCapture(pointerId);
      } catch {
        // Capture may already have been released by the browser.
      }
    }
    if (controls && controlsWereEnabled.current != null) {
      controls.enabled = controlsWereEnabled.current;
    }
    dragMode.current = null;
    activePointer.current = null;
    captureTarget.current = null;
    controlsWereEnabled.current = null;
    grabOffset.current = { x: 0, z: 0 };
    document.body.style.cursor = "";
  };

  useEffect(() => {
    const cancelDrag = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !dragMode.current) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      finishDrag();
    };
    window.addEventListener("keydown", cancelDrag, true);
    return () => {
      window.removeEventListener("keydown", cancelDrag, true);
      finishDrag();
    };
  }, [controls]);

  const beginDrag = (mode: Exclude<DragMode, null>) =>
    (event: ThreeEvent<PointerEvent>) => {
      if (!interactive || event.button !== 0) return;
      event.stopPropagation();
      event.nativeEvent.preventDefault();
      dragMode.current = mode;
      activePointer.current = event.pointerId;
      captureTarget.current = capturingTarget(event);
      captureTarget.current?.setPointerCapture(event.pointerId);
      controlsWereEnabled.current = controls?.enabled ?? null;
      if (controls) controls.enabled = false;
      dragPlane.constant = -center.y;
      if (event.ray.intersectPlane(dragPlane, dragPoint) && mode === "move") {
        grabOffset.current = {
          x: center.x - dragPoint.x,
          z: center.z - dragPoint.z,
        };
      }
      document.body.style.cursor = mode === "move" ? "grabbing" : "crosshair";
    };

  const drag = (event: ThreeEvent<PointerEvent>) => {
    if (!interactive || activePointer.current !== event.pointerId) return;
    event.stopPropagation();
    dragPlane.constant = -center.y;
    if (!event.ray.intersectPlane(dragPlane, dragPoint)) return;
    if (dragMode.current === "move") {
      const coordinate = xzToCoordinate(
        projector,
        dragPoint.x + grabOffset.current.x,
        dragPoint.z + grabOffset.current.z,
      );
      moveField(coordinate.latitude, coordinate.longitude);
      return;
    }
    if (dragMode.current === "rotate") {
      const east = dragPoint.x - center.x;
      const north = -(dragPoint.z - center.z);
      if (Math.hypot(east, north) < 1e-6) return;
      const degrees = (Math.atan2(north, east) * 180) / Math.PI;
      rotateField((degrees + 360) % 360);
    }
  };

  const endDrag = (event: ThreeEvent<PointerEvent>) => {
    if (activePointer.current !== event.pointerId) return;
    event.stopPropagation();
    finishDrag();
  };

  return (
    <group
      position={[center.x, center.y, center.z]}
      rotation={[0, rotation, 0]}
      onDoubleClick={
        interactive
          ? (event) => {
              event.stopPropagation();
              enterField();
            }
          : undefined
      }
      onContextMenu={onContextMenu}
    >
      <Line
        points={outlinePoints}
        color="#73d0da"
        lineWidth={1.7}
        transparent
        opacity={0.92}
      />
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        onPointerDown={beginDrag("move")}
        onPointerMove={drag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerOver={() => {
          if (interactive && !dragMode.current) document.body.style.cursor = "move";
        }}
        onPointerOut={() => {
          if (!dragMode.current) document.body.style.cursor = "";
        }}
      >
        <planeGeometry args={[width + handleOffset, depth + handleOffset]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <mesh
        position={[width / 2 + handleOffset, 0.015, 0]}
        onPointerDown={beginDrag("rotate")}
        onPointerMove={drag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerOver={() => {
          if (interactive && !dragMode.current) document.body.style.cursor = "crosshair";
        }}
        onPointerOut={() => {
          if (!dragMode.current) document.body.style.cursor = "";
        }}
      >
        <sphereGeometry args={[Math.max(0.035, handleOffset * 0.35), 14, 10]} />
        <meshStandardMaterial
          color="#8ee2e8"
          emissive="#163f45"
          emissiveIntensity={0.75}
          roughness={0.48}
        />
      </mesh>
      <Html
        center
        position={[0, 0.08, -depth / 2 - handleOffset * 0.65]}
        distanceFactor={3}
        zIndexRange={[12, 0]}
      >
        <span className="field-outline-label">{placement.name}</span>
      </Html>
    </group>
  );
}
