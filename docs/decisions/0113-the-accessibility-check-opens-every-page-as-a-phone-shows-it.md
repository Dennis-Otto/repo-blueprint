# The accessibility check opens every page as a phone shows it

- Status: accepted
- Date: 2026-11-02

## Context

The check of [decision 0041](0041-every-website-is-accessible-and-quick-and-a-check-proves-it.md) opened every page at 1280 px wide. Nothing looked at the layout that CSS switches to on a narrow screen, and nothing measured whether a page scrolls sideways there, which WCAG 2.2 rules out in its criterion 1.4.10 Reflow. axe-core has no rule for that: it reads the page and doesn't scroll it.

`dennis-otto.github.io` found such a page by hand: the table of its Trust page scrolled sideways at 375 px. Its fix turns each row into a card on a narrow screen. A page that scrolls as a whole can come from any later change of CSS, of content or of the theme, with every check green, in any repository that uses the blueprint.

## Options

1. A second run at 375 px that only measures the width of each page. It takes a few seconds, but a page's layout for a phone keeps going unread, such as text in a card that is too faint in the dark scheme.
2. A second run at 375 px in one scheme, with axe-core and the measure. It takes half of what the next option takes, but what shows only on a phone goes unread in the other scheme, and the colors there differ most.
3. A second run at 375 px in both schemes, with axe-core and the measure.

## Decision

Option 3.

- **A window, not an emulated phone.** The check opens a browser of 375 by 812 px with no emulation of a phone. A phone that a page's `<meta name="viewport">` doesn't convince zooms out of a page that is too wide instead of showing it, and the width of a window can't hide anything that way.
- **The finding.** When `scrollWidth` of the root is larger than its `clientWidth`, the check adds a violation of the rule `reflow`, with the impact *serious*, a link to the explanation of the W3C, and the widest element that overflows. What stays in a frame of its own, or fixed on the screen, makes the page no wider and isn't named. A word that doesn't wrap leaves the box of its element behind, so the boxes of the text count too. An element that the check can't find, such as a pseudo-element, leaves the page as a whole to name.
- **The same rules as any violation.** It fails the check, shows as an annotation at the Markdown of the page and in the summary, and `.github/a11y-accepted.toml` accepts it with the rule `reflow`, its page and the reason. An entry accepts a rule on its page at both widths.
- **The script of every website comes with it.** The first run at 375 px found the same problem on every website with a wide table. On a phone, the frame that Material puts around a table scrolls, and the keyboard can't reach it (WCAG 2.1.1). `.github/mkdocs-blueprint.js` now gives that frame the focus, as it did for a block of code, once it scrolls: a `ResizeObserver` sees a phone that turns and a fold that opens, which a look at the load doesn't.
- **The limits rise.** A second width opens each page twice as often, so a run of every page takes about twice as long. The limit of the step rises from 15 to 30 minutes and that of the job from 20 to 35, about twice the slowest website, as [decision 0097](0097-a-pull-request-checks-the-accessibility-of-the-pages-that-it-changes-and-a-new-violation-fails.md) set them.

## Consequences

The run of every page on `main` and each week takes about twice as long, and each push to `main` waits that long before it publishes: 12 minutes 15 seconds on the blueprint, measured on a runner, where it took 5 minutes 32 seconds at one width, and about 15 minutes on homedarts, the slowest website. A pull request that changes one page takes about 10 seconds instead of 5, and one that changes no page still starts no browser. If that is too long, decision 0097 names the way out: the run of every page moves to a job of its own.

No repository turns red through the update. A sweep of all seven published websites at 375 px found no page that scrolls sideways, and the only finding that depends on the width is the frame of a table, which the script of the update fixes. A later page that scrolls sideways fails the pull request that brings it.

A check of the width is no check of the content: a table that scrolls in its frame passes, although a card may read better on a phone. So the table of that Trust page, which scrolled in its frame, would still pass if it came back: the check guards against a page that scrolls as a whole, and WCAG's exception for tables allows the frame.

The measure has two limits. 375 px is the width of a phone, as the issue asked for, and not the 320 px by which WCAG 1.4.10 measures a page enlarged to 400 %, so a page that overflows only between those two widths passes. And it measures what a page shows when it opens, with only the folds of the page of the automation open: what is too wide in another closed `<details>`, or in a content tab that isn't selected, goes unmeasured.
