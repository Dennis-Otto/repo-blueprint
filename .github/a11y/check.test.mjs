// The tests of the accessibility check, on a small website that the test writes: a
// palette with and without the media of the system, a toggle that does nothing, a
// website with one scheme, and a page of a further language without a translation.
//
//   npm ci --prefix .github/a11y --ignore-scripts
//   node --test .github/a11y/check.test.mjs
//
// https://github.com/Dennis-Otto/repo-blueprint

import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import { checkSite, escaped, launch, sourceOf } from "./check.mjs";

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
