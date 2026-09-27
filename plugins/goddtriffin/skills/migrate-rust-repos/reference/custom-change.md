# Custom changes

A **custom change** is anything the user describes that is not the upgrade: a crate swap (`chrono`
→ `jiff`), a refactor (libraries re-export the dependencies in their public API so consumers stop
pinning matching versions), a convention (every repo gets a `cargo-deny` CI step). SKILL.md owns the
loop around it; this file owns the spec that makes the change come out the same in every repo.

## Contents

- [Why a spec](#why-a-spec)
- [Where specs live](#where-specs-live)
- [Drafting](#drafting)
- [Spec format](#spec-format)
- [Applicability](#applicability)
- [Per-repo research](#per-repo-research)
- [Amending mid-run](#amending-mid-run)
- [Commit message](#commit-message)

## Why a spec

A fleet-wide change hides decisions that must land identically everywhere: which `jiff` type
replaces `DateTime<Utc>`, whether a serialized format must stay byte-identical, whether libraries
re-export the new crate. Decided repo by repo, the fleet drifts. The spec decides each once, up
front, and every repo is migrated against it.

## Where specs live

`~/.cache/migrate-rust-repos/specs/<slug>.md` (or under `$XDG_CACHE_HOME`), `<slug>` a short
kebab-case name (`chrono-to-jiff`). A spec survives pauses, context compaction, and new sessions,
and is reusable when the same change later meets a new repo. If a spec with the slug already
exists, read it and ask whether to reuse it, revise it, or start fresh.

## Drafting

Before the grill session:

1. **Research the change** in a subagent, keeping docs out of the main context: the new crate's
   API and any official migration guide, feature flags, `serde` support, MSRV, known pitfalls. For a
   refactor, the Rust idiom and its trade-offs (e.g. `pub use dep;` vs re-exporting specific items).
2. **Scan the fleet** — `report PATH --uses CRATE...` for crate swaps, plus greps or reading for
   anything else — so the draft reflects how the repos actually use what is changing.
3. **Write the draft spec**, with every open question listed. The grill session settles them; the
   spec is saved only once confirmed.

## Spec format

```markdown
# <title>
Requested: "<the user's words>"   Slug: <slug>   Confirmed: <date>

## Goal
<one paragraph: what changes and why>

## Rules
- <old> → <new>, one line per mapping or decision (types, functions, features, re-export policy)

## Invariants
- <what must still hold afterwards: wire/serialized formats, public API beyond the intended change,
  behavior a user could observe>

## Applicability
<how to tell whether a repo is directly affected: a `report --uses` crate list, a grep, or
criteria for judgment>

## Done check
<how to tell a repo is finished — deterministic where possible, e.g. `report --uses chrono` lists
nothing and no `chrono::` remains in tracked `.rs` files>

## Version impact
<when this change makes a library's release minor vs patch, and when it ships nothing>

## Repos
- <repo>: direct | follows upstream | unaffected — <one-line reason; user notes from the grill>

## Decisions log
- <date> <repo that raised it>: <question> → <answer>
```

## Applicability

Every repo gets a status in the spec's **Repos** section (the status definitions are in SKILL.md
step 2):

- **Mechanically detectable** changes (a crate swap): `report --uses` decides **direct**
  deterministically.
- **Judgment** changes (a refactor like re-exporting dependencies): read every repo and write a
  short analysis of each potentially affected one — what it would change, why, and what you
  recommend. In the grill session the user confirms, denies, or annotates each; record the outcome.
- **Follows upstream** comes from the graph: every repo downstream of a repo that will release.

## Per-repo research

In the repo's turn, before applying: list every site the spec touches (file:line), what each
becomes under the spec's rules, and anything the rules do not cover. For a large repo, do this in a
subagent that returns only the list. Uncovered cases are new decisions — see below.

## Amending mid-run

A case the spec does not cover is a pause, not a guess: invoke `mattpocock:grill-me` for that
question alone, add the rule or invariant to the spec, and log it under **Decisions log**. It
applies to every remaining repo. If it would change a repo already finished, say so and ask whether
to revisit it.

## Commit message

Names the spec's title, summarizes what migrated in this repo, and calls out anything the spec's
invariants required special care for (e.g. a serde format kept stable by a custom adapter).
