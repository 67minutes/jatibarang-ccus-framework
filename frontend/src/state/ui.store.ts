import { create } from "zustand";

/** Transient UI state: which modal dialog is open, and dismissable banners. */

export type ModalKind =
  | null
  | "shortcuts"
  | "about"
  | "find"
  | "compare"
  | "preferences"
  | "validate";

export interface Banner {
  id: string;
  severity: "info" | "warning" | "danger";
  message: string;
}

interface UiState {
  modal: ModalKind;
  banners: Banner[];
  openModal: (modal: ModalKind) => void;
  closeModal: () => void;
  pushBanner: (banner: Banner) => void;
  dismissBanner: (id: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  modal: null,
  banners: [],
  openModal: (modal) => set({ modal }),
  closeModal: () => set({ modal: null }),
  pushBanner: (banner) =>
    set((s) => ({
      banners: [...s.banners.filter((b) => b.id !== banner.id), banner],
    })),
  dismissBanner: (id) =>
    set((s) => ({ banners: s.banners.filter((b) => b.id !== id) })),
}));
