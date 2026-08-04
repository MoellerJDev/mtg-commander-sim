import {
  type RightRailPanel,
  type TablePreferences,
} from "./tablePreferences";


export function TableSettings({
  value,
  onChange,
  onReset,
}: {
  value: TablePreferences;
  onChange: <K extends keyof TablePreferences>(key: K, next: TablePreferences[K]) => void;
  onReset: () => void;
}) {
  const firstPanel = value.rightRailOrder[0];
  function setFirstPanel(panel: RightRailPanel) {
    onChange("rightRailOrder", [panel, ...value.rightRailOrder.filter((item) => item !== panel)]);
  }
  return (
    <details className="table-settings" data-testid="table-settings">
      <summary>Table settings</summary>
      <div className="table-settings-grid">
        <label>Hand height <input aria-label="Hand panel height" type="range" min={190} max={650} step={10} value={value.handPanelHeight} onChange={(event) => onChange("handPanelHeight", Number(event.target.value))} /></label>
        <label>Card scale <input aria-label="Card scale" type="range" min={0.75} max={1.35} step={0.05} value={value.cardScale} onChange={(event) => onChange("cardScale", Number(event.target.value))} /></label>
        <label>Right rail width <input aria-label="Right rail width" type="range" min={260} max={520} step={10} value={value.rightRailWidth} onChange={(event) => onChange("rightRailWidth", Number(event.target.value))} /></label>
        <label>Right rail first <select value={firstPanel} onChange={(event) => setFirstPanel(event.target.value as RightRailPanel)}><option value="stack">Stack</option><option value="activity">Activity</option><option value="card">Card viewer</option></select></label>
        <label>Board density <select value={value.boardDensity} onChange={(event) => onChange("boardDensity", event.target.value as TablePreferences["boardDensity"])}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>
        <label className="check-setting"><input type="checkbox" checked={value.handAutoCollapse} onChange={(event) => onChange("handAutoCollapse", event.target.checked)} /> Auto-collapse empty hand</label>
        <label className="check-setting"><input type="checkbox" checked={value.inspectorCollapsed} onChange={(event) => onChange("inspectorCollapsed", event.target.checked)} /> Collapse card viewer</label>
        <label className="check-setting"><input type="checkbox" checked={value.compactPhaseRail} onChange={(event) => onChange("compactPhaseRail", event.target.checked)} /> Compact phase rail</label>
        <label className="check-setting"><input type="checkbox" checked={value.activityVisible} onChange={(event) => onChange("activityVisible", event.target.checked)} /> Show recent activity</label>
        <button type="button" className="secondary-button" data-testid="reset-table-settings" onClick={onReset}>Reset table layout</button>
      </div>
    </details>
  );
}
