import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { PredictionResult } from "../api/types";
import { useWorkspaceStore } from "../state/workspace.store";
import { maxFrameCount } from "./wellPlates";

/**
 * The single owner of the global playback timeline. Exactly one instance is
 * mounted inside the Canvas; individual reservoir plates only READ the step.
 */
export function TimelineDriver({
  predictions,
}: {
  predictions: Array<PredictionResult | null | undefined>;
}) {
  const playing = useWorkspaceStore((state) => state.timelinePlaying);
  const step = useWorkspaceStore((state) => state.timelineStep);
  const setStep = useWorkspaceStore((state) => state.setTimelineStep);
  const setFrameCount = useWorkspaceStore((state) => state.setTimelineFrameCount);

  const count = useMemo(() => maxFrameCount(predictions), [predictions]);

  useEffect(() => {
    setFrameCount(count);
    return () => setFrameCount(0);
  }, [count, setFrameCount]);

  const accumulator = useRef(0);
  useFrame((_, delta) => {
    if (!playing || count === 0) return;
    accumulator.current += delta;
    if (accumulator.current > 0.18) {
      accumulator.current = 0;
      setStep((step + 1) % count);
    }
  });

  return null;
}
