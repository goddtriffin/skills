# Skill Artifact Standards

Rules for vendored skills: `SKILL.md`, its `reference/*.md` files, and when a skill should be split.

## SKILL.md frontmatter

Frontmatter is YAML with two required fields: `name` and `description`.

| Check | Rule | How to verify |
|---|---|---|
| `name` present | Non-empty | Read frontmatter |
| `name` format | Letters, numbers, hyphens only — no spaces, parentheses, or special chars | Read frontmatter |
| `description` present | Non-empty | Read frontmatter |
| `description` length | ≤ 1024 chars | `python3 -c "print(len(open('SKILL.md').read().split('description:',1)[1].split(chr(10))[0].strip()))"` — or count the description string directly; FAIL if > 1024 |
| `description` voice | Third person, starts with "Use when…" | Read frontmatter |
| `description` content | Triggering conditions only — no workflow/process summary | Read frontmatter |

**Why triggers-only:** a description that summarizes the workflow becomes a shortcut agents follow *instead of* reading the skill body. Keep it to when-to-invoke.

Fix advice patterns:
- Over 1024 chars → cut any workflow summary; keep only triggers and keywords.
- Not "Use when…" → rewrite as third-person triggering conditions.
- Describes what the skill does → strip the process; state only the situations that should invoke it.

## SKILL.md body

The body is everything after the closing `---` of the frontmatter.

| Check | Rule | How to verify |
|---|---|---|
| Body length | < 500 lines | `awk 'f{n++} /^---$/{c++; if(c==2)f=1} END{print n}' SKILL.md` — counts lines after the 2nd `---`; FAIL if ≥ 500 |

Fix advice patterns:
- Over 500 lines → extract heavy/reference material (API tables, long examples, exhaustive rules) into `reference/*.md` loaded on demand. Keep the body as overview + core procedure + pointers.
- Still over 500 after extraction → check the split heuristic below; the skill may be doing two jobs.

## reference/*.md files

Reference files are the release valve for an oversized body. **They have no line ceiling** — that is their purpose.

| Check | Rule | How to verify |
|---|---|---|
| TOC present | Required once the file exceeds 100 lines | `wc -l < reference/FILE.md`; if > 100, confirm a table-of-contents/section-index exists near the top; FAIL if missing |

Fix advice patterns:
- Over 100 lines, no TOC → add a table of contents linking each section.
- Genuinely enormous → do not impose a line cap; instead check the split heuristic — the content may be two distinct domains that belong in separate reference files or separate skills.

## When to split a skill

Recommend splitting one skill into two when **either** signal holds. Line count alone never forces a split.

1. **Multiple unrelated triggers** — the `description`'s "Use when…" clause describes two or more distinct situations that would not co-occur (e.g., "use when onboarding a tenant OR when running DB migrations"). Each trigger wants its own skill.
2. **Distinct standalone workflows** — the body contains two or more procedures that share no state/context and would each make sense invoked alone.

When neither holds but the body is still large, the fix is more reference extraction, not a split.

Fix advice patterns:
- Split recommended → name the two proposed skills and which triggers/workflows go to each; note that shared knowledge should move to a `reference/` file or be pointed to, never duplicated across the split.
