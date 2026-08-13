# Entry-Point Doc Standards

Rules for the thin entry points that route readers to the skills: `CLAUDE.md` (agent-facing),
`README.md` (human-facing), and the skill-index table shared by both.

## Principle: entry points are thin routers

`CLAUDE.md` and `README.md` are succinct entry points, not knowledge stores. Rules and knowledge
live in the vendored skills (the single source of truth). Entry points orient the reader and point
to the right skill — they do not restate skill content.

## CLAUDE.md

Loaded every turn and after every compaction, so every line costs.

| Check | Rule | How to verify |
|---|---|---|
| Length | ~100 lines | `wc -l < CLAUDE.md`; FAIL if > 100 |
| Reference-heavy | Points to skills/reference files rather than embedding rules | Read; FAIL if it restates knowledge that a skill already owns |
| No duplicated knowledge | Does not copy content that lives in a skill | Read; cross-check against skills |

Fix advice patterns:
- Over ~100 lines → move embedded rules/knowledge into the owning skill; leave a one-line pointer.
- Restates a skill → replace the prose with a pointer to that skill.

## README.md

Human mirror of CLAUDE.md — same routing, human framing.

| Check | Rule | How to verify |
|---|---|---|
| Entry-point role | Succinct human orientation, not a knowledge dump | Read |
| Shares the skill-index table | Same table as CLAUDE.md (see below) | Compare tables |

Fix advice patterns:
- Duplicates skill knowledge → replace with pointers, mirroring CLAUDE.md.

## Skill-index table

A table that lists every repo-vendored skill so a reader can route to the right one.

**Applicability:** required when the repo has ≥ 1 vendored skill. If the repo has zero vendored
skills, this check is **N/A** (state N/A, do not FAIL).

| Check | Rule | How to verify |
|---|---|---|
| Table exists | Present in CLAUDE.md | Read CLAUDE.md |
| Mirrored | Present in README.md | Read README.md |
| Required columns | Skill **name** + **trigger** (when to use) | Read both tables |
| One row per skill | Every vendored skill appears | List `.claude/skills/*/` (root only — Claude Code discovers only root `.claude/skills/`), compare to rows |
| Synced | CLAUDE.md and README list the **same** set of skills | Diff the two tables; drift = FAIL |

Fix advice patterns:
- Missing table → add one with name + trigger columns, one row per vendored skill, to both files.
- Drift between files → reconcile so both list the identical skill set.
- Missing a column → add the name or trigger column.
- A skill exists but has no row → add its row (both files).
