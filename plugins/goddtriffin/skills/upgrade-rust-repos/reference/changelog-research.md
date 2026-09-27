# Changelog research

How to turn `changelogs` output into a repo's impact list without re-reading the same changelog
twice — across repos in one run, or across runs.

## The cache

Root: `~/.cache/upgrade-rust-repos/` (or `$XDG_CACHE_HOME/upgrade-rust-repos/`).

| Path | Written by | Contents |
| --- | --- | --- |
| `crates/<name>/<version>/CHANGELOG.md` (or `CHANGES*`, `RELEASES*`, `HISTORY*`, `NEWS*`) | script | the changelog shipped inside that version's `.crate` — covers all history up to it |
| `crates/<name>/releases/<version>.md` | script | GitHub release notes, used only when the crate ships no changelog file (needs `gh`) |
| `crates/<name>/<version>/digest.md` | **you** | that one version's digest (format below) |

Published crate versions are immutable, so nothing here is ever invalidated; deleting the cache
only costs a refetch. **Digests are per version, not per bump,** so they compose: a repo on
`0.7.4` and another on `0.8.1` both reuse the `0.8.x`–`0.9.2` digests. `changelogs` lists
`digests to write` — only versions no earlier repo or run has digested.

## Fan-out

Changelogs for a big bump run to tens of thousands of lines; keep them out of the main context.

- **One subagent per breaking bump.** Give it: the crate, old → new, the version list, the source
  file paths, the `missing_digests`, the digest directory, and the repo path.
- **One subagent for all compatible bumps together** — same inputs, skimming for deprecations,
  behavior changes, and new lints or MSRV requirements.

Each subagent:

1. Reads the existing digests for versions already covered.
2. For each missing version, reads **that version's section** of the changelog (changelogs are
   cumulative; find the heading for the version) and writes `digest.md`.
3. Greps the repo for every affected API named in the digests.
4. Returns the impact list — **only** that, not the digests.

When a crate shows `changelog not found`, the subagent researches it from the repository URL given
(release notes, `compare/vOLD...vNEW`, the crate docs), then writes digests as normal.

## Digest format

Repo-independent — it describes the crate, not any user of it.

```markdown
# <crate> <version>
- breaking: <each removed/renamed/changed-signature API, one line, with the replacement>
- behavior: <changed defaults or semantics that compile silently>
- deprecated: <newly deprecated items and their replacements>
- msrv: <new minimum Rust version, if raised>
- none   # when the version changed nothing a user would notice
```

## Impact list format

Repo-specific — returned to the main agent, never cached.

```markdown
## <crate> <old> -> <new>
- <file>:<line> — <what breaks> → <the fix>
- behavior: <silent change that touches this repo> → <what to check or test>
- no impact   # when nothing in this repo uses the changed APIs
```
