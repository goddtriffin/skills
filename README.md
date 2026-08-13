# goddtriffin-skills

Todd Griffin's personal Claude Code plugin marketplace.

## Adding the marketplace

```
/plugin marketplace add goddtriffin/skills
```

Then install a plugin:

```
/plugin install mattpocock@goddtriffin-skills
```

## Plugins

| Plugin | Skills | Description |
| --- | --- | --- |
| `goddtriffin` | `audit-agent-docs` | Skills written by Todd Griffin. `audit-agent-docs` grades a repo's agent-facing documentation — `CLAUDE.md`, `README.md`, vendored skills, skill-index tables — against a fixed standard and emits a scorecard of what passes and fails. Triggers on reviewing or standardizing agent docs, or deciding whether a skill has grown too broad to stay one skill. |
| `mattpocock` | `grill-me` | Skills originally authored by [Matt Pocock](https://github.com/mattpocock). `grill-me` relentlessly interviews you about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Triggers on "grill me" or wanting a plan stress-tested. |

## Attribution

The `grill-me` skill was originally written by [Matt Pocock](https://github.com/mattpocock); this repo packages it as a Claude Code plugin.

## Structure

```
skills/
├── .claude-plugin/
│   └── marketplace.json             # Marketplace manifest (lists plugins)
└── plugins/                         # One plugin per skill author
    ├── goddtriffin/
    │   ├── .claude-plugin/
    │   │   └── plugin.json          # Plugin manifest
    │   └── skills/
    │       └── audit-agent-docs/
    │           ├── SKILL.md          # The skill itself
    │           └── reference/        # Loaded on demand, not up front
    │               ├── skill-standards.md
    │               ├── entry-doc-standards.md
    │               └── cross-cutting-principles.md
    └── mattpocock/
        ├── .claude-plugin/
        │   └── plugin.json
        └── skills/
            └── grill-me/
                └── SKILL.md
```
