import assert from "node:assert/strict";
import test from "node:test";

import { findSafeAutoPass } from "../src/tableAutomation.ts";

test("automatic passing accepts only pass, concede, and bare mana actions", () => {
  const pass = { action: "pass", id: "pass:1" };
  assert.equal(findSafeAutoPass([pass]), pass);
  assert.equal(
    findSafeAutoPass([pass, { action: "activate", mana_ability: true }]),
    pass,
  );
  assert.equal(findSafeAutoPass([pass, { action: "concede" }]), pass);
});

test("automatic passing stops for every meaningful action category", () => {
  for (const action of ["play_land", "cast", "activate", "undo_mana", "choose", "attack", "block"]) {
    assert.equal(
      findSafeAutoPass([{ action: "pass" }, { action }]),
      null,
      action,
    );
  }
  assert.equal(findSafeAutoPass([{ action: "concede" }]), null);
});
