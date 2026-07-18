import { create } from "zustand";

/**
 * Camera azimuth shared from inside the Canvas to the HTML HUD. North in the
 * scene is -Z (terrain.ts toXZ maps increasing latitude to -Z), so an
 * OrbitControls azimuthal angle of 0 means north is up on screen.
 */
interface CameraState {
  azimuthDeg: number;
  setAzimuthDeg: (value: number) => void;
}

export const useCameraStore = create<CameraState>((set) => ({
  azimuthDeg: 0,
  setAzimuthDeg: (azimuthDeg) => set({ azimuthDeg }),
}));

/** Screen rotation of the compass rose for a camera azimuthal angle. */
export function compassRotationDeg(azimuthalAngleRad: number): number {
  return (azimuthalAngleRad * 180) / Math.PI;
}
