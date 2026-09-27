---
name: upgrade-rust-repos
description: Use when upgrading one Rust repo, or a directory of Rust repos, to the latest dependency versions, Rust edition, rust-version (retiring duplicate clippy msrv), and Cargo resolver — including researching changelog impact, migrating code, and publishing/rolling out in dependency order. Also use when asked for the upgrade state of Rust repos, or which order interdependent Rust repos must be upgraded in.
---

# Upgrade Rust repos

## Overview

Bring Rust repos to the latest of everything — dependencies, edition, `rust-version`, resolver,
Docker build image — with **zero regressions**, then ship each repo the way that
repo ships. Pointed at a directory, upgrade every repo in it one at a time, **most-depended-on
first**, publishing each library before its dependents upgrade onto it.

**Division of labor.** `scripts/upgrade_rust_repos.py` does everything deterministic — discovery,
the dependency graph, target versions, manifest edits, dependency bumps, changelog fetching. You do
what needs judgment — impact analysis, code migration, the fix loop, version-bump level, rollout.
Never spend tokens looking up something a subcommand already answers.

**No run state.** Every subcommand is idempotent and reads the truth from the repos, the toolchain,
and crates.io. To resume after a pause, re-run `report` and continue. What a script cannot detect
(a Docker push already done, a manual step the user took) lives in this session's context; if it is
missing, ask the user. Repeating a harmless step is an acceptable worst case.

## The script

Run with the system `python3` (3.9+, standard library only):
`python3 <this-skill-dir>/scripts/upgrade_rust_repos.py <subcommand>`.

| Subcommand | Does |
| --- | --- |
| `preflight` | Checks `cargo`, `rustup`, `git`, `cargo-upgrade`; notes optional `gh`, `cargo-semver-checks`. |
| `targets` | `rustup update stable`, then derives the latest toolchain, `rust-version`, edition, and resolver from cargo itself — nothing is hardcoded. |
| `report PATH [--json]` | Discovers repos, builds the dependency graph and upgrade order, and lists every repo's gaps against the targets. |
| `changelogs PATH [--json]` | For every direct-dependency bump, fetches the changelog covering **every** version in the range. Cached. |
| `bump REPO` | Toolchain pin and clippy `msrv` removal → `rust-version`/resolver → `cargo fix --edition` → edition → `cargo upgrade --incompatible` → `cargo update` → bare requirements normalized to `M.m.p`. |
| `set-version REPO patch\|minor` | Bumps a library's lockstep version (`[workspace.package]` or `[package]`). |
| `wait-published CRATE VERSION` | Blocks until the crates.io index serves that version. |

`PATH` is a single repo (it has a root `Cargo.toml`) or a directory whose immediate subdirectories
are git repos with a root `Cargo.toml`.

If `preflight` reports a required tool missing, stop and give the user the install command it
prints (`cargo install cargo-edit` for `cargo-upgrade`). Recommend — never require — the optionals.

## Procedure

### 1. Preflight and targets

Run `preflight`, then `targets` once. Keep the target values in context for the whole run so every
repo lands on the same toolchain even if a release ships mid-run; if you ever re-run `targets`,
check the values did not move, and ask the user if they did.

### 2. Report and plan — show the user before touching anything

Run `report PATH`. Present:

- **Upgrade order and tiers.** Tier 0 repos depend on no other repo here. A cycle stops the run —
  show it and ask how to break it. A `WARNING` about a crate name provided by several repos means
  that edge was dropped; ask which repo is the real provider.
- **Per repo:** layout, branch, dirty state, and every finding — gaps against the targets, stale
  first-party edges (a consumer several versions behind its upstream library), and each item
  below that the user must decide:
  - **Non-`M.m.p` requirements** (`=`, `~`, `>=`, `*`, ranges). Never changed automatically.
    Recommend plain `M.m.p` if nothing breaks; look for why the pin exists first (a comment, a
    companion crate that must match, git blame) and say what you found. Change only on approval.
  - **Settings not inherited from the workspace** — member `edition`/`rust-version`/`version` or
    inline dependencies. Recommend moving them to the workspace level
    (`reference/manifest-standards.md`). `bump` converts member `edition`/`rust-version`
    automatically; dependencies and versions move only on approval.
  - **Independently versioned workspace** — say so; that repo's convention wins.
  - **Doc MSRV mentions** — README badges or text restating the Rust version. The report lists
    candidates; confirm each is a real MSRV statement, then recommend deleting it (`Cargo.toml` is
    the single source). Delete only on approval.
- **Rollout per repo** — the repo's own procedure if it documents one, otherwise the fallback in
  step 3i. Name every irreversible action the run will take.

Get the user's go-ahead on the plan. In directory mode, then run `changelogs PATH` once to prefetch
every changelog the run will need.

### 3. Per repo, in upgrade order

Finish one repo completely — shipped — before starting the next.

#### a. Load the repo's own standards

Read `CLAUDE.md` / `AGENTS.md` and invoke any repo skill that governs changing or shipping code
(e.g. a contribution guide or a rollout skill); read the `Makefile` targets. **The repo's rules
override this skill's defaults** wherever they conflict — gates, commit style, branch, rollout.

#### b. Preconditions

- Work tree clean. If dirty, **pause** — never stash or discard someone else's work.
- On the default branch (report shows both). On a feature branch, **pause** and ask.
- `git pull` the default branch.

#### c. Baseline gate

Run the repo's green gate on the untouched tree — its documented gate, else `make lint test` if
both targets exist, else `cargo fmt --check`, `cargo clippy --all-targets --all-features -- -D
warnings`, `cargo test --all-features`. Record the passing test count per test binary (the
`test result: ok. N passed` lines).

**Red baseline:** this repo was already failing before any change. Offer to fix it first. Proceed
only if the fix is small and clearly correct; if it is complex, ambiguous, or touches behavior,
**pause** and hand it to the user. A baseline fix is its own commit, separate from the upgrade,
landed before the upgrade starts. Then re-run the baseline.

#### d. Impact research

Run `changelogs REPO`. For each dependency it lists, the changelog source files are local. Follow
`reference/changelog-research.md`: one subagent per **breaking** bump, one subagent covering all
**compatible** bumps together. Each writes a per-version digest into the shared cache (reused by
every later repo and run) and returns this repo's impact list: what breaks, where (file:line), and
the fix. Where a dependency says `changelog not found`, research it manually from its repository.

For a first-party upstream library upgraded earlier in this run, you already know its changes —
use them directly.

#### e. Bump

Run `bump REPO`. It is safe to re-run. If `cargo fix --edition` fails, the pre-upgrade code does
not compile under migration — fix it and re-run. Then:

- **Dockerfiles** — `report` lists every `rust:<version>` image not already on the target
  toolchain. Update each to the target toolchain, keeping the suffix (`-slim`, `-alpine3.NN`, …),
  and verify that exact tag exists on Docker Hub before relying on it; if the old suffix has no
  build for the new toolchain, pick the nearest one that does and say so.
- **Clippy config** — `bump` removes `msrv` (it duplicates `rust-version`) and deletes a
  `clippy.toml`/`.clippy.toml` left with nothing else. Remove every reference `bump` prints as
  `STILL REFERENCES` — a Dockerfile `COPY` of a deleted file fails the image build; a Cargo
  `include` entry is stale.
- **Approved items** from step 2 — requirement rewrites, moves to the workspace level, doc
  deletions.

#### f. Migrate and fix loop

Apply the impact list, then loop the green gate until it passes. Rules for the loop:

- **Fix root causes.** Never `#[allow]`/`#[expect]` a new lint, loosen or delete a test, add
  `#[ignore]`, or pin a dependency back to dodge a migration. New clippy lints from the new
  toolchain are fixed in code.
- **Same tests, not fewer.** The passing count per test binary must be ≥ the baseline. A drop
  means tests silently stopped compiling in (a feature or `cfg` change) — find out why.
- **Behavior changes need a human.** If a fix changes behavior a user could observe beyond a pure
  API migration, **pause** and ask.
- **No iteration cap** — but when you stop making progress, **pause** (see *Pausing*).
- If the repo documents a smoke test (e.g. run the container and exercise it), it is part of the
  gate.

#### g. Library version

Only publishable library crates get a version bump; binaries keep their version. Decide the level:

| Change | Bump |
| --- | --- |
| Breaking — the library's public API changed, it exposes types from a dependency that had a breaking bump, or the edition migration changed public behavior | **minor** (`x.Y+1.0`) |
| Anything else — toolchain, edition, resolver, internal-only dependency changes | **patch** (`x.y.Z+1`) |

This applies at every version, including ≥ 1.0 — it is this skill's convention, not semver's. If
`cargo-semver-checks` is installed, run it against the last published version to confirm the call.
State the level and the reason, then run `set-version REPO <level>`. In a lockstep workspace this
moves every crate, binaries included — that is the repo's convention. In a workspace `report` flags
as independently versioned, skip `set-version` and bump each library crate's own manifest by hand.

#### h. Commit

One commit (or one PR, if the repo works through PRs) for the whole upgrade: toolchain, edition,
resolver, every dependency bump, and every code migration. Follow the repo's commit style. The
message lists the toolchain/edition moves and the breaking dependency bumps with a line each on
what migrated.

#### i. Rollout

Follow the repo's own procedure exactly when it has one. Otherwise, the fallback:

- **Library:** dry-run publish (`make publish_dry_run` if present, else `cargo publish --dry-run`
  per crate), push the commit, tag `vX.Y.Z` and push the tag, `cargo publish` each publishable
  crate in dependency order, then `wait-published CRATE VERSION` for each before any dependent
  repo starts.
- **Binary:** stop at committed and pushed. Ask whether anything else ships it (an image push, a
  deploy); never invent deploy steps.

**Irreversible actions** — `cargo publish`, pushing a tag, pushing an image, deploying — need the
user's confirmation the first time each kind occurs in a run; later occurrences of the same kind
proceed. A repo's own documented procedure overrides this.

### 4. Finish

Summarize per repo: old → new toolchain/edition/resolver, breaking bumps and what migrated,
version published, rollout done, and anything left for the user (declined recommendations, open
pauses).

## Pausing

Pause whenever something needs a human: a dirty tree, a feature branch, a red baseline too complex
to fix, a behavior change, a migration you cannot complete, a failed publish, a missing tool. Say:

1. **What happened** — the failing command and the relevant output.
2. **What you tried.**
3. **What the user must do** — exact commands or edits, if known.

Then stop. When the user says continue, re-run `report` on the same path, confirm their fix took,
and resume from the first repo that is not finished.

## Rules

- **Requirements are `M.m.p`.** Full `major.minor.patch`, no operator. `bump` rewrites bare `M` and
  `M.m` automatically; everything else is the user's call (step 2).
- **Settings live at the workspace level** and members inherit them. Where each one goes, per
  layout: `reference/manifest-standards.md`.
- **Direct dependencies get changelog research; transitive ones do not.** `cargo update` moves them
  within compatible ranges and the gate is their backstop.
- **Pre-releases are never targets.** Latest means latest stable.
- **Git and path dependencies are not bumped** — the report lists them. A first-party library
  consumed by path within the same repo moves with that repo.
- **Only the Rust toolchain and crates.** Other ecosystems in the repo (JS, the runtime OS image)
  are out of scope.
