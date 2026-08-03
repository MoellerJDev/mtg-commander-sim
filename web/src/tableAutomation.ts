type AutoPassAction = {
  action: string;
  mana_ability?: boolean;
};

export type AutoPassWindow = {
  activePlayer?: string;
  phase?: string;
  principalSeat?: string;
  stackDepth?: number;
};

export function findSafeAutoPass<T extends AutoPassAction>(
  actions: readonly T[],
  window: AutoPassWindow = {},
): T | null {
  const activeEmptyMain = window.principalSeat !== undefined
    && window.principalSeat === window.activePlayer
    && (window.stackDepth ?? 0) === 0
    && ["precombat_main", "postcombat_main"].includes(window.phase ?? "");
  if (activeEmptyMain) return null;
  const pass = actions.find((action) => action.action === "pass") ?? null;
  if (!pass) return null;
  const hasMeaningfulAction = actions.some(
    (action) => action.mana_ability !== true
      && !["pass", "concede"].includes(action.action),
  );
  return hasMeaningfulAction ? null : pass;
}
