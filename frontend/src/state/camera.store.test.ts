import { describe, expect, it } from "vitest";
import { compassRotationDeg, useCameraStore } from "./camera.store";

describe("camera store", () => {
  it("maps azimuthal radians to compass rotation degrees", () => {
    expect(compassRotationDeg(0)).toBe(0);
    expect(compassRotationDeg(Math.PI / 2)).toBeCloseTo(90);
    expect(compassRotationDeg(-Math.PI)).toBeCloseTo(-180);
  });

  it("stores the latest azimuth", () => {
    useCameraStore.getState().setAzimuthDeg(45);
    expect(useCameraStore.getState().azimuthDeg).toBe(45);
  });
});
