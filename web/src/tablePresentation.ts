import type { LegalAction } from "./generated/protocol";

export type ActionWindow = {
  activeSeat: string;
  ownSeat: string;
  phase: string;
  stackDepth: number;
};

export function visibleActionLabel(
  action: LegalAction,
  window: ActionWindow,
): string {
  if (
    action.action === "pass"
    && window.activeSeat === window.ownSeat
    && window.stackDepth === 0
  ) {
    if (window.phase === "precombat_main") return "Continue to combat";
    if (window.phase === "postcombat_main") return "End turn";
  }
  return action.label ?? action.kind ?? action.action;
}
