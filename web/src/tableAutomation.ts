type AutoPassAction = {
  action: string;
  mana_ability?: boolean;
};

export function findSafeAutoPass<T extends AutoPassAction>(
  actions: readonly T[],
): T | null {
  const pass = actions.find((action) => action.action === "pass") ?? null;
  if (!pass) return null;
  const hasMeaningfulAction = actions.some(
    (action) => action.mana_ability !== true
      && !["pass", "concede"].includes(action.action),
  );
  return hasMeaningfulAction ? null : pass;
}
