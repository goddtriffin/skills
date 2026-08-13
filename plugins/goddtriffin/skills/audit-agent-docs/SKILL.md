---
name: audit-agent-docs
description: Use when reviewing, refactoring, or standardizing a repo's agent-facing documentation — CLAUDE.md, README.md, vendored Claude skills (SKILL.md and reference files), or a skill-index table — or when deciding whether a skill has grown too broad and should be split.
---

# Audit Agent Docs

## Overview

Grade a repo's agent-facing documentation against a fixed standard and emit a **scorecard** of what
passes and what fails, with terse, insightful fix advice for each failure. This skill defines the
canonical shape of those files; it does not prescribe a workflow for fixing them — the user brings
their own.

**Report first, fix on request.** The scorecard is always emitted first, no matter what. Never
refactor before reporting.

## When to Use

- Reviewing or standardizing `CLAUDE.md`, `README.md`, or vendored skills in a repo.
- Deciding whether a skill has grown too broad and should be split.
- Before or during a docs/skills refactor, to know exactly what fails the standard.

## Invocation Behavior

1. **Determine scope.**
   - Default: the **entire repo** — discover every in-scope file (see below).
   - If the user names specific files, audit those.
   - If the user restricts to a subset, audit only that subset.
2. **Emit the scorecard first**, always, before touching anything.
3. **Fix only after a go-ahead.** If the user grants it at invocation ("audit and fix"), still emit
   the full scorecard first, then apply fixes immediately after. Absent a go-ahead, stop at the
   scorecard.
4. When fixing, obey **zero knowledge lost** (see cross-cutting principles): every removal or move
   names where the knowledge now lives.

## In-Scope Files

Discover from the repo root:
- `CLAUDE.md`, `README.md`
- Root `.claude/skills/*/SKILL.md` and their `reference/*.md` files
- Any skill-index table inside `CLAUDE.md` / `README.md`

## The Rubric

Load the relevant reference for the detailed checks, thresholds, and exact verification commands:

- **Skill artifacts** — `SKILL.md` frontmatter + body, `reference/*.md`, and the split heuristic:
  see `reference/skill-standards.md`.
- **Entry-point docs** — `CLAUDE.md`, `README.md`, and the skill-index table:
  see `reference/entry-doc-standards.md`.
- **Cross-cutting principles** — single-source-of-truth, no-duplication, docs-earn-their-place, and
  zero-knowledge-lost: see `reference/cross-cutting-principles.md`.

### Checklist (every check, at a glance)

Every threshold below is a **hard FAIL** when exceeded. Run the exact commands from the reference
files rather than eyeballing counts.

**SKILL.md**
- `name` present; letters/numbers/hyphens only
- `description` present; ≤ 1024 chars; third-person "Use when…"; triggers only (no workflow summary)
- Body < 500 lines

**reference/*.md**
- TOC present once the file exceeds 100 lines (no line ceiling otherwise)

**Split heuristic** (recommend a split when either holds; line count never forces one)
- Description has multiple unrelated triggers, OR
- Body contains distinct standalone workflows

**CLAUDE.md**
- ~100 lines (≤ 100)
- Reference-heavy; does not restate knowledge a skill owns

**README.md**
- Succinct human entry point; shares the skill-index table

**Skill-index table** (N/A if repo has zero vendored skills)
- Exists in CLAUDE.md and README
- Columns: name + trigger
- One row per vendored skill; same set synced across both files

**Cross-cutting**
- Single source of truth: one owner per fact
- No duplication across files
- Docs earn their place (insight, not restatement)
- Zero knowledge lost: every fix names the knowledge's new home

## Scorecard Format

List each in-scope file one by one. No top-level summary.

- Per file: a header stating the file path and an overall **PASS** or **FAIL**.
- Under it: one sub-bullet per applicable check, each marked **PASS** or **FAIL**. Every FAIL is
  followed by terse, insightful fix advice. Mark inapplicable checks **N/A**.
- Prose/list form — not a literal table — so fix advice has room.

Then a trailing **Cross-cutting** section for findings that span files: skill-index drift,
duplication / single-source-of-truth violations, and split recommendations.

Example shape:

```
### .claude/skills/foo/SKILL.md — FAIL
- PASS  name: valid
- FAIL  description is 1180 chars → cut the workflow summary; keep triggers only
- FAIL  body is 612 lines → extract the API reference into reference/api.md

### CLAUDE.md — PASS
- PASS  all checks

## Cross-cutting
- FAIL  skill-index table drift: README lists `bar`, CLAUDE.md does not → reconcile both to the same set
- Split recommended for `foo`: description mixes onboarding + migrations (unrelated triggers) →
  propose `onboarding` and `migrations`; move shared setup to a reference file, do not duplicate
```
