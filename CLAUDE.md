# CLAUDE.md

Todd Griffin's personal Claude Code plugin marketplace. This repo *contains* skills; it is not a
codebase they operate on. There is no build, no test suite, and no runtime.

## Structure

- `.claude-plugin/marketplace.json` — the marketplace manifest; every plugin gets an entry.
- `plugins/<author>/.claude-plugin/plugin.json` — one plugin per skill author.
- `plugins/<author>/skills/<skill>/SKILL.md` — the skill; `reference/*.md` beside it loads on demand.

## Skill index

| Skill | Plugin | Trigger |
| --- | --- | --- |
| `audit-agent-docs` | `goddtriffin` | Reviewing, refactoring, or standardizing a repo's agent-facing docs — `CLAUDE.md`, `README.md`, vendored skills, skill-index tables — or deciding whether a skill has grown too broad to stay one skill. |
| `mock-design` | `goddtriffin` | Writing, reviewing, or refactoring a reusable mock implementation of a dependency-injected interface/trait, or deciding how a mock seeds responses, records calls, and verifies seeded responses were consumed. |
| `migrate-rust-repos` | `goddtriffin` | Changing one Rust repo, or a directory of them, repo by repo in dependency order — upgrading to the latest dependencies, edition, `rust-version`, and resolver (retiring duplicate clippy `msrv`), swapping one crate for another (e.g. `chrono` → `jiff`), or applying a refactor or convention fleet-wide — with migration, publishing, and rollout; or reporting upgrade state, crate usage, and change order. |
| `grill-me` | `mattpocock` | Stress-testing a plan or design by being interviewed until every branch of the decision tree is resolved. |

## Working in this repo

- Skills are the single source of truth for their own subject matter. This file routes; it does not
  restate what a skill owns.
- `audit-agent-docs` defines the standard every skill here is held to — including its own. Run it
  before adding or reshaping a skill.
- Adding a skill touches four places: the skill directory, the plugin's `plugin.json`, this file's
  skill index, and the owning plugin's table in the README. Both must list it.
- The README groups skills under their plugin; this index is flat and covers every plugin at once.
- Skills vendored from another author keep attribution in the README and in the plugin description.
