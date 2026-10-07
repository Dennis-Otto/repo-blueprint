import assert from "node:assert/strict";
import { test } from "node:test";

import fc from "fast-check";

import { greet } from "../src/index.ts";

test("greet names the person", () => {
  assert.equal(greet(" Ada "), "Hello, Ada!");
});

test("greet refuses an empty name", () => {
  assert.throws(() => greet("  "), RangeError);
});

test("greet keeps every name", () => {
  fc.assert(
    fc.property(
      fc.string().filter((name) => name.trim() !== ""),
      (name) => greet(name).includes(name.trim()),
    ),
  );
});
