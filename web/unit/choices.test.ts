import assert from "node:assert/strict";
import test from "node:test";

import {
  activeFields,
  choicesWithDefaults,
  executableChoices,
  initialChoices,
  validateChoices,
} from "../src/choices.ts";
import type { ChoiceForm } from "../src/generated/protocol.ts";

function form(fields: ChoiceForm["fields"]): ChoiceForm {
  return { v: 1, fields, submit_label: "Submit" };
}

test("private mulligan-bottom refs require exactly the server count", () => {
  const bottom = form([
    {
      name: "cards",
      label: "Cards",
      control: "refs",
      required: true,
      minimum: 1,
      maximum: 1,
      options: [
        { value: "A01", label: "Forest" },
        { value: "A02", label: "Island" },
      ],
    },
  ]);
  const choices = initialChoices(bottom);
  assert.deepEqual(choices, { cards: [] });
  assert.match(validateChoices(bottom, choices)[0], /at least 1/);
  choices.cards = ["A02"];
  assert.deepEqual(validateChoices(bottom, choices), []);
  assert.deepEqual(executableChoices(bottom, choices), { cards: ["A02"] });
});

test("cost variants activate only their server-issued fields", () => {
  const cast: ChoiceForm = {
    v: 1,
    fields: [],
    submit_label: "Cast",
    variants: {
      field: "cost_option",
      default: "normal",
      options: [
        {
          value: "normal",
          label: "Normal",
          fields: [
            { name: "x", label: "X", control: "integer", minimum: 0, maximum: 4 },
          ],
        },
        {
          value: "pitch",
          label: "Pitch",
          fields: [
            {
              name: "exile_card",
              label: "Exile card",
              control: "ref",
              required: true,
              options: [{ value: "A03", label: "Blue card" }],
            },
          ],
        },
      ],
    },
  };
  const choices = initialChoices(cast);
  assert.deepEqual(choices, { cost_option: "normal", x: 0 });
  const pitch = choicesWithDefaults(cast, { ...choices, cost_option: "pitch" });
  assert.deepEqual(
    activeFields(cast, pitch).map((field) => field.name),
    ["exile_card"],
  );
  assert.equal(pitch.exile_card, "A03");
  assert.deepEqual(executableChoices(cast, pitch), {
    cost_option: "pitch",
    exile_card: "A03",
  });
});

test("dependent top ordering follows only object-map choices sent to top", () => {
  const ordered = form([
    {
      name: "decisions",
      label: "Decisions",
      control: "object_map",
      minimum: 2,
      keys: ["A01", "A02"],
      options: [
        { value: "pay_life", label: "Pay life" },
        { value: "top", label: "Put on top" },
      ],
    },
    {
      name: "top_order",
      label: "Top order",
      control: "refs",
      ordered: true,
      options_from_map: "decisions",
      required_value: "top",
      minimum: 0,
      maximum: 2,
      options: [
        { value: "A01", label: "First" },
        { value: "A02", label: "Second" },
      ],
    },
  ]);
  const choices = initialChoices(ordered);
  choices.decisions = { A01: "pay_life", A02: "top" };
  const topOrder = activeFields(ordered, choices)[1];
  assert.deepEqual(topOrder.legal_refs, ["A02"]);
  assert.deepEqual(topOrder.options, [
    { value: "A02", label: "Second", available: true },
  ]);
  assert.match(validateChoices(ordered, choices)[0], /Top order requires/);
  choices.top_order = ["A02"];
  assert.deepEqual(validateChoices(ordered, choices), []);
});

test("modal target forms validate modes and group cardinality", () => {
  const target = form([
    {
      name: "targets",
      label: "Targets and modes",
      control: "targets",
      required: true,
      schema: {
        legal_modes: ["destroy", "draw"],
        min_modes: 1,
        max_modes: 1,
        mode_schemas: {
          destroy: {
            groups: [
              { id: "permanent", label: "Permanent", min: 1, max: 1, legal_refs: ["B01"] },
            ],
          },
          draw: { groups: [] },
        },
      },
    },
  ]);
  const choices = initialChoices(target);
  assert.match(validateChoices(target, choices)[0], /Choose at least 1 mode/);
  choices.modes = ["destroy"];
  assert.match(validateChoices(target, choices)[0], /Permanent requires/);
  choices.targets = { permanent: ["B01"] };
  assert.deepEqual(validateChoices(target, choices), []);
  assert.deepEqual(executableChoices(target, choices), {
    targets: { permanent: ["B01"] },
    modes: ["destroy"],
  });
});

test("fully ordered server choices initialize in projected order", () => {
  const triggers = form([
    {
      name: "triggers",
      label: "Triggers",
      control: "refs",
      ordered: true,
      minimum: 2,
      maximum: 2,
      options: [
        { value: "S2", label: "Second" },
        { value: "S1", label: "First" },
      ],
    },
  ]);
  const choices = initialChoices(triggers);
  assert.deepEqual(choices.triggers, ["S2", "S1"]);
  assert.deepEqual(validateChoices(triggers, choices), []);
});

test("copy targets preserve defaults and validate each copy", () => {
  const copies = form([
    {
      name: "copy_targets",
      label: "Copy targets",
      control: "copy_targets",
      copy_count: 2,
      copies: [
        {
          default_targets: ["B01"],
          target_schema: {
            groups: [{ id: "target", min: 1, max: 1, legal_refs: ["B01", "C01"] }],
          },
        },
        {
          default_targets: ["B01"],
          target_schema: {
            groups: [{ id: "target", min: 1, max: 1, legal_refs: ["B01", "C01"] }],
          },
        },
      ],
    },
  ]);
  const choices = initialChoices(copies);
  assert.deepEqual(choices.copy_targets, [["B01"], ["B01"]]);
  assert.deepEqual(validateChoices(copies, choices), []);
  choices.copy_targets = [{ target: ["C01"] }, { target: [] }];
  assert.match(validateChoices(copies, choices)[0], /Copy 2/);
});
