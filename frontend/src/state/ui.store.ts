import { create } from "zustand";

/** Transient UI state: which modal dialog is open, and dismissable banners. */

export type ModalKind =
  | null
  | "shortcuts"
  | "about"
  | "find"
  | "compare"
  | "preferences"
  | "validate"
  | "newStudy";

export interface Banner {
  id: string;
  severity: "info" | "warning" | "danger";
  message: string;
}

interface UiState {
  modal: ModalKind;
  newStudyTerrainId: string | null;
  banners: Banner[];
  openModal: (modal: ModalKind) => void;
  closeModal: () => void;
  setNewStudyTerrainId: (terrainId: string | null) => void;
  pushBanner: (banner: Banner) => void;
  dismissBanner: (id: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  modal: null,
  newStudyTerrainId: null,
  banners: [],
  openModal: (modal) => set({ modal }),
  closeModal: () => set({ modal: null, newStudyTerrainId: null }),
  setNewStudyTerrainId: (newStudyTerrainId) => set({ newStudyTerrainId }),
  pushBanner: (banner) =>
    set((s) => ({
      banners: [...s.banners.filter((b) => b.id !== banner.id), banner],
    })),
  dismissBanner: (id) =>
    set((s) => ({ banners: s.banners.filter((b) => b.id !== id) })),
}));
