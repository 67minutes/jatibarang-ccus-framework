import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { PlacedSource } from "../state/field.store";

export type SourceDialogValue = Omit<PlacedSource, "id">;

interface SourceDialogProps {
  initial?: PlacedSource;
  lat: number;
  lon: number;
  onSave: (source: SourceDialogValue) => void;
  onClose: () => void;
}

const DEFAULT_PRESSURE_BAR = 120;
const DEFAULT_TEMPERATURE_C = 27;
const DEFAULT_PURITY = 0.95;
const DEFAULT_PEAK_FLOW_KG_S = 600;

/** Add/edit form for a screening-grade CO2 source. */
export function SourceDialog({
  initial,
  lat,
  lon,
  onSave,
  onClose,
}: SourceDialogProps) {
  const titleId = useId();
  const nameRef = useRef<HTMLInputElement>(null);
  const [latitude, setLatitude] = useState(String(initial?.lat ?? lat));
  const [longitude, setLongitude] = useState(String(initial?.lon ?? lon));
  const [name, setName] = useState(initial?.name ?? "");
  const [capacity, setCapacity] = useState(
    initial ? String(initial.annual_capacity_t) : "",
  );
  const [pressure, setPressure] = useState(
    String(initial?.outlet_pressure_bar ?? DEFAULT_PRESSURE_BAR),
  );
  const [temperature, setTemperature] = useState(
    String(initial?.outlet_temperature_c ?? DEFAULT_TEMPERATURE_C),
  );
  const [purity, setPurity] = useState(
    String(initial?.co2_purity ?? DEFAULT_PURITY),
  );
  const [peakFlow, setPeakFlow] = useState(
    String(initial?.max_mass_flow_kg_s ?? DEFAULT_PEAK_FLOW_KG_S),
  );

  useEffect(() => {
    nameRef.current?.focus({ preventScroll: true });
    const handleKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    };
    window.addEventListener("keydown", handleKey, true);
    return () => window.removeEventListener("keydown", handleKey, true);
  }, [onClose]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const sourceLatitude = Number(latitude);
    const sourceLongitude = Number(longitude);
    const annualCapacity = Number(capacity);
    const outletPressure = Number(pressure);
    const outletTemperature = Number(temperature);
    const co2Purity = Number(purity);
    const maxMassFlow = Number(peakFlow);
    if (
      !name.trim() ||
      !latitude.trim() ||
      !longitude.trim() ||
      !capacity.trim() ||
      !pressure.trim() ||
      !temperature.trim() ||
      !purity.trim() ||
      !peakFlow.trim() ||
      !Number.isFinite(sourceLatitude) ||
      sourceLatitude < -90 ||
      sourceLatitude > 90 ||
      !Number.isFinite(sourceLongitude) ||
      sourceLongitude < -180 ||
      sourceLongitude > 180 ||
      !Number.isFinite(annualCapacity) ||
      annualCapacity <= 0 ||
      !Number.isFinite(outletPressure) ||
      outletPressure < 80 ||
      !Number.isFinite(outletTemperature) ||
      !Number.isFinite(co2Purity) ||
      co2Purity < 0.95 ||
      co2Purity > 1 ||
      !Number.isFinite(maxMassFlow) ||
      maxMassFlow <= 0
    ) {
      return;
    }
    onSave({
      name: name.trim(),
      lat: sourceLatitude,
      lon: sourceLongitude,
      annual_capacity_t: annualCapacity,
      outlet_pressure_bar: outletPressure,
      outlet_temperature_c: outletTemperature,
      co2_purity: co2Purity,
      max_mass_flow_kg_s: maxMassFlow,
    });
  };

  return (
    <div
      className="source-dialog-scrim"
      onPointerDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <section
        className="source-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header>
          <div>
            <span>CO₂ SUPPLY</span>
            <h2 id={titleId}>{initial ? "Edit source" : "Add source"}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close source dialog">
            ×
          </button>
        </header>
        <form onSubmit={submit}>
          <div className="source-dialog-grid">
            <label className="source-dialog-field">
              <span>Latitude</span>
              <input
                type="number"
                min="-90"
                max="90"
                step="any"
                value={latitude}
                onChange={(event) => setLatitude(event.target.value)}
                required
              />
            </label>
            <label className="source-dialog-field">
              <span>Longitude</span>
              <input
                type="number"
                min="-180"
                max="180"
                step="any"
                value={longitude}
                onChange={(event) => setLongitude(event.target.value)}
                required
              />
            </label>
            <label className="source-dialog-field source-dialog-field-wide">
              <span>Source name</span>
              <input
                ref={nameRef}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Subang capture plant"
                required
              />
            </label>
            <label className="source-dialog-field source-dialog-field-wide">
              <span>Annual capacity (t/y)</span>
              <input
                type="number"
                min="1"
                step="1"
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
                required
              />
            </label>
          </div>
          <details className="source-dialog-advanced">
            <summary>Advanced screening inputs</summary>
            <div className="source-dialog-grid">
              <label className="source-dialog-field">
                <span>Outlet pressure (bar)</span>
                <input
                  type="number"
                  min="80"
                  step="0.1"
                  value={pressure}
                  onChange={(event) => setPressure(event.target.value)}
                  required
                />
              </label>
              <label className="source-dialog-field">
                <span>Temperature (°C)</span>
                <input
                  type="number"
                  step="0.1"
                  value={temperature}
                  onChange={(event) => setTemperature(event.target.value)}
                  required
                />
              </label>
              <label className="source-dialog-field">
                <span>CO₂ purity (fraction)</span>
                <input
                  type="number"
                  min="0.95"
                  max="1"
                  step="0.01"
                  value={purity}
                  onChange={(event) => setPurity(event.target.value)}
                  required
                />
              </label>
              <label className="source-dialog-field">
                <span>Peak flow (kg/s)</span>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={peakFlow}
                  onChange={(event) => setPeakFlow(event.target.value)}
                  required
                />
              </label>
            </div>
          </details>
          <footer>
            <button type="button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="source-dialog-primary">
              {initial ? "Save changes" : "Add source"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
