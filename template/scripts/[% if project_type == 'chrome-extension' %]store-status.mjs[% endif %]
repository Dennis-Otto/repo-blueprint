// Decides what a run of the workflow Chrome Web Store, publish-store.yml, does, from
// the status of the item in the store and the release to deliver, and reports it: a
// table in the job summary with the published and the submitted version, the state of
// the review and the days it has taken, and for each problem an annotation that says
// what happened and what to do. No dependencies.
//
//   STATUS=status.json TAG=v1.2.3 node scripts/store-status.mjs
//
// It reads the answer of fetchStatus from the file STATUS, the tag from TAG, and
// EXPLICIT=true when the tag was given by hand. SUBMITTED_AT is when the submitted
// version went to the store, SUBMITTED_FROM says where that time comes from,
// "delivery" or "release", and DOCS is the page of the releases. It writes tag=<TAG>
// to GITHUB_OUTPUT when the release goes to the store, appends its report to
// GITHUB_STEP_SUMMARY and exits with 1 when a person has to act.
//
// The blueprint keeps this file current: https://github.com/Dennis-Otto/repo-blueprint
import { appendFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** A review that takes longer than this many days needs a person to look at it. */
export const MAX_REVIEW_DAYS = 7;

const DAY_MS = 24 * 60 * 60 * 1000;
const PUBLISHED = new Set(["PUBLISHED", "PUBLISHED_TO_TESTERS"]);

const isObject = (value) =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** A revision of the item: the version of its package and its state. */
const revision = (value) => {
  const status = isObject(value) ? value : {};
  const first = Array.isArray(status.distributionChannels)
    ? status.distributionChannels[0]
    : undefined;
  return {
    version:
      isObject(first) && typeof first.crxVersion === "string"
        ? first.crxVersion
        : undefined,
    state: typeof status.state === "string" ? status.state : undefined,
  };
};

/** Reads the answer of fetchStatus; a part that is missing counts as none. */
export const parseStatus = (answer) => {
  const item = isObject(answer) ? answer : {};
  return {
    published: revision(item.publishedItemRevisionStatus),
    submitted: revision(item.submittedItemRevisionStatus),
    takenDown: item.takenDown === true,
    warned: item.warned === true,
  };
};

/** Compares two versions of a manifest, numbers separated by dots: <0, 0 or >0. */
export const compareVersions = (a, b) => {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const difference = (left[i] ?? 0) - (right[i] ?? 0);
    if (difference !== 0) {
      return difference;
    }
  }
  return 0;
};

/** Decides whether the release goes to the store, and what the run reports. */
export const decide = ({ status, tag, explicit, submittedAt, now }) => {
  const version = tag.replace(/^v/, "");
  const { published, submitted } = status;
  const errors = [];
  const warnings = [];
  const notes = [];
  const pending = submitted.state === "PENDING_REVIEW";
  const daysInReview =
    pending && submittedAt
      ? Math.max(
          0,
          Math.floor((now.getTime() - submittedAt.getTime()) / DAY_MS),
        )
      : undefined;
  const result = (deliver) => ({
    deliver,
    daysInReview,
    errors,
    warnings,
    notes,
  });

  if (status.takenDown) {
    errors.push(
      "Google took the item down for a violation of its policies, and no version reaches the users until it is fixed. The Developer Dashboard says why: fix it there, or release the fix and start this workflow by hand with its tag, and ask for a new review.",
    );
    // The daily run leaves a taken-down item alone; a tag given by hand delivers its fix.
    if (!explicit) return result(false);
  }
  if (status.warned) {
    errors.push(
      "Google warned the item about a violation of its policies and takes it down unless it is fixed in time. The Developer Dashboard says what to fix and until when.",
    );
  }

  if (pending) {
    if (daysInReview !== undefined && daysInReview > MAX_REVIEW_DAYS) {
      errors.push(
        `The review of ${submitted.version ?? "the submission"} has taken ${daysInReview} days, longer than ${MAX_REVIEW_DAYS}. Look in the Developer Dashboard whether Google asks for anything, or ask the support of the Chrome Web Store.`,
      );
    }
    notes.push(
      submitted.version === version
        ? `${tag} is in review; Google publishes it after the review.`
        : `The store reviews ${submitted.version ?? "a submission"} and takes no new version until the review ends; the daily run delivers ${tag} after it.`,
    );
    return result(false);
  }

  if (published.version !== undefined) {
    const order = compareVersions(published.version, version);
    if (order === 0) {
      notes.push(`The store has ${tag} already; nothing to deliver.`);
      return result(false);
    }
    if (order > 0) {
      errors.push(
        `The store has ${published.version}, a higher version than ${tag}, and takes only a version higher than its own. Release a version above ${published.version}.`,
      );
      return result(false);
    }
  }

  if (submitted.version === version) {
    if (submitted.state === "STAGED" || PUBLISHED.has(submitted.state ?? "")) {
      notes.push(
        `The store has ${tag} already, in the state ${submitted.state}; nothing to deliver.`,
      );
      return result(false);
    }
    if (!explicit && submitted.state === "REJECTED") {
      errors.push(
        `Google rejected ${tag}. Its mail and the Developer Dashboard say why: fix the cause and release a new version, or, when only the listing or the privacy practices had to change, start this workflow by hand with the tag ${tag} to submit it again.`,
      );
      return result(false);
    }
    if (!explicit && submitted.state === "CANCELLED") {
      notes.push(
        `The submission of ${tag} was cancelled in the Developer Dashboard, and the daily run leaves it so; start this workflow by hand with the tag ${tag} to submit it again.`,
      );
      return result(false);
    }
  } else if (submitted.state === "REJECTED") {
    const earlier =
      submitted.version === undefined ? "" : ` ${submitted.version}`;
    warnings.push(
      `Google rejected the earlier submission${earlier}; ${tag} goes to the review now.`,
    );
  }

  notes.push(`The release ${tag} goes to the Chrome Web Store.`);
  return result(true);
};

const revisionText = (value) =>
  value.version === undefined
    ? "none"
    : `${value.version} (${value.state ?? "unknown"})`;

/** The report of a run for the job summary, in Markdown. */
export const summary = (input, decision, docs) => {
  const { status } = input;
  const standing = status.takenDown
    ? "taken down"
    : status.warned
      ? "warned"
      : "in good standing";
  let review = "no review pending";
  if (status.submitted.state === "PENDING_REVIEW") {
    review =
      decision.daysInReview === undefined
        ? "pending, since an unknown day"
        : `pending for ${decision.daysInReview} ${decision.daysInReview === 1 ? "day" : "days"}, since the ${input.submittedFrom === "delivery" ? "delivery" : "release"} on ${input.submittedAt.toISOString().slice(0, 10)}`;
  }
  const lines = [
    "### The Chrome Web Store",
    "",
    "| | |",
    "| --- | --- |",
    `| Release | ${input.tag} |`,
    `| Published | ${revisionText(status.published)} |`,
    `| Submitted | ${revisionText(status.submitted)} |`,
    `| Review | ${review} |`,
    `| Item | ${standing} |`,
    "",
    ...decision.errors.map((text) => `- **Problem:** ${text}`),
    ...decision.warnings.map((text) => `- **Warning:** ${text}`),
    ...decision.notes.map((text) => `- ${text}`),
  ];
  if (decision.errors.length > 0) {
    lines.push(`- How to fix a problem of the store: ${docs}#when-a-run-fails`);
  }
  return `${lines.join("\n")}\n`;
};

/** A message for a workflow command of GitHub Actions, which ends at a line break. */
export const escapeData = (text) =>
  text.replaceAll("%", "%25").replaceAll("\r", "%0D").replaceAll("\n", "%0A");

const required = (env, name) => {
  const value = env[name];
  if (!value) {
    throw new Error(`The variable ${name} is missing.`);
  }
  return value;
};

/** Runs the decision with the variables of the workflow; returns the exit code. */
export const run = (env, now = new Date(), log = console.log) => {
  const submittedAt = env.SUBMITTED_AT ? new Date(env.SUBMITTED_AT) : undefined;
  const from = env.SUBMITTED_FROM;
  const input = {
    status: parseStatus(
      JSON.parse(readFileSync(required(env, "STATUS"), "utf8")),
    ),
    tag: required(env, "TAG"),
    explicit: env.EXPLICIT === "true",
    submittedAt:
      submittedAt && !Number.isNaN(submittedAt.getTime())
        ? submittedAt
        : undefined,
    submittedFrom: from === "delivery" || from === "release" ? from : undefined,
    now,
  };
  const decision = decide(input);
  for (const text of decision.errors) {
    log(`::error title=Chrome Web Store::${escapeData(text)}`);
  }
  for (const text of decision.warnings) {
    log(`::warning title=Chrome Web Store::${escapeData(text)}`);
  }
  for (const text of decision.notes) {
    log(text);
  }
  appendFileSync(
    required(env, "GITHUB_STEP_SUMMARY"),
    summary(input, decision, env.DOCS ?? "docs/releases.md"),
  );
  if (decision.deliver) {
    appendFileSync(required(env, "GITHUB_OUTPUT"), `tag=${input.tag}\n`);
  }
  return decision.errors.length > 0 ? 1 : 0;
};

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  process.exitCode = run(process.env);
}
