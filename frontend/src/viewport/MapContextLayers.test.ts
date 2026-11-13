import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { lineSegmentPositions } from "./MapContextLayers";

describe("batched map context lines", () => {
  it("encodes disconnected polylines as independent line segments", () => {
    const positions = lineSegmentPositions([
      [new THREE.Vector3(0, 1, 2), new THREE.Vector3(3, 4, 5)],
      [
        new THREE.Vector3(6, 7, 8),
        new THREE.Vector3(9, 10, 11),
        new THREE.Vector3(12, 13, 14),
      ],
    ]);
    expect(Array.from(positions)).toEqual([
      0, 1, 2, 3, 4, 5,
      6, 7, 8, 9, 10, 11,
      9, 10, 11, 12, 13, 14,
    ]);
  });
});
