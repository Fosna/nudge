---
name: audit-loop
description: Run an audit loop on this repo — identify, categorize, prioritize, deep dive, fix, repeat — tracked in an AUDIT-<topic>.md report. Use when the user asks to audit, scan, or sweep the repo for a class of problem (inconsistencies, bugs, security, stale docs, test gaps), or to continue an existing AUDIT-*.md.
---

# audit-loop

A gated loop. The user steers every batch; you never fix ahead of a "go" and never commit
without a "yes". The loop runs until the user says stop.

## 1. Identify

Ask what to audit if the user hasn't named it (inconsistencies, bugs, security, …). Read
every tracked file the topic touches (`git ls-files`); don't sample. Run the test suite
once so the report starts from a known state.

Verify suspected bugs before reporting them: run the code, don't reason about it.

## 2. Categorize

Group findings by kind. For inconsistencies the categories that worked were: behaviour bugs,
wrong or stale docs, duplicated logic and hidden rules, test hygiene, cosmetic. Pick
categories that fit the topic.

## 3. Prioritize

Rate each item by user impact:

- **High:** wrong behaviour a user will run into.
- **Medium:** misleads people, or could hide failures.
- **Low:** wording, style or internal duplication.

Weigh likelihood honestly. If a deep dive shows an item is less severe than first rated,
say so and re-rate it.

## Report: `AUDIT-<topic>.md` in the repo root

Write it before any fix, and update it with every batch.

- Every item gets a stable `#N` and keeps it forever. Write items as bullets labelled
  `- **#N: title.**`, never as a Markdown ordered list, which renumbers.
- Counts are **fixed/found** (`6/6` means done). Use `—` where nothing was found, never `0/0`.
- Top of file: overall fixed/found, a category table (fixed/found, open, fixed, skipped),
  and a severity matrix (categories × High/Medium/Low, each cell fixed/found plus its
  items, ✓ for fixed, ⊘ for skipped).
- Each category section has its fixed/found in the heading, then **Open**, **Fixed**,
  **Skipped**. A fixed item says in a line or two what was wrong and what changed.
- **Skipped** means the user decided against it. Record the decision; it doesn't count as
  fixed.
- Refresh line references after each batch; fixes move them.

## 4. Deep dive

When the user asks about an item, explain: how it fails, a concrete failure scenario,
who actually hits it, and fix options with a recommendation. Don't change files during a
deep dive.

## 5. Fix

1. The user picks a batch (by `#N`, a category, or a severity).
2. Show the plan: per file, what changes and which tests are added or updated. Wait for "go".
3. Apply it. Every behaviour fix gets a test.
4. Run `python3 -m unittest test_nudge` and
   `python3 -W error::ResourceWarning -m unittest test_nudge`. Both must pass.
5. Fix docs the change made stale (README.md, CONTEXT.md, SKILL.md files) in the same batch.
6. Issues found along the way are fixed in the current batch without being added to the
   report.
7. Update the report.
8. Show the commit message, at most 30 words for subject plus body. Commit on "yes". Don't
   push.

Ask the user only when a choice is genuinely theirs: it changes behaviour users rely on,
removes a feature, or the trade-off has no clear winner. Otherwise pick, say what you
picked, and carry on.

## 6. Repeat

After each commit: report fixed/found and what's still open, highest severity first, and
suggest the next batch. Continue until the user says stop.

## Rules learned in this repo

- Don't write counts of things into docs ("four artifacts", "53 tests"). They go stale.
  Point to the source instead (a command, the list itself).
- `CONTEXT.md` is the handoff doc for future sessions. Keep its "verified" and
  "unverified" lists true.
- Code and its comments use ASCII `--`; the Markdown docs use `—`.
