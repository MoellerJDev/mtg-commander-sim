export const TABLE_PREFERENCES_KEY = "commander-table-preferences:v1";

export type TablePreferences = {
  autoMana: boolean;
  autoPass: boolean;
};

export const DEFAULT_TABLE_PREFERENCES: Readonly<TablePreferences> = {
  autoMana: true,
  autoPass: true,
};

export function parseTablePreferences(raw: string | null): TablePreferences {
  if (!raw) return { ...DEFAULT_TABLE_PREFERENCES };
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    return {
      autoMana: typeof value.autoMana === "boolean"
        ? value.autoMana
        : DEFAULT_TABLE_PREFERENCES.autoMana,
      autoPass: typeof value.autoPass === "boolean"
        ? value.autoPass
        : DEFAULT_TABLE_PREFERENCES.autoPass,
    };
  } catch {
    return { ...DEFAULT_TABLE_PREFERENCES };
  }
}

export function loadTablePreferences(): TablePreferences {
  if (typeof window === "undefined") return { ...DEFAULT_TABLE_PREFERENCES };
  return parseTablePreferences(window.localStorage.getItem(TABLE_PREFERENCES_KEY));
}

export function saveTablePreferences(value: TablePreferences): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TABLE_PREFERENCES_KEY, JSON.stringify(value));
}
