import { useQuery } from "@tanstack/react-query";
import { getHealth, getPresets } from "./client";

/** Polled dependency readiness for the status-bar dot and preflight report. */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function usePresets() {
  return useQuery({
    queryKey: ["presets"],
    queryFn: getPresets,
    staleTime: 30_000,
  });
}
