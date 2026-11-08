// The tests of the accessibility check, on a small website that the test writes: a
// palette with and without the media of the system, a toggle that does nothing, a
// website with one scheme, and a page of a further language without a translation; and
// on small repositories around a website, for its command line: the violations that
// fail and those accepted, the line baseline and the digest of the changed pages; on
// pages wider than a phone, and those that only seem to be; and on pages that lead to
// another address. Two tests run at the same time, each in folders of its own, and
// most check in one browser of the four, where what they test shows in any one.
// scripts/check.sh runs them with every line and branch of the check covered.
//
//   npm ci --prefix .github/a11y --ignore-scripts
//   node --test .github/a11y/check.test.mjs
//
// https://github.com/Dennis-Otto/repo-blueprint

import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { after, before, suite, test as nodeTest } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import {
  BROWSERS,
  changedPages,
  checkSite,
  digestOf,
  escaped,
  launch,
  main,
  parseAccepted,
  readAccepted,
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
// The pages of the tests show their scheme as soon as they have loaded, or never: a
// short wait for it, instead of the 3 s of a real website, finds the same.
const QUICK = { schemeTimeout: 200 };
// The browser of the light scheme at the width of a desktop, which a test checks in
// when what it tests shows in any one browser, such as the pages that a run checks.
const ONE = { browsers: BROWSERS.slice(0, 1) };
// The browsers at the width of a phone, where a page may scroll sideways.
const PHONES = { browsers: BROWSERS.filter(({ screen }) => screen.width < 1280) };
// The browser of the dark scheme at the width of a desktop, where the faint text of the
// pages of Material's kind shows.
const DARK = { browsers: BROWSERS.filter(({ scheme, screen }) => scheme === "dark" && screen.width === 1280) };

// Two tests run at the same time, each in folders of its own: test() collects them for
// the suite at the end of this file. A check opens pages at the same time already, one
// for each core, so a second test keeps the cores busy while the first one waits; more
// tests would only slow each other down, and axe-core gives up on a frame of a page
// that takes it more than a second to load into.
const CONCURRENCY = 2;
const tests = [];

function test(name, fn) {
  tests.push({ name, fn });
}

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

/** The schemes in which a rule fails on a page, at a width of the screen. */
function failing(findings, page, rule, width = 1280) {
  return findings
    .filter((finding) => finding.page === page && finding.rule === rule && finding.width === width)
    .map((finding) => finding.scheme)
    .sort();
}

test("every page is checked in the scheme that the system or the toggle shows", async () => {
  const { pages, same, findings } = await checkSite(browser, site, [], null, QUICK);

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
  // The same at the width of a phone, in the browser of each scheme there.
  assert.deepEqual(failing(findings, "index.html", "color-contrast", 375), ["dark"]);
  assert.deepEqual(failing(findings, "stuck.html", "color-scheme", 375), ["dark"]);
  assert.deepEqual(failing(findings, "single.html", "color-contrast", 375), []);
});

test("a page that shows its scheme a moment after it loaded is waited for", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-late-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  // Its script shows the scheme a second after the event load, which the check waits for.
  const late = page("Its palette shows a moment later.", FOLLOWS)
    .replace("show(index);", "addEventListener(\"load\", () => setTimeout(() => show(index), 1_000));");
  await writeFile(path.join(built, "late.html"), late);
  const { findings } = await checkSite(browser, built, [], null, DARK);

  assert.deepEqual(failing(findings, "late.html", "color-contrast"), ["dark"]);
  assert.deepEqual(failing(findings, "late.html", "color-scheme"), []);
});

test("the text inside a fold of the page of the automation is checked as well", async (t) => {
  const folded = await mkdtemp(path.join(tmpdir(), "a11y-fold-"));
  t.after(() => rm(folded, { recursive: true, force: true }));
  const fold = '<details class="blueprint-fold"><summary>Title</summary><p>Faint words.</p></details>';
  await writeFile(path.join(folded, "index.html"), page("", FOLLOWS).replace("<p></p>", fold));

  const { findings } = await checkSite(browser, folded, [], null, DARK);

  const faint = findings.find((finding) => finding.rule === "color-contrast");
  assert.equal(faint.scheme, "dark");
  assert.ok(faint.elements.some((element) => /\bp\b/.test(element)), faint.elements.join());
});

test("the pages named are checked alone", async () => {
  const { pages, same } = await checkSite(browser, site, ["single.html"], null, ONE);

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

// The variables of a runner, which a run of the command line has only when the test
// says so.
const RUNNER = ["GITHUB_ACTIONS", "REPORT_ONLY", "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT"];

/** Runs the command line of the check, with what it logged and, on a runner (the
 * option onRunner), its summary and outputs: with variables of its own beside those of
 * this process, and a log of its own, so that it runs at the same time as other tests.
 * It checks in the browser of the tests, or starts a Chrome of its own, as the command
 * line does, when the test asks for one (ownChrome) or names one in CHROME; in the
 * browser ONE, or in each browser with the option every. */
async function run(repo, argv, { onRunner = false, ownChrome = false, every = false, ...vars } = {}) {
  const lines = [];
  const summaryFile = path.join(repo.root, "summary.md");
  const outputFile = path.join(repo.root, "output.txt");
  await writeFile(summaryFile, "");
  await writeFile(outputFile, "");
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !RUNNER.includes(name)));
  Object.assign(env, vars);
  if (onRunner) {
    Object.assign(env, { GITHUB_ACTIONS: "true", GITHUB_STEP_SUMMARY: summaryFile, GITHUB_OUTPUT: outputFile });
  }
  const status = await main(argv, repo.root, {
    env,
    log: (line) => lines.push(line),
    logError: (line) => lines.push(line),
    browser: ownChrome || vars.CHROME ? null : browser,
    browsers: every ? BROWSERS : ONE.browsers,
  });
  return {
    status,
    lines,
    summary: await readFile(summaryFile, "utf-8"),
    output: await readFile(outputFile, "utf-8"),
  };
}

function entry(name, rule = "color-contrast") {
  return `\n[[accepted]]\npage = "${name}"\nrule = "${rule}"\nreason = "Its colors are the demo."\n`;
}

test("a new violation fails, as an annotation at its Markdown or at mkdocs.yml", async (t) => {
  const repo = await repository(t);
  const { status, lines, summary } = await run(repo, [repo.built], { onRunner: true });

  assert.equal(status, 1);
  const annotations = lines.filter((line) => line.startsWith("::error "));
  assert.equal(annotations.length, 2);
  assert.match(annotations[0], /^::error file=docs\/faint\.md,title=Accessibility%3A color-contrast on faint\.html::/);
  assert.match(annotations[1], /^::error file=mkdocs\.yml,title=Accessibility%3A color-contrast on hook\.html::/);
  assert.match(summary, /2 serious or critical violation\(s\)/);
  assert.match(summary, /How to fix it/);
  assert.match(summary, /goes into `\.github\/a11y-accepted\.toml`, with its page, its rule and the reason/);
});

test("without a runner, a violation shows as a line of the log, from a Chrome of its own in each browser", async (t) => {
  const repo = await repository(t);
  const { status, lines } = await run(repo, [repo.built, "faint.html"], { ownChrome: true, every: true });

  assert.equal(status, 1);
  assert.match(lines[0], /^serious color-contrast on faint\.html: .* in light and dark at 1280 px, light and dark at 375 px, /);
  assert.match(lines.at(-1), /on 1 page\(s\) in the light and the dark scheme, at 1280 and 375 px wide\.$/);
});

test("a violation that the file accepts passes with its reason, and only that one", async (t) => {
  const repo = await repository(t, entry("faint.html"));
  const { status, lines, summary } = await run(repo, [repo.built], { onRunner: true });

  assert.equal(status, 1);
  assert.equal(lines.filter((line) => line.startsWith("::error ")).length, 1);
  assert.match(summary, /Accepted in `\.github\/a11y-accepted\.toml`, which fail nothing: 1/);
  assert.match(summary, /`faint\.html`, color-contrast: Its colors are the demo\./);
  await writeFile(path.join(repo.root, ".github", "a11y-accepted.toml"), entry("faint.html") + entry("hook.html"));
  const passed = await run(repo, [repo.built], { onRunner: true });
  assert.equal(passed.status, 0);
  assert.match(passed.lines.at(-1), /No new serious or critical violation .* 2 accepted, 0 lesser/);
});

test("an accepted violation that is gone is named, on a page that was checked or that no longer exists", async (t) => {
  const accepted = entry("index.html") + entry("gone.html") + entry("faint.html") + entry("hook.html");
  const repo = await repository(t, accepted);
  const { status, lines, summary } = await run(repo, [repo.built], { onRunner: true });

  assert.equal(status, 0);
  const warned = lines.filter((line) => line.startsWith("::warning "));
  assert.equal(warned.length, 2);
  assert.match(warned[0], /^::warning file=\.github\/a11y-accepted\.toml,title=Accessibility%3A an accepted violation is gone::.*on index\.html/);
  assert.match(warned[1], /on gone\.html/);
  assert.match(summary, /no longer found/);
  const local = await run(repo, [repo.built]);
  assert.ok(local.lines.some((line) => line.startsWith(".github/a11y-accepted.toml accepts color-contrast on index.html")));
});

test("an entry of a page that this run didn't check says nothing", () => {
  const entries = [{ page: "other.html", rule: "a", reason: "r" }];
  assert.deepEqual(sorted([], entries, ["index.html"], ["index.html", "other.html"]).gone, []);
});

test("the error about a file that isn't TOML keeps the error of the parser as its cause", () => {
  assert.throws(
    () => parseAccepted("[[accepted]\n"),
    (error) => error.cause instanceof Error,
  );
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
    const { status, lines } = await run(repo, [repo.built]);
    assert.equal(status, 2);
    assert.match(lines[0], message);
    // On a runner it says so at the file and in the summary, also on a fork.
    const seen = await run(repo, [repo.built], { onRunner: true });
    assert.equal(seen.status, 2);
    assert.ok(seen.lines.some((line) =>
      line.startsWith("::error file=.github/a11y-accepted.toml,title=Accessibility%3A the accepted violations::") &&
      message.test(line)));
    assert.match(seen.summary, message);
    assert.match(seen.summary, /How to fix it/);
  }
});

test("a repository without the file of accepted violations has none, and a file that can't be read stops the check", async (t) => {
  const repo = await repository(t);
  const file = path.join(repo.root, ".github", "a11y-accepted.toml");
  assert.equal(await readAccepted(file), "");
  await writeFile(file, "baseline = true\n");
  assert.equal(await readAccepted(file), "baseline = true\n");
  // A folder at that place is no missing file: it isn't to pass as nothing accepted.
  await rm(file);
  await mkdir(file);
  await assert.rejects(readAccepted(file), { code: "EISDIR" });
});

test("the line baseline accepts what a run of every page finds, once", async (t) => {
  const repo = await repository(t, "# What it accepts.\n\n# The first run writes.\nbaseline = true\n");
  const file = path.join(repo.root, ".github", "a11y-accepted.toml");

  const first = await run(repo, [repo.built], { onRunner: true });
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

  const second = await run(repo, [repo.built], { onRunner: true });
  assert.equal(second.status, 0);
  assert.equal(second.output, "");
  await writeFile(path.join(repo.built, "new.html"), faint());
  const third = await run(repo, [repo.built], { onRunner: true });
  assert.equal(third.status, 1);
  assert.match(third.lines.find((line) => line.startsWith("::error ")), /on new\.html/);
});

test("the line baseline on a website without a violation goes as well, also outside a runner", async (t) => {
  const repo = await repository(t, "baseline = true\n");
  await writeFile(path.join(repo.built, "faint.html"), clean("Faint"));
  await writeFile(path.join(repo.built, "hook.html"), clean("Hook"));

  const { status, lines } = await run(repo, [repo.built]);
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

  const named = await run(repo, [repo.built, "hook.html"], { onRunner: true });
  assert.equal(named.status, 0);
  assert.equal(await readFile(file, "utf-8"), text);
  const changed = await run(repo, [repo.built, "--changed-since", digest], { onRunner: true });
  assert.equal(changed.status, 0);
  assert.equal(changed.output, "");
  assert.equal(await readFile(file, "utf-8"), text);
  assert.match(changed.lines.find((line) => line.startsWith("::warning ")), /on faint\.html/);
});

test("REPORT_ONLY reports a violation as a warning", async (t) => {
  const repo = await repository(t);
  const { status, lines } = await run(repo, [repo.built, "faint.html"], { onRunner: true, REPORT_ONLY: "true" });

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
  const base = await run(repo, [repo.built, "--write-digest", digest], { onRunner: true });
  assert.equal(base.status, 0);
  assert.match(base.lines.at(-1), /on 3 page\(s\)/);
  assert.equal(JSON.parse(await readFile(digest, "utf-8")).format, 1);

  // Nothing differs: no browser starts, as a Chrome that doesn't exist shows.
  const noChrome = path.join(repo.root, "no-chrome");
  const nothing = await run(repo, [repo.built, "--changed-since", digest], { onRunner: true, CHROME: noChrome });
  assert.equal(nothing.status, 0);
  assert.match(nothing.lines[0], /No page differs from the website of main/);
  assert.match(nothing.summary, /No page differs/);
  const quiet = await run(repo, [repo.built, "--changed-since", digest], { CHROME: noChrome });
  assert.equal(quiet.status, 0);

  // A new page with a violation fails; the other pages stay closed.
  await writeFile(path.join(repo.built, "new.html"), faint());
  const one = await run(repo, [repo.built, "--changed-since", digest], { onRunner: true });
  assert.equal(one.status, 1);
  assert.match(one.lines.at(-1), /on the 1 changed page\(s\) of 4 in the light scheme, at 1280 px wide\.$/);
  assert.match(one.lines.find((line) => line.startsWith("::error ")), /on new\.html/);

  // What every page shares differs: every page again, which says why.
  await writeFile(path.join(repo.root, "mkdocs.yml"), "site_name: Other\n");
  const every = await run(repo, [repo.built, "--changed-since", digest], { onRunner: true });
  assert.match(every.lines.at(-1), /on 4 page\(s\)/);
  assert.ok(every.lines.includes("It checked every page, because `mkdocs.yml`, which every page shares, differ from main."));
  assert.match(every.summary, /It checked every page, because `mkdocs\.yml`/);

  // Without a digest, every page as well; pages named are those pages.
  const none = await run(repo, [repo.built, "--changed-since", path.join(repo.root, "none.json")]);
  assert.ok(none.lines.some((line) => /no digest of main/.test(line)));
  const named = await run(repo, [repo.built, "index.html", "--changed-since", digest]);
  assert.equal(named.status, 0);
  assert.match(named.lines.at(-1), /on 1 page\(s\)/);
});

test("a page without a translation stays out when it differs as well", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-same-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  await mkdir(path.join(built, "de"));
  await writeFile(path.join(built, "guide.html"), clean("Guide"));
  await writeFile(path.join(built, "de", "guide.html"), clean("Guide"));
  const { pages, same } = await checkSite(browser, built, [], ["guide.html", "de/guide.html"], ONE);
  assert.deepEqual(pages, ["guide.html"]);
  assert.deepEqual(same, []);
});

test("what the check can't run with stops it with the status 2", async (t) => {
  const repo = await repository(t);
  const usage = await run(repo, []);
  assert.equal(usage.status, 2);
  assert.match(usage.lines[0], /^Usage: /);
  assert.equal((await run(repo, [path.join(repo.root, "docs")])).status, 2);
  assert.equal((await run(repo, [repo.built, "--unknown"])).status, 2);
  const missing = await run(repo, [repo.built, "gone.html"]);
  assert.equal(missing.status, 2);
  assert.match(missing.lines[0], /has no page gone\.html/);
  const chrome = await run(repo, [repo.built], { CHROME: path.join(repo.root, "no-chrome") });
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
  const { status, lines, summary } = await run(repo, [repo.built, "asks.html"], { onRunner: true });

  assert.equal(status, 0);
  assert.ok(lines.includes("The pages asked other servers, which the check refused: https://other.test."));
  assert.match(summary, /asked other servers, which the check refused: https:\/\/other\.test/);
});

test("a website without a home page has no address of its own", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-home-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  await writeFile(path.join(built, "only.html"), clean("Only"));
  const { pages, findings } = await checkSite(browser, built, [], null, ONE);
  assert.deepEqual(pages, ["only.html"]);
  assert.deepEqual(findings, []);
});

test("a website with a home page without a canonical address is served as well", async (t) => {
  const repo = await repository(t);
  const { pages } = await checkSite(browser, repo.built, ["index.html"], null, ONE);
  assert.deepEqual(pages, ["index.html"]);
});

test("a lesser violation fails nothing, and the summary counts it", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "lesser.html"), clean("Lesser").replace('lang="en"', 'lang="en" xml:lang="de"'));
  const { status, summary, lines } = await run(repo, [repo.built, "lesser.html"], { onRunner: true });
  assert.equal(status, 0);
  assert.match(summary, /Moderate or minor, which fail nothing: 1 on the pages, of the rules html-xml-lang-mismatch/);
  assert.match(lines.at(-1), /0 accepted, 1 lesser one/);
});

test("the summary lists three elements of a rule and counts the others", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "faint.html"), faint(5));
  const { summary } = await run(repo, [repo.built, "faint.html"], { onRunner: true, every: true });
  assert.match(summary, /5 element\(s\) in light and dark at 1280 px, light and dark at 375 px, .* and 2 more/);
});

test("two rules on one page follow each other by name", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "faint.html"), faint().replace("</main>", '<img src="picture.png"></main>'));
  const { lines } = await run(repo, [repo.built, "faint.html"]);
  assert.match(lines[0], /color-contrast/);
  assert.match(lines[1], /image-alt/);
});

/** A page with what the test puts into it and a style of its own. */
function styled(body, style = "") {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Page</title><style>${style}</style></head><body><main><h1>Page</h1>${body}</main></body></html>`;
}

/** What the check names at the width of a phone, page by page: the widest element that
 * overflows on a page that scrolls sideways, and nothing on one that fits; in the
 * browsers of options, or in each one. */
async function reflowed(t, pages, options = {}) {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-reflow-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  for (const [name, [body, style]] of Object.entries(pages)) {
    await writeFile(path.join(built, `${name}.html`), styled(body, style));
  }
  const { findings } = await checkSite(browser, built, [], null, options);
  const found = {};
  for (const name of Object.keys(pages)) {
    const finding = findings.find((each) => each.page === `${name}.html` && each.rule === "reflow");
    found[name] = finding?.elements;
  }
  return { found, findings };
}

const WORD = "unbreakable".repeat(10);

test("a page that scrolls sideways on a phone fails, and names the widest element that overflows", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.root, "docs", "wide.md"), "# Wide\n");
  await writeFile(path.join(repo.built, "wide.html"), styled(
    '<table class="data wide" style="width: 700px"><tr><td>Name</td><td>Value</td></tr></table>',
  ));
  const { status, lines, summary } = await run(repo, [repo.built, "wide.html"], { onRunner: true, every: true });

  assert.equal(status, 1);
  assert.match(lines[0], /^::error file=docs\/wide\.md,title=Accessibility%3A reflow on wide\.html::The page is \d+ px wide on a screen of 375 px, /);
  assert.match(lines[0], /in light and dark at 375 px, `table\.data\.wide "Name Value"`\./);
  assert.match(lines[0], /https:\/\/www\.w3\.org\/WAI\/WCAG22\/Understanding\/reflow\.html$/);
  assert.match(summary, /\| `wide\.html` \| \[reflow\]\(https:\/\/www\.w3\.org\/WAI\/WCAG22\/Understanding\/reflow\.html\) \| serious \|/);
  assert.match(summary, /\*\*A page that scrolls sideways:\*\* let what is wide wrap, or put it in a frame that scrolls on its own/);
  assert.match(summary, /tabindex="0"/);
});

test("a violation of another rule leaves out what fixes a page that scrolls sideways", async (t) => {
  const repo = await repository(t);
  const { status, summary } = await run(repo, [repo.built, "faint.html"], { onRunner: true });

  assert.equal(status, 1);
  assert.doesNotMatch(summary, /A page that scrolls sideways/);
});

test("a page that scrolls sideways on a phone passes when the file accepts it", async (t) => {
  const repo = await repository(t, entry("wide.html", "reflow"));
  await writeFile(path.join(repo.built, "wide.html"), styled('<div style="width: 700px">Wide</div>'));
  const { status, summary } = await run(repo, [repo.built, "wide.html"], { onRunner: true, every: true });

  assert.equal(status, 0);
  assert.match(summary, /`wide\.html`, reflow: Its colors are the demo\./);
});

test("what fits on a phone, wraps or scrolls in a frame of its own doesn't scroll the page", async (t) => {
  const { found } = await reflowed(t, {
    fits: ['<div style="width: 300px">Fits</div>'],
    wraps: [`<p style="overflow-wrap: anywhere">${WORD}</p>`],
    frame: ['<div tabindex="0" style="overflow-x: auto"><table><tr><td style="width: 700px">Wide</td></tr></table></div>'],
    fixed: ['<div style="position: fixed; top: 0; left: 0; width: 700px">Stays</div>'],
  }, PHONES);

  assert.deepEqual(found, { fits: undefined, wraps: undefined, frame: undefined, fixed: undefined });
});

test("the element that a page names is the widest of those that overflow", async (t) => {
  const { found, findings } = await reflowed(t, {
    // Of what overflows, the widest and not the one that reaches furthest.
    widest: ['<div class="wide" style="width: 700px">Wide</div><div class="far" style="position: relative; left: 800px; width: 100px">Far</div>'],
    // Of an element and one inside it with the same width, the inner one.
    inner: ['<div style="width: 700px"><section id="inner" style="width: 700px">Inner</section></div>'],
    // A word that doesn't wrap leaves its box as wide as the screen.
    word: [`<p>${WORD}</p>`],
    // What stays in a frame or on the screen makes the page no wider, however wide.
    among: [`<div style="position: fixed; width: 2000px"><span>Stays</span></div>
      <div tabindex="0" style="overflow-x: auto"><div style="width: 1500px">Frame</div></div>
      <pre tabindex="0" style="overflow-x: auto">${WORD.repeat(3)}</pre>
      <section class="culprit" style="width: 500px">Wide</section>`],
    // Nothing of the page has a box that overflows, so the page as a whole is named.
    pseudo: ["", 'body::after { content: ""; position: absolute; top: 0; left: 0; width: 900px; height: 1px; }'],
  }, PHONES);

  assert.deepEqual(found.widest, ['div.wide "Wide"']);
  assert.deepEqual(found.inner, ['#inner "Inner"']);
  assert.deepEqual(found.word, [`p "${WORD.slice(0, 40)}"`]);
  assert.deepEqual(found.among, ['section.culprit "Wide"']);
  assert.deepEqual(found.pseudo, ["html"]);
  // In each scheme; that a page fails at the width of a phone alone, the test of the
  // command line above shows, with the widths where it fails.
  assert.deepEqual(failing(findings, "widest.html", "reflow", 375), ["dark", "light"]);
});

// What scrolls sideways on a phone, as Material builds it: a table in the frame that
// its script puts around it, without a link or anything else that takes the focus.
const FRAME = '<div class="md-typeset__scrollwrap" style="overflow-x: auto"><div class="md-typeset__table"><table style="width: 700px"><tr><th>Name</th></tr><tr><td>Value</td></tr></table></div></div>';
const SCRIPT = fileURLToPath(new URL("../mkdocs-blueprint.js", import.meta.url));

/** A page of Material's kind with a table in a frame, and the script of the website. */
function framed(body, script = '<script src="blueprint.js"></script>') {
  return styled(`<article class="md-typeset">${body}</article>${script}`);
}

test("the script of the website gives the focus to what scrolls sideways on a phone", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-frame-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  await copyFile(SCRIPT, path.join(built, "blueprint.js"));
  await writeFile(path.join(built, "bare.html"), framed(FRAME, ""));
  await writeFile(path.join(built, "table.html"), framed(FRAME));
  await writeFile(path.join(built, "code.html"), framed(`<pre><code style="display: block; overflow-x: auto">${WORD}</code></pre>`));
  // A fold is closed when the page loads, so nothing in it can scroll yet.
  await writeFile(path.join(built, "fold.html"), framed(`<details class="blueprint-fold"><summary>Fold</summary>${FRAME}</details>`));
  // At the width of a phone in each scheme, and of a desktop, where the table fits.
  const { findings } = await checkSite(browser, built, [], null, { browsers: [...ONE.browsers, ...PHONES.browsers] });

  const rule = "scrollable-region-focusable";
  // Without the script, the frame fails on a phone alone, where the table doesn't fit.
  assert.deepEqual(failing(findings, "bare.html", rule, 375), ["dark", "light"]);
  assert.deepEqual(failing(findings, "bare.html", rule), []);
  for (const page of ["table.html", "code.html", "fold.html"]) {
    assert.deepEqual(failing(findings, page, rule, 375), [], page);
  }
  // A frame that scrolls is no page that scrolls.
  assert.deepEqual(findings.filter((finding) => finding.rule === "reflow"), []);
});

test("a table takes the focus once a window turns too narrow for it, and not before", async (t) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const tab = await context.newPage();
  await tab.setContent(framed(FRAME, ""));
  await tab.addScriptTag({ path: SCRIPT });
  await tab.evaluate(() => {
    window.dispatchEvent(new Event("load"));
  });
  const frame = tab.locator(".md-typeset__scrollwrap");
  const frames = () => tab.evaluate(async () => {
    for (let each = 0; each < 3; each++) {
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
  });

  await frames();
  assert.equal(await frame.getAttribute("tabindex"), null);
  await tab.setViewportSize({ width: 375, height: 812 });
  await frames();
  assert.equal(await frame.getAttribute("tabindex"), "0");
});

test("the layout of a phone gets its own violations, with the width where they fail", async (t) => {
  const repo = await repository(t);
  await writeFile(path.join(repo.built, "narrow.html"), styled(
    "<p>Too faint on a phone.</p>",
    "@media (max-width: 45em) { p { color: #eee; } }",
  ));
  const { status, lines } = await run(repo, [repo.built, "narrow.html"], { every: true });

  assert.equal(status, 1);
  assert.match(lines[0], /color-contrast on narrow\.html: .*: 1 element\(s\) in light and dark at 375 px, `p`/);
  assert.doesNotMatch(lines[0], /1280/);
  assert.match(lines.at(-1), /on 1 page\(s\) in the light and the dark scheme, at 1280 and 375 px wide\.$/);
});

test("the command line runs the check when node starts the file", async () => {
  const check = fileURLToPath(new URL("./check.mjs", import.meta.url));
  await assert.rejects(promisify(execFile)(process.execPath, [check]), (error) => {
    assert.equal(error.code, 2);
    assert.match(error.stderr, /^Usage: /);
    return true;
  });
});

/** A page that leads to another address at once, as a page of an old address does: by
 * its refresh, or by its script, which takes the query and the fragment along. */
function moved(target, { script = false, lang = "en" } = {}) {
  const leads = script
    ? `<script>location.replace(${JSON.stringify(target)} + location.search + location.hash);</script>`
    : `<meta http-equiv="refresh" content="0; url=${target}">`;
  const language = lang ? ` lang="${lang}"` : "";
  return `<!doctype html><html${language}><head><meta charset="utf-8"><title>This page has moved - Other</title>${leads}</head><body><main><p>This page has moved to <a href="${target}">the website of Other</a>.</p></main></body></html>`;
}

test("a page that leads to another address is checked as it shows, and the summary says where it leads", async (t) => {
  const repo = await repository(t);
  // Pages of another website at the same address, which this folder doesn't have, and
  // of another server.
  await writeFile(path.join(repo.built, "refresh.html"), moved("https://website.test/other/games.html"));
  await writeFile(path.join(repo.built, "script.html"), moved("other/index.html", { script: true }));
  await writeFile(path.join(repo.built, "away.html"), moved("https://other.test/page.html", { script: true }));
  // Without its language, the page itself fails, not the page where it leads.
  await writeFile(path.join(repo.built, "nolang.html"), moved("https://website.test/other/", { lang: "" }));
  const pages = ["refresh.html", "script.html", "away.html", "nolang.html"];
  const { status, lines, summary } = await run(repo, [repo.built, ...pages], { onRunner: true });

  assert.equal(status, 1);
  const annotations = lines.filter((line) => line.startsWith("::error "));
  assert.equal(annotations.length, 1, annotations.join("\n"));
  assert.match(annotations[0], /title=Accessibility%3A html-has-lang on nolang\.html::/);
  const leads = "It checked 4 page(s) that lead to another address, by a refresh or a script, as they show before they leave, and followed none: `away.html` to https://other.test/page.html, `nolang.html` to https://website.test/other/, `refresh.html` to https://website.test/other/games.html and 1 more.";
  assert.ok(lines.includes(leads), lines.join("\n"));
  assert.ok(summary.includes(`\n${leads}\n`), summary);
  // Where a page leads is no server that it asks.
  assert.doesNotMatch(summary, /asked other servers/);

  const { findings, redirects } = await checkSite(browser, repo.built, ["script.html"], null, ONE);
  assert.deepEqual(findings.filter((finding) => finding.impact === "serious" || finding.impact === "critical"), []);
  assert.deepEqual(redirects, [{ page: "script.html", target: "https://website.test/other/index.html" }]);
  const one = await run(repo, [repo.built, "refresh.html"]);
  assert.equal(one.status, 0);
  assert.ok(one.lines.includes("It checked 1 page(s) that lead to another address, by a refresh or a script, as they show before they leave, and followed none: `refresh.html` to https://website.test/other/games.html."));
});

test("a frame of a page loads its own page, which the page doesn't leave for", async (t) => {
  const built = await mkdtemp(path.join(tmpdir(), "a11y-frames-"));
  t.after(() => rm(built, { recursive: true, force: true }));
  await writeFile(path.join(built, "framed.html"), styled('<iframe title="Faint" src="faint.html"></iframe>'));
  await writeFile(path.join(built, "faint.html"), faint());
  const { findings, redirects } = await checkSite(browser, built, ["framed.html"], null, ONE);

  assert.deepEqual(failing(findings, "framed.html", "color-contrast"), ["light"]);
  assert.deepEqual(redirects, []);
});

suite("the accessibility check", { concurrency: CONCURRENCY }, () => {
  for (const { name, fn } of tests) {
    nodeTest(name, fn);
  }
});
