export const TABLE_PREFERENCES_KEY = "commander-table-preferences:v2";
export const LEGACY_TABLE_PREFERENCES_KEY = "commander-table-preferences:v1";

export type RightRailPanel = "stack" | "activity" | "card";
export type BoardDensity = "comfortable" | "compact";

export type TablePreferences = {
  autoMana: boolean;
  autoPass: boolean;
  handPanelHeight: number;
  handAutoCollapse: boolean;
  cardScale: number;
  rightRailWidth: number;
  rightRailOrder: RightRailPanel[];
  inspectorCollapsed: boolean;
  boardDensity: BoardDensity;
  compactPhaseRail: boolean;
  activityVisible: boolean;
};

export const DEFAULT_TABLE_PREFERENCES: Readonly<TablePreferences> = {
  autoMana: true,
  autoPass: true,
  handPanelHeight: 310,
  handAutoCollapse: true,
  cardScale: 1,
  rightRailWidth: 320,
  rightRailOrder: ["stack", "activity", "card"],
  inspectorCollapsed: false,
  boardDensity: "comfortable",
  compactPhaseRail: false,
  activityVisible: true,
};

function boundedNumber(value: unknown, fallback: number, minimum: number, maximum: number): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(maximum, Math.max(minimum, value))
    : fallback;
}

function railOrder(value: unknown): RightRailPanel[] {
  if (!Array.isArray(value)) return [...DEFAULT_TABLE_PREFERENCES.rightRailOrder];
  const allowed = new Set<RightRailPanel>(["stack", "activity", "card"]);
  const result = value.filter((item): item is RightRailPanel => typeof item === "string" && allowed.has(item as RightRailPanel));
  return result.length === allowed.size && new Set(result).size === allowed.size
    ? result
    : [...DEFAULT_TABLE_PREFERENCES.rightRailOrder];
}

export function parseTablePreferences(raw: string | null): TablePreferences {
  if (!raw) return { ...DEFAULT_TABLE_PREFERENCES, rightRailOrder: [...DEFAULT_TABLE_PREFERENCES.rightRailOrder] };
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    return {
      autoMana: typeof value.autoMana === "boolean" ? value.autoMana : DEFAULT_TABLE_PREFERENCES.autoMana,
      autoPass: typeof value.autoPass === "boolean" ? value.autoPass : DEFAULT_TABLE_PREFERENCES.autoPass,
      handPanelHeight: boundedNumber(value.handPanelHeight, DEFAULT_TABLE_PREFERENCES.handPanelHeight, 190, 650),
      handAutoCollapse: typeof value.handAutoCollapse === "boolean" ? value.handAutoCollapse : DEFAULT_TABLE_PREFERENCES.handAutoCollapse,
      cardScale: boundedNumber(value.cardScale, DEFAULT_TABLE_PREFERENCES.cardScale, 0.75, 1.35),
      rightRailWidth: boundedNumber(value.rightRailWidth, DEFAULT_TABLE_PREFERENCES.rightRailWidth, 260, 520),
      rightRailOrder: railOrder(value.rightRailOrder),
      inspectorCollapsed: typeof value.inspectorCollapsed === "boolean" ? value.inspectorCollapsed : DEFAULT_TABLE_PREFERENCES.inspectorCollapsed,
      boardDensity: value.boardDensity === "compact" || value.boardDensity === "comfortable" ? value.boardDensity : DEFAULT_TABLE_PREFERENCES.boardDensity,
      compactPhaseRail: typeof value.compactPhaseRail === "boolean" ? value.compactPhaseRail : DEFAULT_TABLE_PREFERENCES.compactPhaseRail,
      activityVisible: typeof value.activityVisible === "boolean" ? value.activityVisible : DEFAULT_TABLE_PREFERENCES.activityVisible,
    };
  } catch {
    return { ...DEFAULT_TABLE_PREFERENCES, rightRailOrder: [...DEFAULT_TABLE_PREFERENCES.rightRailOrder] };
  }
}

export function loadTablePreferences(): TablePreferences {
  if (typeof window === "undefined") return parseTablePreferences(null);
  const current = window.localStorage.getItem(TABLE_PREFERENCES_KEY);
  if (current) return parseTablePreferences(current);
  return parseTablePreferences(window.localStorage.getItem(LEGACY_TABLE_PREFERENCES_KEY));
}

export function saveTablePreferences(value: TablePreferences): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TABLE_PREFERENCES_KEY, JSON.stringify(value));
  window.localStorage.removeItem(LEGACY_TABLE_PREFERENCES_KEY);
}
