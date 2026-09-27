# Upgrade

The **upgrade** change: bring a repo to the latest of everything — dependencies, edition,
`rust-version`, resolver, Docker build image. SKILL.md owns the loop around it; this file owns what
is specific to upgrading.

## Contents

- [Targets](#targets)
- [Plan decisions](#plan-decisions)
- [Research](#research)
- [Apply](#apply)
- [Commit message](#commit-message)
- [Rules](#rules)

## Targets

| Subcommand | Does |
| --- | --- |
| `targets` | `rustup update stable`, then derives the latest toolchain, `rust-version`, edition, and resolver from cargo itself — nothing is hardcoded. |
| `changelogs PATH [--json]` | For every direct-dependency bump, fetches the changelog covering **every** version in the range. Cached. |
| `bump REPO` | Toolchain pin and clippy `msrv` removal → `rust-version`/resolver → `cargo fix --edition` → edition → `cargo upgrade --incompatible` → `cargo update` → bare requirements normalized to `M.m.p`. |

Run `targets` once, in preflight. Keep the values in context for the whole run so every repo lands
on the same toolchain even if a release ships mid-run; if you ever re-run `targets`, check the
values did not move, and ask the user if they did.

## Plan decisions

`report PATH --upgrade` lists, per repo, every gap against the targets, stale first-party edges (a
consumer several versions behind its upstream library), and these items for the grill session:

- **Non-`M.m.p` requirements** (`=`, `~`, `>=`, `*`, ranges). Never changed automatically.
  Recommend plain `M.m.p` if nothing breaks; look for why the pin exists first (a comment, a
  companion crate that must match, git blame) and say what you found. Change only on approval.
- **Settings not inherited from the workspace** — member `edition`/`rust-version`/`version` or
  inline dependencies. Recommend moving them to the workspace level (`manifest-standards.md`).
  `bump` converts member `edition`/`rust-version` automatically; dependencies and versions move
  only on approval.
- **Independently versioned workspace** — say so; that repo's convention wins.
- **Doc MSRV mentions** — README badges or text restating the Rust version. The report lists
  candidates; confirm each is a real MSRV statement, then recommend deleting it (`Cargo.toml` is the
  single source). Delete only on approval.

In directory mode, once the plan is confirmed, run `changelogs PATH` once to prefetch every
changelog the run will need.

## Research

Run `changelogs REPO`. For each dependency it lists, the changelog source files are local. Follow
`changelog-research.md`: one subagent per **breaking** bump, one subagent covering all
**compatible** bumps together. Each writes a per-version digest into the shared cache (reused by
every later repo and run) and returns this repo's impact list: what breaks, where (file:line), and
the fix. Where a dependency says `changelog not found`, research it manually from its repository.

For a first-party upstream library released earlier in this run, you already know its changes —
use them directly.

## Apply

Run `bump REPO`. It is safe to re-run. If `cargo fix --edition` fails, the pre-upgrade code does not
compile under migration — fix it and re-run. Then:

- **Dockerfiles** — `report --upgrade` lists every `rust:<version>` image not already on the target
  toolchain. Update each to the target toolchain, keeping the suffix (`-slim`, `-alpine3.NN`, …),
  and verify that exact tag exists on Docker Hub before relying on it; if the old suffix has no
  build for the new toolchain, pick the nearest one that does and say so.
- **Clippy config** — `bump` removes `msrv` (it duplicates `rust-version`) and deletes a
  `clippy.toml`/`.clippy.toml` left with nothing else. Remove every reference `bump` prints as
  `STILL REFERENCES` — a Dockerfile `COPY` of a deleted file fails the image build; a Cargo
  `include` entry is stale.
- **Approved plan decisions** — requirement rewrites, moves to the workspace level, doc deletions.

Then apply the impact list and run the fix loop. New clippy lints from the new toolchain are fixed
in code, never allowed.

## Commit message

Lists the toolchain/edition moves and the breaking dependency bumps, with a line each on what
migrated.

## Rules

- **`bump` rewrites bare `M` and `M.m`** to the full locked version automatically; every other
  non-`M.m.p` form is the user's call (above).
- **Direct dependencies get changelog research; transitive ones do not.** `cargo update` moves them
  within compatible ranges and the gate is their backstop.
- **Only the Rust toolchain and crates.** Other ecosystems in the repo (JS, the runtime OS image)
  are out of scope for an upgrade — a custom change can cover them.
