import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_TABLE_PREFERENCES,
  parseTablePreferences,
} from "../src/tablePreferences.ts";

test("table preferences default to automatic mana and automatic empty passes", () => {
  assert.deepEqual(parseTablePreferences(null), DEFAULT_TABLE_PREFERENCES);
  assert.deepEqual(parseTablePreferences("not json"), DEFAULT_TABLE_PREFERENCES);
});

test("table preferences preserve valid toggles and repair invalid fields", () => {
  assert.deepEqual(
    parseTablePreferences('{"autoMana":false,"autoPass":false}'),
    { autoMana: false, autoPass: false },
  );
  assert.deepEqual(
    parseTablePreferences('{"autoMana":"yes","autoPass":false}'),
    { autoMana: true, autoPass: false },
  );
});
