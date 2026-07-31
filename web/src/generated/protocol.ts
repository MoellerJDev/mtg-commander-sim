// Application-facing refinements over the generated JSON Schema bindings.

import type { MTGCommanderSimClientCommandEnvelopeV30 } from "./command-envelope";
import type { MTGCommanderSimProjectedDecisionPacketV30 } from "./decision-packet";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface ChoiceForm {
  v: number;
  fields: Record<string, JsonValue>[];
  submit_label: string;
  variants?: Record<string, JsonValue>;
}

export interface LegalAction {
  id: string;
  action: string;
  kind?: string;
  label?: string;
  form?: ChoiceForm;
  [key: string]: JsonValue | ChoiceForm | undefined;
}

export interface Decision {
  id: string;
  kind: string;
  actor: string | null;
  cap: string;
  allow: string[];
  legal_actions: LegalAction[];
  sim: 0 | 1;
  ctx: Record<string, JsonValue>;
}

export interface PatchOperation {
  op: "add" | "remove" | "replace";
  path: string;
  value?: JsonValue;
}

export interface DecisionPacket
  extends MTGCommanderSimProjectedDecisionPacketV30 {
  state?: Record<string, JsonValue>;
  patch?: PatchOperation[];
  decision: Decision | null;
  defs?: Record<string, JsonValue>[];
  events?: Record<string, JsonValue>[];
}

export interface CommandEnvelope
  extends MTGCommanderSimClientCommandEnvelopeV30 {
  choices: Record<string, JsonValue>;
}

export interface CommandReceipt {
  ok: boolean;
  code: string;
  summary: string;
  game_id: string;
  command_id: string;
  decision_id: string;
  state_revision: number;
  state_changed: boolean;
  event_ids: number[];
  replayed: boolean;
}
