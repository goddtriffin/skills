# Manifest standards

Where every upgraded setting lives, per repo layout, and why. `bump` applies the automatic parts;
the rest surface in `report --upgrade` for the user to approve.

## Layouts

`report` labels each repo with one of three layouts, from its root `Cargo.toml`:

| Layout | Root manifest has | Settings live in |
| --- | --- | --- |
| `single-crate` | `[package]` only | `[package]`, `[dependencies]` |
| `root-package-workspace` | `[workspace]` and `[package]` | `[workspace]`, `[workspace.package]`, `[workspace.dependencies]` |
| `virtual-workspace` | `[workspace]` only | same as above |

The skill handles all three and never converts one into another.

## Per setting

| Setting | Workspace | Single crate |
| --- | --- | --- |
| `edition` | `[workspace.package]`; members `edition.workspace = true` | `[package]` |
| `rust-version` | `[workspace.package]`; members `rust-version.workspace = true` | `[package]` |
| `resolver` | `[workspace] resolver = "N"`, always explicit; **never** on members | **never set** — the edition implies it |
| `version` | `[workspace.package]`; members `version.workspace = true` (lockstep) | `[package]` |
| dependencies | `[workspace.dependencies]`; members `name.workspace = true` | `[dependencies]` etc. |
| clippy `msrv` | **never set** — removed; a config file left empty is deleted | same |
| toolchain pin | `rust-toolchain.toml` numeric `channel` → full target toolchain | same |

**Why the resolver differs.** Cargo reads `resolver` only from the workspace root and ignores (with
a warning) any on a member. A virtual workspace has no package to infer it from, so it must be
explicit; a root-package workspace could infer it from the root package's edition, but explicit is
kept for consistency and so moving the root package later cannot silently drop it. A single crate
infers it from its edition, so an explicit one is only a way to fall behind — `bump` removes it.

**Why no clippy `msrv`.** Clippy falls back to the `rust-version` cargo passes it, inherited or
not, so `msrv` only restates `Cargo.toml` and can drift from it (clippy warns when they differ).
A clippy config that held nothing else is deleted, along with whatever referenced it.

**Toolchain pins.** Only numeric channels (`1.85`, `1.85.0`) are bumped; named channels (`stable`,
`nightly`, `nightly-YYYY-MM-DD`) are left alone. The skill never creates a pin.

## Requirements

- Every registry requirement is `M.m.p` with no operator — a caret requirement in Cargo terms, so
  it is a floor, not a pin; `Cargo.lock` is what pins the build.
- Bare `M` / `M.m` → rewritten by `bump` to the full version `Cargo.lock` resolved.
- `=M.m.p`, `~`, `>=`, `<`, `*`, compound ranges → reported, never rewritten automatically. An
  exact pin in a library breaks resolution for every downstream crate needing a different patch.
- `cargo upgrade` skips exact pins by default; it respects `rust-version`, which is why `bump`
  raises `rust-version` first.

## Library versions

- Only crates with a library target and `publish` not `false` are version-bumped. Binaries keep
  their version, except as a side effect of a lockstep workspace version.
- Breaking → minor; anything else → patch, at every major including ≥ 1.0 (see SKILL.md step 3e).
- **Independently versioned workspace** (members carry their own `version`): `report --upgrade` flags it; do not
  use `set-version` there. Bump each library crate's own manifest, following the repo's convention.

## Lints

Every repo carries the same lint table: the strictest settings short of `nursery`, with every
warning a hard error. `report --upgrade` does not check it; compare by hand and bring the repo onto
it as part of an upgrade.

| Layout | Lives in |
| --- | --- |
| workspace | `[workspace.lints.rust]`, `[workspace.lints.clippy]`, `[workspace.lints.cargo]`; every member `[lints] workspace = true` |
| single crate | `[lints.rust]`, `[lints.clippy]`, `[lints.cargo]` |

```toml
[workspace.lints.rust]
unsafe_code = { level = "forbid", priority = 0 }
unfulfilled_lint_expectations = { level = "forbid", priority = 1 }
unused = { level = "deny", priority = -1 }

[workspace.lints.clippy]
all = { level = "deny", priority = -1 }
correctness = { level = "deny", priority = -1 }
suspicious = { level = "deny", priority = -1 }
style = { level = "deny", priority = -1 }
complexity = { level = "deny", priority = -1 }
perf = { level = "deny", priority = -1 }
pedantic = { level = "deny", priority = -1 }
cargo = { level = "deny", priority = -1 }
nursery = { level = "allow", priority = 0 }
allow_attributes = { level = "forbid", priority = 1 }
multiple_crate_versions = { level = "allow", priority = 1 }

[workspace.lints.cargo]
correctness = { level = "deny", priority = -1 }
suspicious = { level = "deny", priority = -1 }
style = { level = "deny", priority = -1 }
pedantic = { level = "deny", priority = -1 }
```

- **Nothing looser.** Remove any other allow — a nursery lint allowed by name is already allowed.
- **Stricter additions stay.** A repo that also denies `restriction` lints (`unwrap_used`,
  `indexing_slicing`, …) keeps them after the standard keys.
- **`allow_attributes` forbid** turns every `#[allow]` into `#[expect(..., reason = "...")]` or a
  code fix; `unfulfilled_lint_expectations` forbid then catches each stale `#[expect]`.
- **`[lints.cargo]`** (stable since Rust 1.100) makes Cargo's own lints errors —
  `unused_dependencies`, `unused_workspace_dependencies`, `unused_workspace_package_fields`,
  `missing_lints_inheritance`, `redundant_homepage`; `pedantic` adds `non_kebab_case_bins` and
  `manual_readme`. Clippy's `-D warnings` never covered these. Fix an unused dependency by removing
  it, or moving it to the table it belongs in (e.g. `dev-dependencies`). For hidden candidates the
  lint skips, run once:
  `CARGO_LOG=cargo::diagnostics::rules::unused_dependencies=debug cargo check --workspace --all-targets --all-features`.
- **Makefile.** The `lint` target's clippy line is
  `cargo clippy --workspace --all-targets --all-features -- -D warnings`, and `fix` is the same
  with `--fix --allow-dirty --allow-staged`. Keep extra invocations that cover more (a feature
  matrix).
