# Cross-Cutting Principles

Principles that apply across every in-scope file. These are the checks that span files or judge
knowledge placement, and they populate the scorecard's trailing **Cross-cutting** section.

## Single source of truth

Each piece of knowledge has exactly one home — a skill or reference file that owns it. Entry
points and other skills point to that home rather than copying it.

| Check | Rule | How to verify |
|---|---|---|
| One owner per fact | No fact is authoritatively defined in two places | Scan for the same rule/knowledge stated in multiple files |

Fix advice: designate one owner; replace the other copies with pointers.

## No duplication

Related to SSOT but broader: the same content should not appear verbatim or near-verbatim across
files (CLAUDE.md restating a skill; two skills covering the same rule).

| Check | Rule | How to verify |
|---|---|---|
| No repeated content | Same knowledge not present in two+ files | Compare files; flag overlaps |

Fix advice: keep the best single statement in its owner; delete the copies, leaving pointers.

## Docs earn their place

Documentation must be succinct and insightful — never a restatement of what the code/config
already says. Prose that merely narrates code earns no place.

| Check | Rule | How to verify |
|---|---|---|
| Insight over restatement | Each doc paragraph adds knowledge not obvious from the code | Read; flag prose that just describes code line-by-line |

Fix advice: cut restatement; keep only the why/when/gotchas the code cannot express.

## Zero knowledge lost

**Governing mandate for any fix.** When advising a refactor — or applying one — content is *moved,
deduplicated, and made more succinct*, never dropped. Deleting a file is only allowed once its
knowledge is fully preserved in its new home.

This is not a passive check; it is an instruction the audit carries into every fix recommendation:

- Every fix that removes or relocates content must name where the knowledge now lives.
- Deduplication keeps the single best statement — it does not discard the underlying fact.
- Before recommending deletion of a doc, confirm its knowledge exists elsewhere.

Fix advice: pair every "delete" or "move" recommendation with the destination that preserves the
knowledge, so the user's refactor loses nothing.
