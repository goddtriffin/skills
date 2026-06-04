# goddtriffin-skills

Todd Griffin's personal Claude Code plugin marketplace.

## Adding the marketplace

```
/plugin marketplace add /Users/toddgriffin/Documents/code/skills
```

(or, once pushed to GitHub, `/plugin marketplace add <owner>/<repo>`)

Then install a plugin:

```
/plugin install mattpocock@goddtriffin-skills
```

## Plugins

| Plugin | Skills | Description |
| --- | --- | --- |
| `mattpocock` | `grill-me` | Skills from [Matt Pocock](https://github.com/mattpocock). `grill-me` relentlessly interviews you about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Triggers on "grill me" or wanting a plan stress-tested. |

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
