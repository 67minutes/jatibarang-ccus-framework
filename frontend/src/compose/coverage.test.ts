import { describe, expect, it } from "vitest";
import type { OperationalGrid } from "../api/types";
import {
  comboFingerprint,
  coveredCombos,
  coveredGridSchedules,
  nativeScheduleAvailability,
  scheduleCombos,
  type ScheduleCombo,
} from "./coverage";

const STANDARD_GRID: OperationalGrid = {
  injection_rate_m3_day: [8000, 9000, 10000],
  injection_duration_days: [45],
  soak_duration_days: [25, 30, 35],
  production_duration_days: [170, 190, 210],
  production_bhp_psi: [650, 675, 700],
  cycles: [3, 4],
};

const CASE_0016_NATIVE: ScheduleCombo = {
  injection_rate_m3_day: 8687.177439504216,
  soak_duration_days: 28.126672556861426,
  production_duration_days: 199.0340798188366,
  production_bhp_psi: 669.0069852265157,
  cycles: 4,
};

const CASE_0016_NATIVE_FINGERPRINT =
  "E76B43C3F324821A90DCE393ACEEAB5FDF5C4AAF158639E2A37DCBDAC170E451";

describe("comboFingerprint", () => {
  it("matches the backend fingerprint for the case_0016 native schedule", () => {
    expect(comboFingerprint(CASE_0016_NATIVE, 46.89706574654418)).toBe(
      CASE_0016_NATIVE_FINGERPRINT,
    );
  });

  it("preserves Python float formatting for integer-valued grid levels", () => {
    expect(
      comboFingerprint(
        {
          injection_rate_m3_day: 8000,
          soak_duration_days: 25,
          production_duration_days: 170,
          production_bhp_psi: 650,
          cycles: 3,
        },
        45,
      ),
    ).toBe("6FDE14E31D4CF57243E0C2CF439221DC104B9F8B28B468150B9F5645610B5702");
  });
});

describe("coveredCombos", () => {
  it("expands the promoted Feature 005 design to 162 combinations", () => {
    expect(scheduleCombos(STANDARD_GRID)).toHaveLength(162);
  });

  it("does not misreport an off-grid native launch pad as grid coverage", () => {
    const result = coveredCombos(STANDARD_GRID, 45, [
      CASE_0016_NATIVE_FINGERPRINT.toLowerCase(),
    ]);

    expect(result.total).toBe(162);
    expect(result.covered).toBe(0);
    expect(result.enabled).toEqual([]);
    expect(result.disabled).toHaveLength(162);
    expect(result.offGridFingerprints).toEqual([CASE_0016_NATIVE_FINGERPRINT]);
  });

  it("returns only exact grid matches as enabled", () => {
    const combos = scheduleCombos(STANDARD_GRID);
    const covered = [
      comboFingerprint(combos[0], 45),
      comboFingerprint(combos.at(-1)!, 45),
    ];

    const result = coveredCombos(STANDARD_GRID, 45, covered);
    expect(result.covered).toBe(2);
    expect(result.enabled).toEqual([combos[0], combos.at(-1)]);
    expect(result.disabled).toHaveLength(160);
    expect(result.offGridFingerprints).toEqual([]);
  });

  it("covers every injection-duration level without double-counting off-grid pads", () => {
    const grid = {
      ...STANDARD_GRID,
      injection_duration_days: [45, 50],
    };
    const combo = scheduleCombos(grid)[0];
    const covered = [
      comboFingerprint(combo, 45),
      comboFingerprint(combo, 50),
    ];

    const result = coveredGridSchedules(grid, covered);
    expect(result.total).toBe(324);
    expect(result.covered).toBe(2);
    expect(result.enabled.map((schedule) => schedule.injection_duration_days)).toEqual([
      45,
      50,
    ]);
    expect(result.offGridFingerprints).toEqual([]);
  });
});

describe("nativeScheduleAvailability", () => {
  it("reports a runnable native schedule separately when it is off-grid", () => {
    expect(
      nativeScheduleAvailability(
        STANDARD_GRID,
        45,
        CASE_0016_NATIVE_FINGERPRINT,
        [CASE_0016_NATIVE_FINGERPRINT],
      ),
    ).toEqual({
      fingerprint: CASE_0016_NATIVE_FINGERPRINT,
      available: true,
      onGrid: false,
    });
  });

  it("does not call a native schedule on-grid when its injection duration is absent", () => {
    const combo = scheduleCombos(STANDARD_GRID)[0];
    const fingerprint = comboFingerprint(combo, 50);
    expect(
      nativeScheduleAvailability(STANDARD_GRID, 50, fingerprint, [fingerprint]),
    ).toMatchObject({ available: true, onGrid: false });
  });
});
