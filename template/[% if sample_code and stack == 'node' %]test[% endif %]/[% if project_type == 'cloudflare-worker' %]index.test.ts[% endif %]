// The tests run in workerd, the runtime of Cloudflare Workers, as vitest.config.ts
// sets them up: exports.default is the Worker of src/index.ts with the bindings of
// wrangler.jsonc, and each request reaches it as one from the internet would. A
// secret lives only in Cloudflare: a test that needs one imports the Worker of
// src/index.ts and calls worker.fetch(request, { ...env, TOKEN: "test" },
// createExecutionContext()), with env and createExecutionContext from cloudflare:test.
import { exports } from "cloudflare:workers";
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { greet } from "../src/greet.ts";

describe("greet", () => {
  it("names the person", () => {
    expect(greet(" Ada ")).toBe("Hello, Ada!");
  });

  it("refuses an empty name", () => {
    expect(() => greet("  ")).toThrow(RangeError);
  });

  it("keeps every name", () => {
    fc.assert(
      fc.property(
        fc.string().filter((name) => name.trim() !== ""),
        (name) => greet(name).includes(name.trim()),
      ),
    );
  });
});

describe("the Worker", () => {
  it("greets the name of the query", async () => {
    const response = await exports.default.fetch(
      "https://example.com/?name=Ada",
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ message: "Hello, Ada!" });
  });

  it("greets the world without a name", async () => {
    const response = await exports.default.fetch("https://example.com/");
    expect(await response.json()).toEqual({ message: "Hello, world!" });
  });

  it("answers a HEAD without a body", async () => {
    const response = await exports.default.fetch("https://example.com/", {
      method: "HEAD",
    });
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("");
  });

  it("refuses an empty name", async () => {
    const response = await exports.default.fetch(
      "https://example.com/?name=%20",
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "name is empty" });
  });

  it("knows no other path", async () => {
    const response = await exports.default.fetch("https://example.com/admin");
    expect(response.status).toBe(404);
  });

  it("refuses every other method", async () => {
    const response = await exports.default.fetch("https://example.com/", {
      method: "POST",
    });
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("GET, HEAD");
  });
});
