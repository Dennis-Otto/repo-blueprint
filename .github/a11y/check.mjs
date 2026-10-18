// The accessibility check of the website, a step of the check docs: it opens every
// page that MkDocs built into a folder, such as site/, in Chrome, in the light and in
// the dark scheme, and runs axe-core on each with the rules of WCAG 2.2 at the levels
// A and AA. A violation whose impact is serious or critical fails it, with the page,
// the rule, the elements and a link that explains the fix; the lesser ones it counts.
// The pages come from the folder alone: a request to the address of the website is
// answered from there, and one to another server is refused and named, so the check
// reads nothing from the network. After a build, on your machine:
//
//   npm ci --prefix .github/a11y --ignore-scripts
//   node .github/a11y/check.mjs site
//
// It drives the Google Chrome that GitHub's runners have; CHROME names another
// Chrome or Chromium, by the path of its program. REPORT_ONLY=true annotates the
// violations as warnings rather than errors, for a check that doesn't fail on them
// yet. Renovate keeps the tools current.
// https://github.com/Dennis-Otto/repo-blueprint

import { existsSync } from "node:fs";
import { appendFile, readdir, readFile } from "node:fs/promises";
import { availableParallelism } from "node:os";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { AxeBuilder } from "@axe-core/playwright";
import { chromium } from "playwright-core";

// The rules of WCAG 2.0, 2.1 and 2.2 at the levels A and AA.
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
// The impacts that fail the check.
const FAILING = new Set(["critical", "serious"]);
// The schemes of the reader's system, and the one of Material that each should show.
const SCHEMES = { light: "default", dark: "slate" };
// Pages that are checked at the same time: one for each core, from two to eight.
const PARALLEL = Math.min(8, Math.max(2, availableParallelism()));
// The address of a website without one in its pages.
const NOWHERE = "https://website.test/";
const TYPES = {
  ".avif": "image/avif",
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".mp4": "video/mp4",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ttf": "font/ttf",
  ".txt": "text/plain; charset=utf-8",
  ".webm": "video/webm",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".xml": "application/xml",
};

/** The pages of the website: every HTML file of the folder outside its assets. */
async function pagesOf(site) {
  const names = await readdir(site, { recursive: true });
  return names
    .map((name) => name.split(path.sep).join("/"))
    .filter((name) => name.endsWith(".html") && !/^(assets|search)\//.test(name))
    .sort();
}

/** The address of the website, from the canonical link of its home page. */
async function addressOf(site) {
  try {
    const home = await readFile(path.join(site, "index.html"), "utf-8");
    const canonical = home.match(/<link rel="canonical" href="([^"]+)"/);
    if (canonical) {
      return new URL(".", canonical[1]).href;
    }
  } catch {
    // A website without a home page has no address of its own.
  }
  return NOWHERE;
}

/** The Markdown file of a page, for the annotation, when docs/ has one. */
function sourceOf(page, root = ".") {
  const name = page.replace(/\.html$/, "");
  const candidates = [`${name}.md`, `${name}/index.md`, `${name}/README.md`];
  const language = name.match(/^([a-z]{2})\/(.+)$/);
  if (language) {
    const [, code, rest] = language;
    candidates.push(`${rest}.${code}.md`, `${rest}/index.${code}.md`, `${rest}/README.${code}.md`);
  }
  if (name === "index" || name.endsWith("/index")) {
    candidates.push(`${name.replace(/index$/, "")}README.md`);
  }
  return candidates
    .map((candidate) => `docs/${candidate}`)
    .find((candidate) => existsSync(path.join(root, candidate)));
}

/** A value for a command of GitHub Actions, such as ::error. */
function escaped(text, property = false) {
  let value = String(text).replaceAll("%", "%25").replaceAll("\r", "%0D").replaceAll("\n", "%0A");
  if (property) {
    value = value.replaceAll(":", "%3A").replaceAll(",", "%2C");
  }
  return value;
}

/** Answers every request to the website from the folder, and refuses the others. */
async function serve(context, site, address, foreign) {
  const root = path.resolve(site);
  const prefix = new URL(address).pathname;
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!url.href.startsWith(address)) {
      foreign.add(url.origin);
      await route.abort("blockedbyclient");
      return;
    }
    let file = path.resolve(root, decodeURIComponent(url.pathname.slice(prefix.length)));
    if (url.pathname.endsWith("/")) {
      file = path.join(file, "index.html");
    }
    if (file !== root && !file.startsWith(root + path.sep)) {
      await route.fulfill({ status: 403 });
      return;
    }
    try {
      const body = await readFile(file);
      const type = TYPES[path.extname(file).toLowerCase()] ?? "application/octet-stream";
      await route.fulfill({ status: 200, contentType: type, body });
    } catch {
      await route.fulfill({ status: 404, contentType: TYPES[".txt"], body: "Not found" });
    }
  });
}

/** The violations of one page in one scheme. */
async function check(context, address, page, scheme) {
  const tab = await context.newPage();
  try {
    await tab.goto(new URL(page, address).href, { waitUntil: "load", timeout: 60_000 });
    // Material sets the scheme of the reader with its script; another page has none.
    await tab
      .waitForFunction(
        (wanted) => {
          const body = document.body;
          return !body?.hasAttribute("data-md-color-scheme") ||
            body.getAttribute("data-md-color-scheme") === wanted;
        },
        SCHEMES[scheme],
        { timeout: 5_000 },
      )
      .catch(() => {});
    // The fonts, and the frames after which the script of Material has measured the
    // page, such as a block of code that scrolls and takes the focus.
    await tab.evaluate(async () => {
      await document.fonts.ready;
      for (let frame = 0; frame < 3; frame++) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
    });
    const results = await new AxeBuilder({ page: tab }).withTags(TAGS).analyze();
    return results.violations.map((violation) => ({
      page,
      scheme,
      rule: violation.id,
      impact: violation.impact ?? "minor",
      help: violation.help,
      link: violation.helpUrl,
      elements: violation.nodes.map((node) => node.target.join(" ")),
    }));
  } finally {
    await tab.close();
  }
}

/** Runs each task with at most PARALLEL at a time. */
async function pool(tasks) {
  const results = [];
  let next = 0;
  async function worker() {
    while (next < tasks.length) {
      const task = tasks[next++];
      results.push(...(await task()));
    }
  }
  await Promise.all(Array.from({ length: Math.min(PARALLEL, tasks.length) }, worker));
  return results;
}

/** The findings of the same rule on the same page, with the schemes where it fails. */
function grouped(findings) {
  const groups = new Map();
  for (const finding of findings) {
    const key = `${finding.page}\0${finding.rule}`;
    const group = groups.get(key) ?? { ...finding, schemes: [], elements: [] };
    group.schemes.push(finding.scheme);
    for (const element of finding.elements) {
      if (!group.elements.includes(element)) {
        group.elements.push(element);
      }
    }
    groups.set(key, group);
  }
  return [...groups.values()].sort(
    (a, b) => a.page.localeCompare(b.page) || a.rule.localeCompare(b.rule),
  );
}

function described(group) {
  const shown = group.elements.slice(0, 3).map((element) => `\`${element}\``).join(", ");
  const more = group.elements.length > 3 ? ` and ${group.elements.length - 3} more` : "";
  return `${group.help}: ${group.elements.length} element(s) in ${group.schemes.join(" and ")}, ${shown}${more}.`;
}

/** What failed, why it matters and how to fix it, for the summary of the job. */
function summary(failing, lesser, pages, foreign) {
  const lines = ["## Accessibility of the website", ""];
  if (failing.length === 0) {
    lines.push(
      `axe-core found no serious or critical violation of WCAG 2.2 A or AA on ${pages} page(s), in the light and the dark scheme.`,
    );
  } else {
    lines.push(
      `axe-core found ${failing.length} serious or critical violation(s) of WCAG 2.2 A or AA on the pages below.`,
      "",
      "**Why it matters:** a reader who uses a screen reader, the keyboard alone or a larger contrast can't use what these rules find: text too faint to read, a link told apart by its color alone, a control without a name.",
      "",
      "**How to fix it:** the link of each rule explains the fix. A page of `docs/` is yours to fix; what every page shows, such as the header, comes from the blueprint, whose issue tracker takes it. Build the website and run the check again: `npm ci --prefix .github/a11y --ignore-scripts && node .github/a11y/check.mjs site`.",
      "",
      "| Page | Rule | Impact | What it found |",
      "| --- | --- | --- | --- |",
    );
    for (const group of failing) {
      lines.push(
        `| \`${group.page}\` | [${group.rule}](${group.link}) | ${group.impact} | ${described(group).replaceAll("|", "\\|")} |`,
      );
    }
  }
  if (lesser.length > 0) {
    const rules = [...new Set(lesser.map((group) => group.rule))].sort().join(", ");
    lines.push("", `Moderate or minor, which fail nothing: ${lesser.length} on the pages, of the rules ${rules}.`);
  }
  if (foreign.size > 0) {
    lines.push("", `The pages asked other servers, which the check refused: ${[...foreign].sort().join(", ")}.`);
  }
  return `${lines.join("\n")}\n`;
}

async function main(argv) {
  const [site] = argv;
  if (!site || !existsSync(path.join(site, "index.html"))) {
    console.error("Usage: node .github/a11y/check.mjs SITE: SITE is the folder of a built website, with its index.html.");
    return 2;
  }
  const pages = await pagesOf(site);
  const address = await addressOf(site);
  const foreign = new Set();
  const executablePath = process.env.CHROME || undefined;
  let browser;
  try {
    browser = await chromium.launch(executablePath ? { executablePath } : { channel: "chrome" });
  } catch (error) {
    console.error(`Chrome doesn't start: ${error.message.split("\n")[0]}`);
    console.error("Install Google Chrome, or name another Chrome or Chromium with CHROME=/path/to/chrome.");
    return 2;
  }
  let findings;
  try {
    const contexts = {};
    for (const scheme of Object.keys(SCHEMES)) {
      contexts[scheme] = await browser.newContext({ colorScheme: scheme, viewport: { width: 1280, height: 900 } });
      await serve(contexts[scheme], site, address, foreign);
    }
    const tasks = pages.flatMap((page) =>
      Object.keys(SCHEMES).map((scheme) => () => check(contexts[scheme], address, page, scheme)),
    );
    findings = await pool(tasks);
  } finally {
    await browser.close();
  }
  const groups = grouped(findings);
  const failing = groups.filter((group) => FAILING.has(group.impact));
  const lesser = groups.filter((group) => !FAILING.has(group.impact));
  const actions = process.env.GITHUB_ACTIONS === "true";
  // A check that only reports annotates with warnings.
  const level = process.env.REPORT_ONLY === "true" ? "warning" : "error";
  for (const group of failing) {
    const message = `${described(group)} ${group.link}`;
    if (actions) {
      const file = sourceOf(group.page);
      const where = file ? `file=${escaped(file, true)},` : "";
      console.log(`::${level} ${where}title=${escaped(`Accessibility: ${group.rule} on ${group.page}`, true)}::${escaped(message)}`);
    } else {
      console.log(`${group.impact} ${group.rule} on ${group.page}: ${message}`);
    }
  }
  const text = summary(failing, lesser, pages.length, foreign);
  if (process.env.GITHUB_STEP_SUMMARY) {
    await appendFile(process.env.GITHUB_STEP_SUMMARY, text);
  }
  console.log(
    failing.length === 0
      ? `No serious or critical violation of WCAG 2.2 A or AA on ${pages.length} page(s), in both schemes; ${lesser.length} lesser one(s).`
      : `${failing.length} serious or critical violation(s) of WCAG 2.2 A or AA on ${pages.length} page(s).`,
  );
  if (foreign.size > 0) {
    console.log(`The pages asked other servers, which the check refused: ${[...foreign].sort().join(", ")}.`);
  }
  return failing.length === 0 ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  process.exitCode = await main(process.argv.slice(2));
}
