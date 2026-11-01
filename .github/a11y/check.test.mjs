// The tests of the accessibility check, on a small website that the test writes: a
// palette with and without the media of the system, a toggle that does nothing, a
// website with one scheme, and a page of a further language without a translation; and
// on small repositories around a website, for its command line: the violations that
// fail and those accepted, the line baseline and the digest of the changed pages.
// scripts/check.sh runs them with every line and branch of the check covered.
//
//   npm ci --prefix .github/a11y --ignore-scripts
//   node --test .github/a11y/check.test.mjs
//
// https://github.com/Dennis-Otto/repo-blueprint

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  changedPages,
  checkSite,
  digestOf,
  escaped,
  launch,
  main,
  parseAccepted,
  readDigest,
  sorted,
  sourceOf,
} from "./check.mjs";

// As Material picks the scheme: the one it saved, else the first option whose media
// the system matches, else the first one; a toggle switches to its option. A page
// with data-stuck has a toggle that does nothing.
const PALETTE = `<script>
const options = [...document.querySelectorAll('input[name="__palette"]')];
const saved = JSON.parse(localStorage.getItem("__palette") || "null");
const index = saved ? saved.index : Math.max(0, options.findIndex(
  (option) => option.dataset.mdColorMedia && matchMedia(option.dataset.mdColorMedia).matches));
function show(chosen) {
  document.body.setAttribute("data-md-color-scheme", options[chosen].dataset.mdColorScheme);
  localStorage.setItem("__palette", JSON.stringify({ index: chosen }));
}
options.forEach((option, chosen) => option.addEventListener("change", () => {
  if (!document.body.hasAttribute("data-stuck")) show(chosen);
}));
show(index);
</script>`;

function option(scheme, media = "") {
  const attribute = media ? ` data-md-color-media="${media}"` : "";
  return `<input type="radio" name="__palette" aria-label="${scheme}" data-md-color-scheme="${scheme}"${attribute}>`;
}

// The text is too faint in the dark scheme alone.
function page(text, options, stuck = false) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Page</title>
<style>[data-md-color-scheme="slate"] { background: #222; } [data-md-color-scheme="slate"] p { color: #444; }</style>
</head><body data-md-color-scheme="default"${stuck ? " data-stuck" : ""}><main>
<form>${options.join("")}</form><article><h1>Page</h1><p>${text}</p></article>
</main>${options.length > 0 ? PALETTE : ""}</body></html>`;
}

const FOLLOWS = [option("default", "(prefers-color-scheme: light)"), option("slate", "(prefers-color-scheme: dark)")];
const TOGGLES = [option("default"), option("slate")];

let site;
let browser;

before(async () => {
  site = await mkdtemp(path.join(tmpdir(), "a11y-"));
  await mkdir(path.join(site, "de"));
  const pages = {
    "index.html": page("A palette with the media of each scheme.", FOLLOWS),
    "toggle.html": page("A palette without media.", TOGGLES),
    "stuck.html": page("A toggle that does nothing.", TOGGLES, true),
    "single.html": page("One scheme alone.", []),
    "de/index.html": page("A palette with the media of each scheme.", FOLLOWS),
    "de/toggle.html": page("Eine Palette ohne Medien.", TOGGLES),
  };
  for (const [name, html] of Object.entries(pages)) {
    await writeFile(path.join(site, name), html);
  }
  browser = await launch();
});

after(async () => {
  await browser?.close();
  await rm(site, { recursive: true, force: true });
});

/** The schemes in which a rule fails on a page. */
function failing(findings, page, rule) {
  return findings
    .filter((finding) => finding.page === page && finding.rule === rule)
    .map((finding) => finding.scheme)
    .sort();
}

test("every page is checked in the scheme that the system or the toggle shows", async () => {
  const { pages, same, findings } = await checkSite(browser, site);

  assert.deepEqual(pages, ["de/toggle.html", "index.html", "single.html", "stuck.html", "toggle.html"]);
  assert.deepEqual(same, ["de/index.html"]);
  assert.deepEqual(failing(findings, "index.html", "color-contrast"), ["dark"]);
  assert.deepEqual(failing(findings, "toggle.html", "color-contrast"), ["dark"]);
  assert.deepEqual(failing(findings, "de/toggle.html", "color-contrast"), ["dark"]);
  assert.deepEqual(failing(findings, "single.html", "color-contrast"), []);
  assert.deepEqual(failing(findings, "single.html", "color-scheme"), []);
  assert.deepEqual(failing(findings, "stuck.html", "color-scheme"), ["dark"]);
  assert.deepEqual(failing(findings, "stuck.html", "color-contrast"), []);
  const unshown = findings.find((finding) => finding.rule === "color-scheme");
  assert.equal(unshown.impact, "serious");
  assert.match(unshown.help, /doesn't show the dark scheme/);
});

test("the pages named are checked alone", async () => {
  const { pages, same } = await checkSite(browser, site, ["single.html"]);

  assert.deepEqual(pages, ["single.html"]);
  assert.deepEqual(same, []);
});

test("an annotation names the Markdown of a page, also of a further language", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "a11y-docs-"));
  try {
    await mkdir(path.join(root, "docs", "guide"), { recursive: true });
    for (const name of ["README.md", "guide.de.md", "guide/index.md"]) {
      await writeFile(path.join(root, "docs", name), "# Page\n");
    }
    assert.equal(sourceOf("index.html", root), "docs/README.md");
    assert.equal(sourceOf("de/guide.html", root), "docs/guide.de.md");
    assert.equal(sourceOf("guide.html", root), "docs/guide/index.md");
    assert.equal(sourceOf("gone.html", root), undefined);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("a value of an annotation keeps its lines and its separators", () => {
  assert.equal(escaped("50%\r\na"), "50%25%0D%0Aa");
  assert.equal(escaped("docs/a,b:c.md", true), "docs/a%2Cb%3Ac.md");
});

function clean(text) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Page</title></head><body><main><h1>${text}</h1></main></body></html>`;
}

// Text too faint to read in both schemes, each its own element.
function faint(paragraphs = 1) {
  const text = "<p>Too faint.</p>".repeat(paragraphs);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Page</title><style>p { color: #eee; }</style></head><body><main><h1>Faint</h1>${text}</main></body></html>`;
}

/** A small repository with a built website: a clean home page, a page with a
 * violation whose Markdown is in docs/, and one with a violation that has none. */
async function repository(t, accepted) {
  const root = await mkdtemp(path.join(tmpdir(), "a11y-repo-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const built = path.join(root, "site");
  await mkdir(path.join(built, "assets"), { recursive: true });
  await mkdir(path.join(root, ".github"));
  await mkdir(path.join(root, "docs"));
  await writeFile(path.join(root, "docs", "faint.md"), "# Faint\n");
  await writeFile(path.join(root, "mkdocs.yml"), "site_name: Test\n");
  await writeFile(path.join(built, "assets", "theme.css"), "body { margin: 0; }\n");
  await writeFile(path.join(built, "index.html"), clean("Home"));
  await writeFile(path.join(built, "faint.html"), faint());
  await writeFile(path.join(built, "hook.html"), faint());
  if (accepted !== undefined) {
    await writeFile(path.join(root, ".github", "a11y-accepted.toml"), accepted);
  }
  return { root, built };
}

/** Runs the command line of the check, with what it logged and, on a runner (the
 * option onRunner), its summary and outputs. */
async function run(t, repo, argv, { onRunner = false, ...env } = {}) {
  const lines = [];
  const log = t.mock.method(console, "log", (line) => lines.push(line));
  const error = t.mock.method(console, "error", (line) => lines.push(line));
  const saved = { ...process.env };
  const summaryFile = path.join(repo.root, "summary.md");
  const outputFile = path.join(repo.root, "output.txt");
  await writeFile(summaryFile, "");
  await writeFile(outputFile, "");
  for (const name of ["GITHUB_ACTIONS", "REPORT_ONLY", "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT"]) {
    delete process.env[name];
  }
  Object.assign(process.env, env);
  if (onRunner) {
    Object.assign(process.env, {
      GITHUB_ACTIONS: "true",
      GITHUB_STEP_SUMMARY: summaryFile,
      GITHUB_OUTPUT: outputFile,
    });
  }
  try {
    const status = await main(argv, repo.root);
    return {
      status,
      lines,
      summary: await readFile(summaryFile, "utf-8"),
      output: await readFile(outputFile, "utf-8"),
    };
  } finally {
    log.mock.restore();
    error.mock.restore();
    process.env = saved;
  }
}

function entry(name, rule = "color-contrast") {
  return `\n[[accepted]]\npage = "${name}"\nrule = "${rule}"\nreason = "Its colors are the demo."\n`;
}

test("a new violation fails, as an annotation at its Markdown or at mkdocs.yml", async (t) => {
  const repo = await repository(t);
  const { status, lines, summary } = await run(t, repo, [repo.built], { onRunner: true });

  assert.equal(status, 1);
  const annotations = lines.filter((line) => line.startsWith("::error "));
  assert.equal(annotations.length, 2);
  assert.match(annotations[0], /^::error file=docs\/faint\.md,title=Accessibility%3A color-contrast on faint\.html::/);
  assert.match(annotations[1], /^::error file=mkdocs\.yml,title=Accessibility%3A color-contrast on hook\.html::/);
  assert.match(summary, /2 serious or critical violation\(s\)/);
  assert.match(summary, /How to fix it/);
  assert.match(summary, /goes into `\.github\/a11y-accepted\.toml`, with its page, its rule and the reason/);
});

test("without a runner, a violation shows as a line of the log", async (t) => {
  const repo = await repository(t);
  const { status, lines } = await run(t, repo, [repo.built, "faint.html"]);

  assert.equal(status, 1);
  assert.match(lines[0], /^serious color-contrast on faint\.html: /);
});

test("a violation that the file accepts passes with its reason, and only that one", async (t) => {
  const repo = await repository(t, entry("faint.html"));
  const { status, lines, summary } = await run(t, repo, [repo.built], { onRunner: true });

  assert.equal(status, 1);
  assert.equal(lines.filter((line) => line.startsWith("::error ")).length, 1);
  assert.match(summary, /Accepted in `\.github\/a11y-accepted\.toml`, which fail nothing: 1/);
  assert.match(summary, /`faint\.html`, color-contrast: Its colors are the demo\./);
  await writeFile(path.join(repo.root, ".github", "a11y-accepted.toml"), entry("faint.html") + entry("hook.html"));
  const passed = await run(t, repo, [repo.built], { onRunner: true });
  assert.equal(passed.status, 0);
  assert.match(passed.lines.at(-1), /No new serious or critical violation .* 2 accepted, 0 lesser/);
});

test("an accepted violation that is gone is named, on a page that was checked or that no longer exists", async (t) => {
  const accepted = entry("index.html") + entry("gone.html") + entry("faint.html") + entry("hook.html");
  const repo = await repository(t, accepted);
  const { status, lines, summary } = await run(t, repo, [repo.built], { onRunner: true });

  assert.equal(status, 0);
  const warned = lines.filter((line) => line.startsWith("::warning "));
  assert.equal(warned.length, 2);
  assert.match(warned[0], /^::warning file=\.github\/a11y-accepted\.toml,title=Accessibility%3A an accepted violation is gone::.*on index\.html/);
  assert.match(warned[1], /on gone\.html/);
  assert.match(summary, /no longer found/);
  const local = await run(t, repo, [repo.built]);
  assert.ok(local.lines.some((line) => line.startsWith(".github/a11y-accepted.toml accepts color-contrast on index.html")));
});

test("an entry of a page that this run didn't check says nothing", () => {
  const entries = [{ page: "other.html", rule: "a", reason: "r" }];
  assert.deepEqual(sorted([], entries, ["index.html"], ["index.html", "other.html"]).gone, []);
});

test("an entry without its reason, or a file that isn't one, stops the check", async (t) => {
  for (const [text, message] of [
    ['[[accepted]]\npage = "a.html"\nrule = "b"\n', /entry 1 has no reason/],
    ['[[accepted]]\npage = "a.html"\nrule = "b"\nreason = "  "\n', /entry 1 has no reason/],
    ["[[accepted]\n", /isn't valid TOML/],
    ["other = 1\n", /the key other means nothing here/],
    ['baseline = "yes"\n', /baseline is true or false/],
    ['accepted = "all"\n', /accepted is a list of tables/],
  ]) {
    assert.throws(() => parseAccepted(text), message);
    const repo = await repository(t, text);
    const { status, lines } = await run(t, repo, [repo.built]);
    assert.equal(status, 2);
    assert.match(lines[0], message);
    // On a runner it says so at the file and in the summary, also on a fork.
    const seen = await run(t, repo, [repo.built], { onRunner: true });
    assert.equal(seen.status, 2);
    assert.ok(seen.lines.some((line) =>
      line.startsWith("::error file=.github/a11y-accepted.toml,title=Accessibility%3A the accepted violations::") &&
      message.test(line)));
    assert.match(seen.summary, message);
    assert.match(seen.summary, /How to fix it/);
  }
});

test("the line baseline accepts what a run of every page finds, once", async (t) => {
  const repo = await repository(t, "# What it accepts.\n\n# The first run writes.\nbaseline = true\n");
  const file = path.join(repo.root, ".github", "a11y-accepted.toml");

  const first = await run(t, repo, [repo.built], { onRunner: true });
  assert.equal(first.status, 0);
  assert.equal(first.lines.filter((line) => line.startsWith("::warning ")).length, 2);
  assert.equal(first.output, "written=true\n");
  assert.match(first.summary, /still has its line `baseline = true`/);
  const written = await readFile(file, "utf-8");
  assert.ok(written.startsWith("# What it accepts.\n\n[[accepted]]\n"));
  assert.doesNotMatch(written, /baseline|first run/);
  const { baseline, entries } = parseAccepted(written);
  assert.equal(baseline, false);
  assert.deepEqual(entries.map((each) => each.page), ["faint.html", "hook.html"]);
  assert.ok(entries.every((each) => /Fix it, or say here why it stays/.test(each.reason)));

  const second = await run(t, repo, [repo.built], { onRunner: true });
  assert.equal(second.status, 0);
  assert.equal(second.output, "");
  await writeFile(path.join(repo.built, "new.html"), faint());
  const third = await run(t, repo, [repo.built], { onRunner: true });
  assert.equal(third.status, 1);
  assert.match(third.lines.find((line) => line.startsWith("::error ")), /on new\.html/);
});

test("the line baseline on a website without a violation goes as well, also outside a runner", async (t) => {
  const repo = await repository(t, "baseline = true\n");
  await writeFile(path.join(repo.built, "faint.html"), clean("Faint"));
  await writeFile(path.join(repo.built, "hook.html"), clean("Hook"));

  const { status, lines } = await run(t, repo, [repo.built]);
  assert.equal(status, 0);
  assert.ok(lines.some((line) => /now accepts the 0 violation/.test(line)));
  assert.equal(await readFile(path.join(repo.root, ".github", "a11y-accepted.toml"), "utf-8"), "");
});

test("a run of some pages with the line baseline reports, and writes nothing", async (t) => {
  const text = "baseline = true\n";
  const repo = await repository(t, text);
  const file = path.join(repo.root, ".github", "a11y-accepted.toml");
  const digest = path.join(repo.root, "digest.json");
  await writeFile(digest, JSON.stringify(await digestOf(repo.built, repo.root)));
  await writeFile(path.join(repo.built, "faint.html"), faint(2));

  const named = await run(t, repo, [repo.built, "hook.html"], { onRunner: true });
  assert.equal(named.status, 0);
  assert.equal(await readFile(file, "utf-8"), text);
  const changed = await run(t, repo, [repo.built, "--changed-since", digest], { onRunner: true });
  assert.equal(changed.status, 0);
  assert.equal(changed.output, "");
  assert.equal(await readFile(file, "utf-8"), text);
  assert.match(changed.lines.find((line) => line.startsWith("::warning ")), /on faint\.html/);
});

test("REPORT_ONLY reports a violation as a warning", async (t) => {
  const repo = await repository(t);
  const { status, lines } = await run(t, repo, [repo.built, "faint.html"], { onRunner: true, REPORT_ONLY: "true" });

  assert.equal(status, 0);
  assert.match(lines[0], /^::warning file=docs\/faint\.md,/);
});

test("the digest leaves out the date of a page and names what every page shares", async (t) => {
  const repo = await repository(t, "");
  const before = await digestOf(repo.built, repo.root);
  assert.deepEqual(Object.keys(before.pages), ["faint.html", "hook.html", "index.html"]);
  assert.deepEqual(Object.keys(before.shared), ["site/assets/theme.css", "mkdocs.yml", ".github/a11y-accepted.toml"]);
  assert.match(before.pages["index.html"], /^[0-9a-f]{64}$/);

  const dated = (date) => clean("Home").replace("</main>", `<aside class="md-source-file">${date}</aside></main>`);
  await writeFile(path.join(repo.built, "index.html"), dated("January"));
  const january = await digestOf(repo.built, repo.root);
  await writeFile(path.join(repo.built, "index.html"), dated("March"));
  const march = await digestOf(repo.built, repo.root);
  assert.deepEqual(changedPages(march, january), { pages: [], reason: "" });
  await writeFile(path.join(repo.built, "index.html"), clean("Other"));
  const other = await digestOf(repo.built, repo.root);
  assert.deepEqual(changedPages(other, march), { pages: ["index.html"], reason: "" });
});

test("only a page that differs, or a new one, needs the check, unless what all share differs", () => {
  const before = { format: 1, shared: { a: "1", b: "2", c: "3", d: "4" }, pages: { "x.html": "1", "y.html": "2", "gone.html": "3" } };
  const same = { ...before, pages: { "x.html": "1", "y.html": "changed", "new.html": "4" } };
  assert.deepEqual(changedPages(same, before), { pages: ["y.html", "new.html"], reason: "" });
  assert.equal(changedPages(same, null).pages, null);
  assert.match(changedPages(same, null).reason, /no digest of main/);
  const one = changedPages({ ...before, shared: { ...before.shared, a: "new" } }, before);
  assert.equal(one.pages, null);
  assert.equal(one.reason, "`a`, which every page shares, differ from main");
  const added = changedPages({ ...before, shared: { ...before.shared, e: "5" } }, before);
  assert.match(added.reason, /^`e`/);
  const all = changedPages({ ...before, shared: { a: "9", b: "9", c: "9", d: "9" } }, before);
  assert.match(all.reason, /^`a`, `b`, `c` and 1 more, which/);
});

test("a digest that is missing, broken or of another format counts as none", async (t) => {
  const repo = await repository(t);
  const file = path.join(repo.root, "digest.json");
  assert.equal(await readDigest(file), null);
  for (const text of ["not json", '{"format":2,"shared":{},"pages":{}}', '{"format":1,"pages":{}}', '{"format":1,"shared":{}}']) {
    await writeFile(file, text);
    assert.equal(await readDigest(file), null);
  }
  await writeFile(file, '{"format":1,"shared":{},"pages":{}}');
  assert.deepEqual(await readDigest(file), { format: 1, shared: {}, pages: {} });
});

test("a pull request checks the pages that differ from the digest of main alone", async (t) => {
  const repo = await repository(t, entry("faint.html") + entry("hook.html"));
  const digest = path.join(repo.root, "digest.json");
  const base = await run(t, repo, [repo.built, "--write-digest", digest], { onRunner: true });
  assert.equal(base.status, 0);
  assert.match(base.lines.at(-1), /on 3 page\(s\)/);
  assert.equal(JSON.parse(await readFile(digest, "utf-8")).format, 1);

  // Nothing differs: no browser starts, as a Chrome that doesn't exist shows.
  const noChrome = path.join(repo.root, "no-chrome");
  const nothing = await run(t, repo, [repo.built, "--changed-since", digest], { onRunner: true, CHROME: noChrome });
  assert.equal(nothing.status, 0);
  assert.match(nothing.lines[0], /No page differs from the website of main/);
  assert.match(nothing.summary, /No page differs/);
  const quiet = await run(t, repo, [repo.built, "--changed-since", digest], { CHROME: noChrome });
  assert.equal(quiet.status, 0);

  // A new page with a violation fails; the other pages stay closed.
  await writeFile(path.join(repo.built, "new.html"), faint());
  const one = await run(t, repo, [repo.built, "--changed-since", digest], { onRunner: true });
  assert.equal(one.status, 1);
  assert.match(one.lines.at(-1), /on the 1 changed page\(s\) of 4 in the light and the dark scheme/);
  assert.match(one.lines.find((line) => line.startsWith("::error ")), /on new\.html/);

  // What every page shares differs: every page again, which says why.
  await writeFile(path.join(repo.root, "mkdocs.yml"), "site_name: Other\n");
  const every = await run(t, repo, [repo.built, "--changed-since", digest], { onRunner: true });
  assert.match(every.lines.at(-1), /on 4 page\(s\)/);
  assert.ok(every.lines.includes("It checked every page, because `mkdocs.yml`, which every page shares, differ from main."));
  assert.match(every.summary, /It checked every page, because `mkdocs\.yml`/);

  // Without a digest, every page as well; pages named are those pages.
  const none = await run(t, repo, [repo.built, "--changed-since", path.join(repo.root, "none.json")]);
  assert.ok(none.lines.some((line) => /no digest of main/.test(line)));
  const named = await run(t, repo, [repo.built, "index.html", "--changed-since", digest]);
  assert.equal(named.status, 0);
  assert.match(named.lines.at(-1), /on 1 page\(s\)/);
});

test("a page without a translation stays out when it differs as well", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-same-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  await mkdir(path.join(built, "de"));
  await writeFile(path.join(built, "guide.html"), clean("Guide"));
  await writeFile(path.join(built, "de", "guide.html"), clean("Guide"));
  const { pages, same } = await checkSite(browser, built, [], ["guide.html", "de/guide.html"]);
  assert.deepEqual(pages, ["guide.html"]);
  assert.deepEqual(same, []);
});

test("what the check can't run with stops it with the status 2", async (t) => {
  const repo = await repository(t);
  const usage = await run(t, repo, []);
  assert.equal(usage.status, 2);
  assert.match(usage.lines[0], /^Usage: /);
  assert.equal((await run(t, repo, [path.join(repo.root, "docs")])).status, 2);
  assert.equal((await run(t, repo, [repo.built, "--unknown"])).status, 2);
  const missing = await run(t, repo, [repo.built, "gone.html"]);
  assert.equal(missing.status, 2);
  assert.match(missing.lines[0], /has no page gone\.html/);
  const chrome = await run(t, repo, [repo.built], { CHROME: path.join(repo.root, "no-chrome") });
  assert.equal(chrome.status, 2);
  assert.match(chrome.lines[0], /^Chrome doesn't start/);
  assert.match(chrome.lines[1], /CHROME=/);
});

test("the website answers from its folder, and other servers are refused and named", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "index.html"), clean("Home").replace(
    "</head>",
    '<link rel="canonical" href="https://example.test/project/"></head>',
  ));
  await writeFile(path.join(repo.built, "assets", "data.bin"), "data");
  await writeFile(path.join(repo.built, "assets", "index.html"), clean("Assets"));
  const pictures = ["https://other.test/a.png", "assets/data.bin", "missing.png", "assets/", "/project/%2e%2e%2foutside.png"];
  await writeFile(path.join(repo.built, "asks.html"), clean("Asks").replace(
    "</main>",
    `${pictures.map((source, index) => `<img alt="${index}" src="${source}">`).join("")}</main>`,
  ));
  const { status, lines, summary } = await run(t, repo, [repo.built, "asks.html"], { onRunner: true });

  assert.equal(status, 0);
  assert.ok(lines.includes("The pages asked other servers, which the check refused: https://other.test."));
  assert.match(summary, /asked other servers, which the check refused: https:\/\/other\.test/);
});

test("a website without a home page has no address of its own", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-home-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  await writeFile(path.join(built, "only.html"), clean("Only"));
  const { pages, findings } = await checkSite(browser, built);
  assert.deepEqual(pages, ["only.html"]);
  assert.deepEqual(findings, []);
});

test("a website with a home page without a canonical address is served as well", async (t) => {
  const repo = await repository(t);
  const { pages } = await checkSite(browser, repo.built, ["index.html"]);
  assert.deepEqual(pages, ["index.html"]);
});

test("a lesser violation fails nothing, and the summary counts it", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "lesser.html"), clean("Lesser").replace('lang="en"', 'lang="en" xml:lang="de"'));
  const { status, summary, lines } = await run(t, repo, [repo.built, "lesser.html"], { onRunner: true });
  assert.equal(status, 0);
  assert.match(summary, /Moderate or minor, which fail nothing: 1 on the pages, of the rules html-xml-lang-mismatch/);
  assert.match(lines.at(-1), /0 accepted, 1 lesser one/);
});

test("the summary lists three elements of a rule and counts the others", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "faint.html"), faint(5));
  const { summary } = await run(t, repo, [repo.built, "faint.html"], { onRunner: true });
  assert.match(summary, /5 element\(s\) in light and dark, .* and 2 more/);
});

test("two rules on one page follow each other by name", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "faint.html"), faint().replace("</main>", '<img src="picture.png"></main>'));
  const { lines } = await run(t, repo, [repo.built, "faint.html"]);
  assert.match(lines[0], /color-contrast/);
  assert.match(lines[1], /image-alt/);
});

test("the command line runs the check when node starts the file", () => {
  const check = fileURLToPath(new URL("./check.mjs", import.meta.url));
  const { status, stderr } = spawnSync(process.execPath, [check], { encoding: "utf-8" });
  assert.equal(status, 2);
  assert.match(stderr, /^Usage: /);
});
