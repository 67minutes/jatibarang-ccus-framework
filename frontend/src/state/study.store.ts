import { create } from "zustand";

/**
 * Human-facing study metadata. Scientific identity remains the backend request
 * fingerprint; this metadata only makes files and ledger entries usable by
 * people. It is persisted inside exported study memos, never browser storage.
 */
export interface StudyMetadata {
  name: string;
  analyst: string;
  notes: string;
  memo_file_name: string;
  save_location_strategy: "ask_on_save";
  start_view: "2d" | "3d";
  vertical_exaggeration: number;
  created_at: string;
}

export interface NewStudyOptions {
  name: string;
  analyst: string;
  notes: string;
  template: "demo" | "current";
  memoFileName: string;
  startView: "2d" | "3d";
  verticalExaggeration: number;
}

interface StudyState {
  study: StudyMetadata;
  create: (options: NewStudyOptions) => void;
  load: (study: StudyMetadata) => void;
  setMemoFileName: (memoFileName: string) => void;
}

export const DEFAULT_STUDY_NAME = "Jatibarang screening study";

function safeMemoName(value: string): string {
  const stem = value
    .replace(/\.study\.json$/i, "")
    .replace(/[^a-z0-9._-]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 72);
  return `${stem || "jatibarang-study"}.study.json`;
}

function defaultStudy(): StudyMetadata {
  return {
    name: DEFAULT_STUDY_NAME,
    analyst: "",
    notes: "",
    memo_file_name: "jatibarang-screening-study.study.json",
    save_location_strategy: "ask_on_save",
    start_view: "3d",
    vertical_exaggeration: 5,
    created_at: new Date().toISOString(),
  };
}

export const useStudyStore = create<StudyState>((set) => ({
  study: defaultStudy(),
  create: (options) =>
    set({
      study: {
        name: options.name.trim() || DEFAULT_STUDY_NAME,
        analyst: options.analyst.trim(),
        notes: options.notes.trim(),
        memo_file_name: safeMemoName(options.memoFileName || options.name),
        save_location_strategy: "ask_on_save",
        start_view: options.startView,
        vertical_exaggeration: options.verticalExaggeration,
        created_at: new Date().toISOString(),
      },
    }),
  load: (study) => set({ study }),
  setMemoFileName: (memoFileName) =>
    set((s) => ({
      study: { ...s.study, memo_file_name: safeMemoName(memoFileName) },
    })),
}));
