import assert from "node:assert/strict";
import { test } from "node:test";

import { greet } from "../src/index.ts";

test("greet names the person", () => {
  assert.equal(greet(" Ada "), "Hello, Ada!");
});

test("greet refuses an empty name", () => {
  assert.throws(() => greet("  "), RangeError);
});
