import { useWorkspaceStore } from "../state/workspace.store";

export function PreferencesDialog() {
  const palette = useWorkspaceStore((s) => s.terrainPalette);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const cameraMotion = useWorkspaceStore((s) => s.cameraMotion);
  const setPalette = useWorkspaceStore((s) => s.setTerrainPalette);
  const setExaggeration = useWorkspaceStore((s) => s.setExaggeration);
  const setCameraMotion = useWorkspaceStore((s) => s.setCameraMotion);

  return (
    <div className="dialog-form">
      <p className="dialog-intro">
        View preferences apply immediately and remain session-local. Scientific
        inputs are edited only in Compose.
      </p>
      <div className="dialog-grid">
        <label className="dialog-field dialog-field-wide">
          <span>Terrain treatment</span>
          <select value={palette} onChange={(e) => setPalette(e.target.value as typeof palette)}>
            <option value="geologic">Geologic relief</option>
            <option value="monochrome">Monochrome survey</option>
          </select>
          <small>Geologic relief uses a restrained elevation palette; reservoir colors remain data-only.</small>
        </label>
        <label className="dialog-field">
          <span>Vertical exaggeration</span>
          <select value={exaggeration} onChange={(e) => setExaggeration(Number(e.target.value))}>
            {[1, 2, 5, 10].map((value) => (
              <option key={value} value={value}>{value}{"\u00d7"}</option>
            ))}
          </select>
        </label>
        <label className="dialog-check">
          <input
            type="checkbox"
            checked={cameraMotion}
            onChange={(e) => setCameraMotion(e.target.checked)}
          />
          <span>
            Smooth camera framing
            <small>Animate Reset Camera and Frame Selection transitions.</small>
          </span>
        </label>
      </div>
    </div>
  );
}
