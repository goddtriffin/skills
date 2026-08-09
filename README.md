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
| `mattpocock` | `grill-me` | Skills originally authored by [Matt Pocock](https://github.com/mattpocock). `grill-me` relentlessly interviews you about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Triggers on "grill me" or wanting a plan stress-tested. |

## Attribution

The `grill-me` skill was originally written by [Matt Pocock](https://github.com/mattpocock); this repo packages it as a Claude Code plugin.

## Structure

```
skills/
├── .claude-plugin/
│   └── marketplace.json         # Marketplace manifest (lists plugins)
└── plugins/
    └── mattpocock/              # Plugin (named after the skill's author)
        ├── .claude-plugin/
        │   └── plugin.json      # Plugin manifest
        └── skills/
            └── grill-me/
                └── SKILL.md     # The skill itself
```
