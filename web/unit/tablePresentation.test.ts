import assert from "node:assert/strict";
import test from "node:test";

import { visibleActionLabel } from "../src/tablePresentation.ts";

const pass = { id: "pass", action: "pass", label: "Pass priority" };

test("active empty main phases label their intentional turn advance", () => {
  assert.equal(visibleActionLabel(pass, {
    activeSeat: "A", ownSeat: "A", phase: "precombat_main", stackDepth: 0,
  }), "Continue to combat");
  assert.equal(visibleActionLabel(pass, {
    activeSeat: "A", ownSeat: "A", phase: "postcombat_main", stackDepth: 0,
  }), "End turn");
});

test("response windows retain the ordinary priority label", () => {
  assert.equal(visibleActionLabel(pass, {
    activeSeat: "A", ownSeat: "B", phase: "precombat_main", stackDepth: 0,
  }), "Pass priority");
  assert.equal(visibleActionLabel(pass, {
    activeSeat: "A", ownSeat: "A", phase: "precombat_main", stackDepth: 1,
  }), "Pass priority");
});
