import type { OperationalGrid } from "../api/types";

/** The five schedule dimensions varied by the Feature 005 launch-pad design. */
export interface ScheduleCombo {
  injection_rate_m3_day: number;
  soak_duration_days: number;
  production_duration_days: number;
  production_bhp_psi: number;
  cycles: number;
}

export interface ScheduleCoverage {
  total: number;
  covered: number;
  /** Grid combinations for which an imported launch pad is available. */
  enabled: ScheduleCombo[];
  /** Grid combinations that cannot be screened without an offline MRST run. */
  disabled: ScheduleCombo[];
  /** Imported launch pads that do not correspond to the active grid. */
  offGridFingerprints: string[];
}

export interface OperatingScheduleInput extends ScheduleCombo {
  injection_reference_pressure_bar: number;
  injection_reference_temperature_c: number;
  injection_duration_days: number;
}

export interface GridScheduleCoverage {
  total: number;
  covered: number;
  enabled: OperatingScheduleInput[];
  disabled: OperatingScheduleInput[];
  offGridFingerprints: string[];
}

export interface NativeScheduleAvailability {
  fingerprint: string;
  available: boolean;
  onGrid: boolean;
}

const INJECTION_REFERENCE_PRESSURE_BAR = 1.01325;
const INJECTION_REFERENCE_TEMPERATURE_C = 15.0;

const SHA256_ROUND_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotateRight(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}

/**
 * Small synchronous SHA-256 implementation. The coverage calculation runs while
 * editing the grid, so the asynchronous Web Crypto API is deliberately avoided.
 */
function sha256(value: string): string {
  const bytes = new TextEncoder().encode(value);
  const byteLength = bytes.length;
  const paddedLength = Math.ceil((byteLength + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[byteLength] = 0x80;

  const bitLength = BigInt(byteLength) * 8n;
  const lengthView = new DataView(padded.buffer);
  lengthView.setUint32(paddedLength - 8, Number(bitLength >> 32n), false);
  lengthView.setUint32(
    paddedLength - 4,
    Number(bitLength & 0xffff_ffffn),
    false,
  );

  const state = new Uint32Array([
    0x6a09e667,
    0xbb67ae85,
    0x3c6ef372,
    0xa54ff53a,
    0x510e527f,
    0x9b05688c,
    0x1f83d9ab,
    0x5be0cd19,
  ]);
  const words = new Uint32Array(64);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = lengthView.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 64; index += 1) {
      const previous15 = words[index - 15];
      const previous2 = words[index - 2];
      const sigma0 =
        rotateRight(previous15, 7) ^
        rotateRight(previous15, 18) ^
        (previous15 >>> 3);
      const sigma1 =
        rotateRight(previous2, 17) ^
        rotateRight(previous2, 19) ^
        (previous2 >>> 10);
      words[index] =
        (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }

    let a = state[0];
    let b = state[1];
    let c = state[2];
    let d = state[3];
    let e = state[4];
    let f = state[5];
    let g = state[6];
    let h = state[7];

    for (let index = 0; index < 64; index += 1) {
      const bigSigma1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choose = (e & f) ^ (~e & g);
      const first =
        (h + bigSigma1 + choose + SHA256_ROUND_CONSTANTS[index] + words[index]) >>> 0;
      const bigSigma0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const second = (bigSigma0 + majority) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + first) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (first + second) >>> 0;
    }

    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
    state[4] = (state[4] + e) >>> 0;
    state[5] = (state[5] + f) >>> 0;
    state[6] = (state[6] + g) >>> 0;
    state[7] = (state[7] + h) >>> 0;
  }

  return Array.from(state, (word) => word.toString(16).padStart(8, "0"))
    .join("")
    .toUpperCase();
}

/** Render a JavaScript number the way Python's json.dumps renders a float. */
function pythonFloat(value: number): string {
  if (!Number.isFinite(value)) {
    throw new Error("Schedule values must be finite numbers.");
  }
  if (Number.isInteger(value)) return `${value}.0`;

  const rendered = String(value);
  const exponentAt = rendered.indexOf("e");
  if (exponentAt < 0) return rendered;

  const mantissa = rendered.slice(0, exponentAt);
  const rawExponent = rendered.slice(exponentAt + 1);
  const sign = rawExponent.startsWith("-") ? "-" : "+";
  const digits = rawExponent.replace(/^[+-]/, "").padStart(2, "0");
  return `${mantissa}e${sign}${digits}`;
}

function schedulePayload(combo: ScheduleCombo, injectionDurationDays: number): string {
  if (!Number.isInteger(combo.cycles)) {
    throw new Error("Schedule cycles must be an integer.");
  }
  // Key order and float formatting mirror json.dumps(..., sort_keys=True,
  // separators=(",", ":")) over OperatingSchedule.model_dump(mode="json").
  return (
    `{"cycles":${combo.cycles},` +
    `"injection_duration_days":${pythonFloat(injectionDurationDays)},` +
    `"injection_rate_m3_day":${pythonFloat(combo.injection_rate_m3_day)},` +
    `"injection_reference_pressure_bar":${pythonFloat(INJECTION_REFERENCE_PRESSURE_BAR)},` +
    `"injection_reference_temperature_c":${pythonFloat(INJECTION_REFERENCE_TEMPERATURE_C)},` +
    `"production_bhp_psi":${pythonFloat(combo.production_bhp_psi)},` +
    `"production_duration_days":${pythonFloat(combo.production_duration_days)},` +
    `"soak_duration_days":${pythonFloat(combo.soak_duration_days)}}`
  );
}

/** Mirrors surrogate/preprocessing.py::schedule_fingerprint exactly. */
export function comboFingerprint(
  combo: ScheduleCombo,
  injectionDurationDays: number,
): string {
  return sha256(schedulePayload(combo, injectionDurationDays));
}

/** Expand the five-dimensional Feature 005 schedule grid deterministically. */
export function scheduleCombos(grid: OperationalGrid): ScheduleCombo[] {
  const combinations: ScheduleCombo[] = [];
  for (const injection_rate_m3_day of [...grid.injection_rate_m3_day].sort((a, b) => a - b)) {
    for (const soak_duration_days of [...grid.soak_duration_days].sort((a, b) => a - b)) {
      for (const production_duration_days of [...grid.production_duration_days].sort((a, b) => a - b)) {
        for (const production_bhp_psi of [...grid.production_bhp_psi].sort((a, b) => a - b)) {
          for (const cycles of [...grid.cycles].sort((a, b) => a - b)) {
            combinations.push({
              injection_rate_m3_day,
              soak_duration_days,
              production_duration_days,
              production_bhp_psi,
              cycles,
            });
          }
        }
      }
    }
  }
  return combinations;
}

function operatingSchedule(
  combo: ScheduleCombo,
  injectionDurationDays: number,
): OperatingScheduleInput {
  return {
    ...combo,
    injection_reference_pressure_bar: INJECTION_REFERENCE_PRESSURE_BAR,
    injection_reference_temperature_c: INJECTION_REFERENCE_TEMPERATURE_C,
    injection_duration_days: injectionDurationDays,
  };
}

/** Coverage across every injection-duration level in the active grid. */
export function coveredGridSchedules(
  grid: OperationalGrid,
  covered: string[],
): GridScheduleCoverage {
  const available = new Set(covered.map((fingerprint) => fingerprint.toUpperCase()));
  const enabled: OperatingScheduleInput[] = [];
  const disabled: OperatingScheduleInput[] = [];
  const gridFingerprints = new Set<string>();
  const durations = [...grid.injection_duration_days].sort((a, b) => a - b);

  for (const injectionDurationDays of durations) {
    for (const combo of scheduleCombos(grid)) {
      const fingerprint = comboFingerprint(combo, injectionDurationDays);
      gridFingerprints.add(fingerprint);
      (available.has(fingerprint) ? enabled : disabled).push(
        operatingSchedule(combo, injectionDurationDays),
      );
    }
  }

  return {
    total: enabled.length + disabled.length,
    covered: enabled.length,
    enabled,
    disabled,
    offGridFingerprints: [...available]
      .filter((fingerprint) => !gridFingerprints.has(fingerprint))
      .sort(),
  };
}

export function coveredCombos(
  grid: OperationalGrid,
  injectionDurationDays: number,
  covered: string[],
): ScheduleCoverage {
  const available = new Set(covered.map((fingerprint) => fingerprint.toUpperCase()));
  const enabled: ScheduleCombo[] = [];
  const disabled: ScheduleCombo[] = [];
  const gridFingerprints = new Set<string>();

  for (const combo of scheduleCombos(grid)) {
    const fingerprint = comboFingerprint(combo, injectionDurationDays);
    gridFingerprints.add(fingerprint);
    (available.has(fingerprint) ? enabled : disabled).push(combo);
  }

  return {
    total: enabled.length + disabled.length,
    covered: enabled.length,
    enabled,
    disabled,
    offGridFingerprints: [...available]
      .filter((fingerprint) => !gridFingerprints.has(fingerprint))
      .sort(),
  };
}

/**
 * Report native-seed availability independently from grid coverage. An
 * imported native schedule can be runnable yet off the active 162-point grid.
 */
export function nativeScheduleAvailability(
  grid: OperationalGrid,
  injectionDurationDays: number,
  nativeFingerprint: string,
  covered: string[],
): NativeScheduleAvailability {
  const fingerprint = nativeFingerprint.toUpperCase();
  const available = new Set(covered.map((item) => item.toUpperCase())).has(fingerprint);
  const durationOnGrid = grid.injection_duration_days.includes(injectionDurationDays);
  const onGrid =
    durationOnGrid &&
    scheduleCombos(grid).some(
      (combo) => comboFingerprint(combo, injectionDurationDays) === fingerprint,
    );
  return { fingerprint, available, onGrid };
}
