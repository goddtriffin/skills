# goddtriffin-skills

Todd Griffin's personal Claude Code plugin marketplace.

## Install

```
/plugin marketplace add goddtriffin/skills
/plugin install goddtriffin@goddtriffin-skills
/plugin install mattpocock@goddtriffin-skills
```

## Plugin: `goddtriffin`

Skills written by Todd Griffin.

| Skill              | Trigger                                                                                                                                                                                                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `audit-agent-docs` | Reviewing, refactoring, or standardizing a repo's agent-facing docs — `CLAUDE.md`, `README.md`, vendored skills, skill-index tables — or deciding whether a skill has grown too broad to stay one skill. Emits a pass/fail scorecard before changing anything.       |
| `mock-design`      | Writing, reviewing, or refactoring a reusable mock implementation of a dependency-injected interface/trait, or deciding how a mock seeds responses, records calls, and verifies seeded responses were consumed. Language-agnostic rules with per-language mechanics. |
| `migrate-rust-repos` | Changing one Rust repo, or a directory of them, repo by repo in dependency order — upgrading to the latest dependencies, edition, `rust-version`, and resolver (retiring duplicate clippy `msrv`), swapping one crate for another (e.g. `chrono` → `jiff`), or applying a refactor or convention fleet-wide — with migration, publishing, and rollout; or reporting upgrade state, crate usage, and change order. |

## Plugin: `mattpocock`

Skills originally authored by [Matt Pocock](https://github.com/mattpocock); this
repo packages them as a Claude Code plugin.

| Skill      | Trigger                                                                                                   |
| ---------- | --------------------------------------------------------------------------------------------------------- |
| `grill-me` | Stress-testing a plan or design by being interviewed until every branch of the decision tree is resolved. |
