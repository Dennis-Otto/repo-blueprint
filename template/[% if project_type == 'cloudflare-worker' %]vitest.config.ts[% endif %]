// The tests of the Worker, which run in workerd, the runtime of Cloudflare Workers,
// with the bindings of the configuration of Wrangler, through the Vitest integration
// of Cloudflare. `npm test` runs them with every line, branch and function of src/
// covered, as the step "Tests" of scripts/check.sh asks, and writes lcov.info for the
// coverage in the report of the PR coach; in the CI, Vitest makes each test that
// fails an annotation at its line.
//
// The blueprint keeps this file current: https://github.com/Dennis-Otto/repo-blueprint
import { existsSync } from "node:fs";

import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

// The configuration that the project has, in the order in which Wrangler looks for it.
const configPath = ["wrangler.jsonc", "wrangler.json", "wrangler.toml"].find(
  (name) => existsSync(name),
);

export default defineConfig({
  plugins: [cloudflareTest({ wrangler: { configPath } })],
  test: {
    include: ["test/**/*.test.ts"],
    coverage: {
      provider: "istanbul",
      include: ["src/**"],
      reporter: ["text", ["lcovonly", { file: "../lcov.info" }]],
      thresholds: {
        lines: 100,
        branches: 100,
        functions: 100,
        statements: 100,
      },
    },
  },
});
