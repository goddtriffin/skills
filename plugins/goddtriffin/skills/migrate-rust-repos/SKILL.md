---
name: migrate-rust-repos
description: Use when changing one Rust repo, or a directory of Rust repos, repo by repo in dependency order — upgrading to the latest dependency versions, Rust edition, rust-version (retiring duplicate clippy msrv), and Cargo resolver; swapping one crate for another across repos (e.g. chrono to jiff, xml-builder to quick-xml); or applying a refactor or convention fleet-wide (e.g. libraries re-exporting their dependencies) — including migrating code, publishing libraries before their dependents, and rolling out. Also use when asked for the upgrade state of Rust repos, which repos depend on a crate, or which order interdependent Rust repos must be changed in.
---

# Migrate Rust repos

## Overview

Apply one or more changes to Rust repos with **zero regressions**, then ship each repo the way that
repo ships. Pointed at a directory, work through every repo one at a time, **most-depended-on
first**, publishing each library before its dependents move onto it. The run ends with the fleet in
lockstep: every first-party dependent on the latest release of every first-party library.

**Changes.** A run applies exactly what the user asks for — never assume the other kind:

| Change | What | Owner |
| --- | --- | --- |
| **upgrade** | Latest toolchain, edition, `rust-version`, resolver, dependencies, Docker build image | `reference/upgrade.md` |
| **custom** | Anything the user describes: a crate swap, a refactor, a repo-wide convention. Each is pinned down by a confirmed spec | `reference/custom-change.md` |
| **follow upstream** | Implicit: a repo whose first-party library was released earlier in this run moves to that release and adapts — **even when it is a patch** | this file |

A run may combine several. Each change is its own commit; each repo still gets **one** version bump
and **one** release covering all of them.

**Division of labor.** `scripts/migrate_rust_repos.py` does everything deterministic — discovery,
the dependency graph, who uses which crate, target versions, manifest edits, dependency bumps,
changelog fetching. You do what needs judgment — specs, impact analysis, code migration, the fix
loop, version-bump level, rollout. Never spend tokens looking up something a subcommand answers.

**No run state.** Every subcommand is idempotent and reads the truth from the repos, the toolchain,
and crates.io. Specs are *input*, not progress. To resume, re-run `report`, apply each spec's done
check, look at open PRs, and continue. What none of that can detect (a Docker push already done, a
manual step the user took) lives in this session's context; if it is missing, ask the user.
Repeating a harmless step is an acceptable worst case.

## The script

Run with the system `python3` (3.9+, standard library only):
`python3 <this-skill-dir>/scripts/migrate_rust_repos.py <subcommand>`.

| Subcommand | Does |
| --- | --- |
| `preflight` | Checks `cargo`, `rustup`, `git`, `cargo-upgrade`; notes `gh`, `cargo-semver-checks`. |
| `report PATH [--upgrade] [--uses CRATE...] [--json]` | Discovers repos, builds the dependency graph and migration order, shows branch and dirty state. `--upgrade` adds every gap against the upgrade targets; `--uses` lists where each repo declares each crate directly. |
| `targets` | Upgrade only — `reference/upgrade.md`. |
| `changelogs PATH [--json]` | Upgrade only — `reference/upgrade.md`. |
| `bump REPO` | Upgrade only — `reference/upgrade.md`. |
| `follow REPO CRATE...` | Moves each first-party crate to its latest published version (`cargo upgrade -p CRATE@latest` + `cargo update -p`); fails if one is held back. |
| `set-version REPO patch\|minor` | Bumps a library's lockstep version (`[workspace.package]` or `[package]`). |
| `wait-published CRATE VERSION` | Blocks until the crates.io index serves that version. |

`PATH` is a single repo (it has a root `Cargo.toml`) or a directory whose immediate subdirectories
are git repos with a root `Cargo.toml`. Put `PATH` before `--uses`.

If `preflight` reports a required tool missing, stop and give the user the install command it
prints. `gh` is needed for PRs, the default way changes land; without it, ask the user how each
repo's changes should land.

## Procedure

### 1. Preflight

Run `preflight`. If the run includes an upgrade, also run `targets` (`reference/upgrade.md`).

### 2. Plan — one grill session, before touching anything

**Research first**, so the questions are informed:

- Run `report PATH`, adding `--upgrade` if upgrading and `--uses CRATE...` for every crate a custom
  change adds or removes.
- **Order.** Tier 0 repos depend on no other repo here. A cycle stops the run — show it and ask how
  to break it. A `WARNING` about a crate name provided by several repos means that edge was
  dropped; ask which repo is the real provider.
- **Each custom change:** draft its spec and classify every repo (`reference/custom-change.md`).
- **Upgrade:** collect the decisions `reference/upgrade.md` lists.
- **Status per repo:** **direct** (a change applies to it), **follows upstream** (depends,
  directly or transitively, on a first-party library that will be released this run), or
  **unaffected** (skipped). Every repo is checked; none is assumed.
- **Landing per repo:** a PR, unless the repo explicitly documents committing to the default branch.
  If a repo's convention is unclear, it is a question for the session.
- **Rollout per repo:** its own documented procedure, otherwise the fallback in step 3h. Name every
  irreversible action the run will take.

**Then grill.** Invoke `mattpocock:grill-me` with the draft plan. If it is not installed, interview
the user yourself: one question at a time, each with your recommended answer, and answer from the
repos whatever they can answer. Cover, in order:

1. **Scope** — which changes, which repos, and each repo's change order: upgrade first, then follow
   upstream, then custom changes in the order the user gave (unless one depends on another).
2. **Each custom-change spec**, until every rule and invariant is settled.
3. **Status per repo**, with the reason. For a change that is not mechanically detectable,
   summarize your analysis of each potentially affected repo; the user confirms, denies, or
   annotates each.
4. **Upgrade decisions.**
5. **Landing and rollout**, including every irreversible action.

The outcome is one confirmed plan with every spec saved. From here the run asks nothing except
real pauses and genuinely new decisions. If upgrading a directory, prefetch changelogs now.

### 3. Per repo, in migration order

Skip unaffected repos. Finish one repo completely — shipped — before starting the next.

#### a. Load the repo's own standards

Read `CLAUDE.md` / `AGENTS.md` and invoke any repo skill that governs changing or shipping code
(e.g. a contribution guide or a rollout skill); read the `Makefile` targets. **The repo's rules
override this skill's defaults** wherever they conflict — gates, commit style, branch, rollout.

#### b. Preconditions

- Work tree clean. If dirty, **pause** — never stash or discard someone else's work.
- On the default branch (report shows both). On a feature branch, **pause** and ask.
- `git pull` the default branch. If the repo lands through PRs, create a branch for this run.

#### c. Baseline gate

Run the repo's green gate on the untouched tree — its documented gate, else `make lint test` if
both targets exist, else `cargo fmt --check`, `cargo clippy --all-targets --all-features -- -D
warnings`, `cargo test --all-features`. Record the passing test count per test binary (the
`test result: ok. N passed` lines).

**Red baseline:** this repo was already failing before any change. Offer to fix it first. Proceed
only if the fix is small and clearly correct; if it is complex, ambiguous, or touches behavior,
**pause** and hand it to the user. A baseline fix is its own commit, separate from the changes,
landed before they start. Then re-run the baseline.

#### d. Each change, in the repo's change order

For each change: research → apply → fix loop → commit. The gate is green after every commit.

| Change | Research | Apply |
| --- | --- | --- |
| upgrade | `reference/upgrade.md` | `reference/upgrade.md` |
| follow upstream | none — the upstream's commits and PR from earlier in this run say what changed | `follow REPO CRATE...` for every first-party crate released this run that this repo depends on directly, then adapt the code. An upgrade's `bump` already covers this; skip it then. |
| custom | `reference/custom-change.md` | per the spec |

If `follow` reports a crate held back because this repo's `rust-version` is older than the
upstream's, **pause** — raising it is an upgrade decision for the user.

**Fix loop** — loop the green gate until it passes:

- **Fix root causes.** Never `#[allow]`/`#[expect]` a new lint, loosen or delete a test, add
  `#[ignore]`, or pin a dependency back to dodge a migration.
- **Same tests, not fewer.** The passing count per test binary must be ≥ the baseline. A drop
  means tests silently stopped compiling in (a feature or `cfg` change) — find out why.
- **Behavior changes need a human.** If a fix changes behavior a user could observe beyond what the
  change's spec or the upgrade intends, **pause** and ask.
- **No iteration cap** — but when you stop making progress, **pause** (see *Pausing*).
- If the repo documents a smoke test (e.g. run the container and exercise it), it is part of the
  gate.

**New decisions.** When a change raises a question the plan did not settle, stop and invoke
`mattpocock:grill-me` for just that question. Record the answer in the spec; it binds every
remaining repo.

**Commit** — one commit per change, in the repo's commit style. The message says what changed and
why; `reference/upgrade.md` and `reference/custom-change.md` say what their messages must list.

#### e. Library version

Only publishable library crates get a version bump; binaries keep their version. Decide the level
from **all** of this repo's changes together — the highest one wins:

| Change | Bump |
| --- | --- |
| Breaking — the library's public API changed, it exposes types from a dependency that had a breaking bump, or a migration changed public behavior | **minor** (`x.Y+1.0`) |
| Anything else that changes what ships — toolchain, edition, resolver, internal-only dependency changes, additive API | **patch** (`x.y.Z+1`) |
| Nothing that ships changed — only CI, Makefile, docs not packaged in the crate | **none** — no release, and dependents do not follow |

This applies at every version, including ≥ 1.0 — it is this skill's convention, not semver's. A
README that is the crate's `readme` ships (crates.io and docs.rs render it). If
`cargo-semver-checks` is installed, run it against the last published version to confirm the call.
State the level and the reason, then run `set-version REPO <level>` and commit it. In a lockstep
workspace this moves every crate, binaries included — that is the repo's convention. In a workspace
`report --upgrade` flags as independently versioned, skip `set-version` and bump each library
crate's own manifest by hand.

#### f. Land

**Default: PRs.** Commit directly to the default branch only when the repo explicitly documents
that it does.

- **Group commits by review size.** Small changes share one PR, one commit per change. A large
  change gets its own PR. The version-bump commit goes in the last PR to merge. Say how you split
  them and why.
- Push, open the PR(s) with `gh pr create` following any PR template, and watch the checks.
- **Wait for the merge.** A library must be merged before it is tagged and published, and
  dependents cannot start until then — do not start another repo meanwhile. Tell the user what is
  ready to merge, watch with `gh pr view` / `gh pr checks`, and continue once it merges; then
  `git pull` the default branch.
- If the repo merges by squash, that convention wins; the separate commits still serve review.

#### g. Rollout

Follow the repo's own procedure exactly when it has one. Otherwise, the fallback:

- **Library:** dry-run publish (`make publish_dry_run` if present, else `cargo publish --dry-run`
  per crate) on the merged default branch, tag `vX.Y.Z` and push the tag, `cargo publish` each
  publishable crate in dependency order, then `wait-published CRATE VERSION` for each before any
  dependent repo starts.
- **Binary:** stop at merged. Ask whether anything else ships it (an image push, a deploy); never
  invent deploy steps.

**Irreversible actions** — `cargo publish`, pushing a tag, pushing an image, deploying, committing
straight to a default branch — need the user's confirmation the first time each kind occurs in a
run; later occurrences of the same kind proceed. A repo's own documented procedure overrides this.

### 4. Finish

Summarize per repo: each change and what it migrated, version published, PRs and rollout done,
repos skipped as unaffected, and anything left for the user (declined recommendations, open pauses,
PRs awaiting merge).

## Pausing

Pause whenever something needs a human: a dirty tree, a feature branch, a red baseline too complex
to fix, a behavior change, a migration you cannot complete, a held-back first-party crate, a failed
publish, a missing tool. Say:

1. **What happened** — the failing command and the relevant output.
2. **What you tried.**
3. **What the user must do** — exact commands or edits, if known.

Then stop. When the user says continue, re-run `report` on the same path (with the same flags),
apply each spec's done check, check open PRs, confirm their fix took, and resume from the first
repo that is not finished.

## Rules

- **Only what was asked.** An upgrade never rides along with a custom change, nor the reverse. The
  one implicit change is follow upstream, and it is the lockstep the user wants.
- **Requirements are `M.m.p`.** Full `major.minor.patch`, no operator — including any dependency a
  change adds. Other forms are the user's call (`reference/upgrade.md`).
- **Settings live at the workspace level** and members inherit them, including any dependency a
  change adds. Where each one goes, per layout: `reference/manifest-standards.md`.
- **Pre-releases are never targets.** Latest means latest stable.
- **Git and path dependencies are not bumped** — the report lists them. A first-party library
  consumed by path within the same repo moves with that repo.
- **Rust repos only.** Discovery skips repos without a root `Cargo.toml`; say which were skipped.
  Within a Rust repo, every file is in scope for a custom change — CI, Dockerfiles, Makefiles, docs.
