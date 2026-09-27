#!/usr/bin/env python3
"""Deterministic helpers for the migrate-rust-repos skill.

Python 3.9+, standard library only. Every subcommand is idempotent and derives
its answer from the repos, the toolchain, and crates.io — there is no run state.
The only thing written outside a repo is an immutable download cache.

Subcommands:
  preflight                 check required and optional tools
  targets                   update stable, print latest toolchain/edition/resolver
  report PATH               discover repos, dependency graph, migration order
                            (--upgrade: upgrade gaps; --uses CRATE: who depends on it)
  changelogs PATH           fetch changelogs for every direct-dependency bump
  bump REPO                 edition migration, toolchain fields, dependency bumps
  follow REPO CRATE...      move first-party deps to their latest published versions
  set-version REPO LEVEL    bump a library's version (LEVEL: patch | minor)
  wait-published CRATE VER  block until crates.io serves CRATE@VER
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "migrate-rust-repos (https://github.com/goddtriffin/skills)"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "migrate-rust-repos"
KNOWN_EDITIONS = ["2015", "2018", "2021", "2024"]  # only for stepping; the target is discovered
CHANGELOG_NAME = re.compile(r"^(CHANGELOG|CHANGES|RELEASES|RELEASE-NOTES|HISTORY|NEWS)", re.I)
DEP_TABLE = re.compile(r"^(workspace\.)?(target\..+\.)?(dev-|build-)?dependencies$")
DEP_SUBTABLE = re.compile(r"^(workspace\.)?(target\..+\.)?(dev-|build-)?dependencies\.([^.]+)$")
FULL_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
BARE_VERSION = re.compile(r"^\d+(\.\d+)?$")


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, cwd=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and p.returncode != 0:
        die(f"`{' '.join(cmd)}` failed in {cwd or '.'}:\n{p.stdout}{p.stderr}")
    return p


# ---------------------------------------------------------------- TOML (line-level)
# Python 3.9 has no tomllib. Cargo resolves semantics via `cargo metadata`; these
# helpers only locate and rewrite individual `key = value` lines, preserving the
# rest of the file byte-for-byte.

def _depth_delta(line):
    depth, quote, i = 0, None, 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            break
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        i += 1
    return depth


def scan(text):
    """Yield (line_index, table, key, raw_value) for every top-level key line."""
    table, depth = "", 0
    for i, line in enumerate(text.split("\n")):
        s = line.strip()
        if depth > 0:
            depth += _depth_delta(line)
            continue
        m = re.match(r"^\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$", s)
        if m:
            table = m.group(1).replace('"', "").replace(" ", "")
            continue
        m = re.match(r'^([A-Za-z0-9_\-."]+)\s*=\s*(.*)$', s)
        if m:
            yield i, table, m.group(1).replace('"', ""), m.group(2)
            depth = _depth_delta(m.group(2))


def get(text, table, key):
    for _, t, k, v in scan(text):
        if t == table and k == key:
            return v
    return None


def string_value(raw):
    m = re.match(r'^"([^"]*)"', raw.strip()) if raw else None
    return m.group(1) if m else None


def tables(text):
    return {t for _, t, _, _ in scan(text)} | set(
        m.group(1).replace('"', "").replace(" ", "")
        for m in re.finditer(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?", text, re.M))


def set_key(text, table, key, value):
    lines = text.split("\n")
    for i, t, k, _ in scan(text):
        if t == table and k == key:
            indent = re.match(r"^\s*", lines[i]).group(0)
            lines[i] = f"{indent}{key} = {value}"
            return "\n".join(lines)
    # Insert after the table's last key line, or create the table.
    last, header = None, None
    for i, line in enumerate(lines):
        if re.match(rf"^\s*\[\s*{re.escape(table)}\s*\]", line):
            header = i
    for i, t, _, _ in scan(text):
        if t == table:
            last = i
    if header is not None:
        at = last if last is not None and last > header else header
        # step past a multi-line value
        depth = 0
        for j in range(at, len(lines)):
            depth += _depth_delta(lines[j] if j > at else lines[j].split("=", 1)[-1])
            if depth <= 0:
                at = j
                break
        lines.insert(at + 1, f"{key} = {value}")
        return "\n".join(lines)
    parent = table.rsplit(".", 1)[0] if "." in table else None
    block = [f"[{table}]", f"{key} = {value}", ""]
    if parent:
        # place the new table just before the first table header after [parent]
        seen = False
        for i, line in enumerate(lines):
            if re.match(rf"^\s*\[\s*{re.escape(parent)}\s*\]", line):
                seen = True
            elif seen and re.match(r"^\s*\[", line):
                lines[i:i] = block
                return "\n".join(lines)
    return text.rstrip("\n") + "\n\n" + "\n".join(block)


def delete_key(text, table, key):
    lines = text.split("\n")
    for i, t, k, _ in scan(text):
        if t == table and k == key:
            del lines[i]
            return "\n".join(lines)
    return text


# ---------------------------------------------------------------- versions

def vtuple(v):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v)
    return tuple(int(x) for x in m.groups()) if m else None


def is_breaking(old, new):
    a, b = vtuple(old), vtuple(new)
    if not a or not b:
        return False
    if a[0] != b[0]:
        return True
    if a[0] == 0 and a[1] != b[1]:
        return True
    return a[0] == 0 and a[1] == 0 and a[2] != b[2]


# ---------------------------------------------------------------- crates.io

_memo = {}


def http_get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return data if binary else data.decode()


def index_path(name):
    n = name.lower()
    if len(n) <= 2:
        return f"{len(n)}/{n}"
    if len(n) == 3:
        return f"3/{n[0]}/{n}"
    return f"{n[:2]}/{n[2:4]}/{n}"


def index_versions(name, fresh=False):
    """All published versions from the sparse index: [(vers, yanked)]."""
    if name in _memo and not fresh:
        return _memo[name]
    body = http_get(f"https://index.crates.io/{index_path(name)}")
    out = []
    for line in (body or "").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append((d["vers"], d.get("yanked", False)))
    _memo[name] = out
    return out


def latest_stable(name):
    vs = [vtuple(v) for v, y in index_versions(name) if not y and vtuple(v)]
    return ".".join(map(str, max(vs))) if vs else None


def crate_repository(name):
    body = http_get(f"https://crates.io/api/v1/crates/{name}")
    return (json.loads(body)["crate"].get("repository") or "") if body else ""


# ---------------------------------------------------------------- repos

def cargo_metadata(repo):
    p = run(["cargo", "metadata", "--format-version", "1", "--no-deps",
             "--manifest-path", str(repo / "Cargo.toml")], check=False)
    if p.returncode != 0:
        return None, p.stderr.strip()
    return json.loads(p.stdout), None


def layout(root_text):
    ws, pkg = "workspace" in tables(root_text), "package" in tables(root_text)
    if ws and pkg:
        return "root-package-workspace"
    return "virtual-workspace" if ws else "single-crate"


def discover(path):
    path = path.resolve()
    if (path / "Cargo.toml").exists():
        return [path]
    return sorted((d for d in path.iterdir()
                   if d.is_dir() and (d / ".git").exists() and (d / "Cargo.toml").exists()),
                  key=lambda d: d.name.lower())


def skipped(path):
    """Git repos in a directory that discovery skips: no root Cargo.toml."""
    path = path.resolve()
    if (path / "Cargo.toml").exists():
        return []
    return sorted(d.name for d in path.iterdir()
                  if d.is_dir() and (d / ".git").exists() and not (d / "Cargo.toml").exists())


def manifests(repo, meta):
    """Root manifest plus every workspace member's manifest (deduplicated)."""
    out = [repo / "Cargo.toml"]
    for p in (meta or {}).get("packages", []):
        m = Path(p["manifest_path"])
        if m not in out:
            out.append(m)
    return out


def dep_entries(text):
    """Yield dicts describing every dependency declaration in one manifest."""
    for i, table, key, raw in scan(text):
        m = DEP_SUBTABLE.match(table)
        if m and key == "version":
            yield {"line": i, "table": table, "key": m.group(4), "crate": m.group(4),
                   "req": string_value(raw), "kind": "registry", "inherited": False}
            continue
        if not DEP_TABLE.match(table):
            continue
        e = {"line": i, "table": table, "key": key, "crate": key, "req": None,
             "kind": "registry", "inherited": False}
        if raw.startswith('"'):
            e["req"] = string_value(raw)
        elif key.endswith(".workspace") or re.search(r"\bworkspace\s*=\s*true", raw):
            e.update(inherited=True, key=key.split(".")[0], crate=key.split(".")[0])
        else:
            vm = re.search(r'\bversion\s*=\s*"([^"]*)"', raw)
            pm = re.search(r'\bpackage\s*=\s*"([^"]*)"', raw)
            e["req"] = vm.group(1) if vm else None
            e["crate"] = pm.group(1) if pm else key
            if re.search(r"\bgit\s*=", raw):
                e["kind"] = "git"
            elif re.search(r"\bpath\s*=", raw):
                e["kind"] = "path"
        yield e


def lock_versions(text):
    out = {}
    for m in re.finditer(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text or ""):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


def best_locked(locked, req):
    """Highest locked version satisfying a caret requirement ("1", "1.2", "1.2.3")."""
    parts = [int(x) for x in req.split(".")]
    # caret: leading zeros widen what must match exactly
    fixed = next((i + 1 for i, x in enumerate(parts) if x != 0), len(parts))
    fixed = min(fixed, len(parts))
    cands = [t for t in map(vtuple, locked)
             if t and list(t[:fixed]) == parts[:fixed] and t[:len(parts)] >= tuple(parts)]
    return ".".join(map(str, max(cands))) if cands else None


def git(repo, *args):
    p = run(["git", *args], cwd=repo, check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def default_branch(repo):
    ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return ref.split("/", 1)[1] if ref else "main"


def is_publishable_lib(pkg):
    lib = any(k in ("lib", "rlib", "proc-macro") for t in pkg["targets"] for k in t["kind"])
    return lib and pkg.get("publish") != []


def clippy_files(repo):
    return [p for p in repo.rglob("*clippy.toml")
            if p.name in ("clippy.toml", ".clippy.toml") and "target" not in p.parts]


def toolchain_files(repo):
    return [p for p in (repo / "rust-toolchain.toml", repo / "rust-toolchain") if p.exists()]


def grep(repo, globs, pattern):
    """Search git-tracked files only, so ignored clones and build output never match."""
    rx, hits = re.compile(pattern), []
    for rel in (git(repo, "ls-files", "--", *globs) or "").splitlines():
        f = repo / rel
        if CHANGELOG_NAME.match(f.name) or not f.is_file():
            continue
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    return hits


# ---------------------------------------------------------------- targets

def compute_targets(update=False):
    if update:
        run(["rustup", "update", "stable"])
    full = re.search(r"(\d+\.\d+\.\d+)", run(["rustc", "+stable", "--version"]).stdout).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        run(["cargo", "+stable", "new", "--lib", "--vcs", "none", "probe"], cwd=ws)
        edition = string_value(get((ws / "probe" / "Cargo.toml").read_text(), "package", "edition"))
        (ws / "Cargo.toml").write_text('[workspace]\nmembers = ["probe"]\n')
        err = run(["cargo", "+stable", "metadata", "--format-version", "1", "--no-deps"], cwd=ws).stderr
    m = re.search(r'implies `resolver = "(\d+)"`', err)
    if not edition or not m:
        die("could not derive the latest edition/resolver from cargo; "
            "look them up in the Cargo reference instead.\n" + err)
    major, minor, _ = full.split(".")
    return {"toolchain": full, "rust_version": f"{major}.{minor}",
            "edition": edition, "resolver": m.group(1)}


# ---------------------------------------------------------------- report

def uses(repo, meta, crates):
    """Every manifest line declaring one of `crates` directly (renames resolved)."""
    hits = []
    for mf in manifests(repo, meta):
        for e in dep_entries(mf.read_text()):
            if e["crate"] in crates:
                how = "inherited" if e["inherited"] else (e["req"] or e["kind"])
                hits.append(f"{e['crate']}: {mf.relative_to(repo)} [{e['table']}] {how}")
    return hits


def repo_state(repo, targets=None, uses_crates=()):
    """Discovery and graph inputs always; upgrade findings only when `targets` is given."""
    root_text = (repo / "Cargo.toml").read_text()
    meta, err = cargo_metadata(repo)
    st = {"repo": repo.name, "path": str(repo), "layout": layout(root_text),
          "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
          "default_branch": default_branch(repo),
          "dirty": bool(git(repo, "status", "--porcelain")),
          "metadata_error": err, "packages": [], "provides": [], "deps": [], "findings": [],
          "uses": [], "dockerfile_rust": [], "doc_msrv_mentions": []}
    if meta is None:
        return st
    st["uses"] = uses(repo, meta, set(uses_crates))
    ws = st["layout"] != "single-crate"
    tbl = "workspace.package" if ws else "package"
    member_ids = set(meta.get("workspace_members", []))
    for p in meta["packages"]:
        if p["id"] not in member_ids:
            continue
        lib = is_publishable_lib(p)
        st["packages"].append({"name": p["name"], "version": p["version"], "publishable_lib": lib,
                               "edition": p["edition"], "rust_version": p.get("rust_version")})
        if p.get("publish") != []:
            st["provides"].append(p["name"])
    if targets is None:
        st["deps"] = [{"manifest": str(mf.relative_to(repo)), "crate": e["crate"], "kind": e["kind"],
                       "req": e["req"]}
                      for mf in manifests(repo, meta) for e in dep_entries(mf.read_text())
                      if not e["inherited"]]
        return st
    cur = {"edition": string_value(get(root_text, tbl, "edition")),
           "rust_version": string_value(get(root_text, tbl, "rust-version")),
           "resolver": string_value(get(root_text, "workspace" if ws else "package", "resolver"))}
    st["current"] = cur
    for k in ("edition", "rust_version"):
        if cur[k] != targets[k]:
            st["findings"].append(f"{k}: {cur[k]} -> {targets[k]} (in [{tbl}])")
    if ws and cur["resolver"] != targets["resolver"]:
        st["findings"].append(f"resolver: {cur['resolver']} -> {targets['resolver']} (in [workspace])")
    if not ws and cur["resolver"]:
        st["findings"].append(f"single crate sets `resolver = \"{cur['resolver']}\"`; "
                              "remove it, the edition implies it")
    for f in clippy_files(repo):
        if get(f.read_text(), "", "msrv") is not None:
            left = "kept" if clippy_residue(f.read_text()) else "deleted (nothing else in it)"
            st["findings"].append(f"{f.relative_to(repo)}: msrv duplicates rust-version; bump removes "
                                  f"it, file {left}")
            if left != "kept":
                st["findings"] += [f"references {f.name} (remove with the file): {h}"
                                   for h in grep(repo, ["*"], re.escape(f.name))
                                   if not h.startswith(f"{f.relative_to(repo)}:")]
    for f in toolchain_files(repo):
        st["findings"].append(f"toolchain pin {f.name}: {f.read_text().strip()!r}")

    lock_text = (Path(meta["workspace_root"]) / "Cargo.lock")
    locked = lock_versions(lock_text.read_text() if lock_text.exists() else "")
    versions = {}
    for mf in manifests(repo, meta):
        text = mf.read_text()
        rel = mf.relative_to(repo)
        member = ws and mf != repo / "Cargo.toml"
        if member:
            for key in ("edition", "rust-version", "version"):
                raw = get(text, "package", key)
                if raw is not None and "workspace" not in raw and get(text, "package", f"{key}.workspace") is None:
                    st["findings"].append(f"{rel}: [package] {key} is not inherited from the workspace")
                if key == "version" and raw is not None and "workspace" not in raw:
                    versions[str(rel)] = string_value(raw)
            if get(text, "package", "resolver") is not None:
                st["findings"].append(f"{rel}: member sets resolver; cargo ignores it, remove it")
        for e in dep_entries(text):
            if e["inherited"]:
                continue
            if member and e["kind"] != "path":
                st["findings"].append(f"{rel}: dependency `{e['key']}` declared inline, "
                                      "not via workspace.dependencies")
            if e["kind"] == "git" or (e["kind"] == "path" and not e["req"]):
                st["deps"].append({"manifest": str(rel), "crate": e["crate"], "kind": e["kind"]})
                continue
            req = e["req"] or ""
            lk = best_locked(locked.get(e["crate"], []), req.lstrip("^")) if BARE_VERSION.match(req.lstrip("^")) or FULL_VERSION.match(req.lstrip("^")) else None
            d = {"manifest": str(rel), "crate": e["crate"], "kind": e["kind"], "req": req,
                 "locked": lk, "latest": latest_stable(e["crate"])}
            if BARE_VERSION.match(req):
                d["flag"] = "bare requirement; bump normalizes it to M.m.p"
            elif not FULL_VERSION.match(req):
                d["flag"] = "non-M.m.p requirement; recommend plain M.m.p if nothing breaks (user decides)"
            base = lk or (req if FULL_VERSION.match(req) else None)
            if d["latest"] and base and vtuple(d["latest"]) > vtuple(base):
                d["bump"] = "breaking" if is_breaking(base, d["latest"]) else "compatible"
            elif d["latest"] and FULL_VERSION.match(req) and vtuple(d["latest"]) > vtuple(req):
                d["bump"] = "requirement-only (already locked at latest)"
            st["deps"].append(d)
    if versions:
        st["findings"].append("workspace crates are independently versioned: bump each library "
                              "crate in its own manifest, following the repo's convention")
    st["dockerfile_rust"] = [h for h in grep(repo, ["*Dockerfile*"], r"\brust:\S+")
                             if f"rust:{targets['toolchain']}" not in h]
    st["doc_msrv_mentions"] = grep(repo, ["*.md"], r"(?i)\bmsrv\b|minimum supported rust|"
                                   r"\brust(c)?\s+1\.\d+|\brust-version\s*=?\s*\"?1\.\d+")
    return st


def graph(states):
    provider, detail = {}, []
    for s in states:
        for c in s["provides"]:
            provider.setdefault(c, []).append(s["repo"])
    edges = {s["repo"]: set() for s in states}
    for s in states:
        for d in s["deps"]:
            if d["crate"] in s["provides"]:
                continue  # the repo's own workspace member
            ups = provider.get(d["crate"], [])
            if len(ups) > 1:
                detail.append(f"WARNING: {s['repo']} depends on `{d['crate']}`, provided by "
                              f"several repos ({', '.join(ups)}); resolve the edge by hand")
                continue
            up = ups[0] if ups else None
            if up:
                edges[s["repo"]].add(up)
                latest_local = next((p["version"] for u in states if u["repo"] == up
                                     for p in u["packages"] if p["name"] == d["crate"]), None)
                detail.append(f"{s['repo']} -> {up}: {d['crate']} {d.get('req')} "
                              f"(upstream local {latest_local})")
    order, tiers, done = [], {}, set()
    while len(done) < len(edges):
        ready = sorted((r for r in edges if r not in done and edges[r] <= done), key=str.lower)
        if not ready:
            cyc = sorted(r for r in edges if r not in done)
            die(f"dependency cycle among: {', '.join(cyc)}")
        for r in ready:
            tiers[r] = 1 + max((tiers[u] for u in edges[r]), default=-1)
        order += ready
        done |= set(ready)
    return order, tiers, sorted(set(detail))


def cmd_report(args):
    targets = compute_targets() if args.upgrade else None
    states = [repo_state(r, targets, args.uses) for r in discover(Path(args.path))]
    if not states:
        die(f"no Rust repos at {args.path}")
    order, tiers, edges = graph(states)
    if args.json:
        print(json.dumps({"targets": targets, "order": order, "tiers": tiers, "edges": edges,
                          "skipped": skipped(Path(args.path)), "repos": states}, indent=2))
        return
    if skipped(Path(args.path)):
        print(f"# Skipped (git repos without a root Cargo.toml)\n  {', '.join(skipped(Path(args.path)))}\n")
    if targets:
        print(f"# Targets\n{json.dumps(targets)}\n")
    print("# Migration order (tier: repo)")
    for r in order:
        print(f"  {tiers[r]}: {r}")
    if edges:
        print("\n# First-party edges\n" + "\n".join(f"  {e}" for e in edges))
    by = {s["repo"]: s for s in states}
    for r in order:
        s = by[r]
        print(f"\n## {r}  [{s['layout']}]  branch={s['branch']} default={s['default_branch']}"
              f"{'  DIRTY' if s['dirty'] else ''}")
        if s["metadata_error"]:
            print(f"  cargo metadata failed: {s['metadata_error']}")
            continue
        for p in s["packages"]:
            print(f"  crate {p['name']} {p['version']} {'lib' if p['publishable_lib'] else 'bin/unpublished'}")
        if args.uses:
            print("\n".join(f"  uses {h}" for h in s["uses"]) or f"  uses none of: {', '.join(args.uses)}")
        for f in s["findings"]:
            print(f"  - {f}")
        for d in s["deps"]:
            if "bump" in d or "flag" in d or d["kind"] == "git":
                print(f"  dep {d['crate']} {d.get('req') or d['kind']} (locked {d.get('locked')})"
                      f" -> {d.get('latest')} {d.get('bump', '')} {d.get('flag', '')}  [{d['manifest']}]")
        for h in s["dockerfile_rust"]:
            print(f"  docker: {h}")
        for h in s["doc_msrv_mentions"]:
            print(f"  possible doc MSRV mention (if it is one, recommend deleting it): {h}")


# ---------------------------------------------------------------- changelogs

def fetch_changelog(name, version):
    d = CACHE / "crates" / name / version
    marker = d / ".fetched"
    if not marker.exists():
        data = http_get(f"https://static.crates.io/crates/{name}/{name}-{version}.crate", binary=True)
        d.mkdir(parents=True, exist_ok=True)
        if data:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for m in tar.getmembers():
                    parts = m.name.split("/")
                    if m.isfile() and len(parts) == 2 and CHANGELOG_NAME.match(parts[1]):
                        (d / parts[1]).write_bytes(tar.extractfile(m).read())
        marker.write_text("")
    return sorted(str(p) for p in d.iterdir() if CHANGELOG_NAME.match(p.name))


def fetch_releases(name, versions):
    if not shutil.which("gh"):
        return [], "gh not installed"
    repo_url = crate_repository(name)
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", repo_url)
    if not m:
        return [], f"repository is not on GitHub: {repo_url or 'none'}"
    owner, gh_repo = m.group(1), m.group(2).removesuffix(".git")
    rel_dir = CACHE / "crates" / name / "releases"
    wanted = {v: rel_dir / f"{v}.md" for v in versions}
    if not all(p.exists() for p in wanted.values()):
        p = run(["gh", "api", "--paginate", f"repos/{owner}/{gh_repo}/releases",
                 "--jq", ".[] | {tag_name, body}"], check=False)
        if p.returncode != 0:
            return [], f"gh api failed: {p.stderr.strip()}"
        rel_dir.mkdir(parents=True, exist_ok=True)
        for line in p.stdout.splitlines():
            r = json.loads(line)
            for v, path in wanted.items():
                if re.search(rf"(^|[^0-9.]){re.escape(v)}$", r["tag_name"]):
                    path.write_text(f"# {r['tag_name']}\n\n{r.get('body') or ''}\n")
    return [str(p) for p in wanted.values() if p.exists()], None


def repo_bumps(repo):
    """Direct registry deps: committed (HEAD) locked version -> latest stable."""
    meta, err = cargo_metadata(repo)
    if meta is None:
        die(f"{repo.name}: cargo metadata failed: {err}")
    root = Path(meta["workspace_root"])
    head_lock = git(root, "show", "HEAD:Cargo.lock")
    disk_lock = (root / "Cargo.lock").read_text() if (root / "Cargo.lock").exists() else ""
    locked = lock_versions(head_lock or disk_lock)
    out = {}
    for mf in manifests(repo, meta):
        for e in dep_entries(mf.read_text()):
            if e["inherited"] or e["kind"] == "git" or not e["req"]:
                continue
            req = e["req"].lstrip("^")
            old = best_locked(locked.get(e["crate"], []), req) if BARE_VERSION.match(req) or FULL_VERSION.match(req) else None
            old = old or (req if FULL_VERSION.match(req) else None)
            new = latest_stable(e["crate"])
            if old and new and vtuple(new) > vtuple(old):
                out[e["crate"]] = (old, new)
    return out


def cmd_changelogs(args):
    bumps = {}
    for repo in discover(Path(args.path)):
        for crate, (old, new) in repo_bumps(repo).items():
            bumps.setdefault((crate, old, new), []).append(repo.name)
    result = []
    for (crate, old, new), repos in sorted(bumps.items()):
        between = sorted((v for v, y in index_versions(crate)
                          if not y and vtuple(v) and vtuple(old) < vtuple(v) <= vtuple(new)), key=vtuple)
        files = fetch_changelog(crate, new)
        releases, note = ([], None) if files else fetch_releases(crate, between)
        digests = {v: str(CACHE / "crates" / crate / v / "digest.md") for v in between}
        result.append({
            "crate": crate, "old": old, "new": new, "breaking": is_breaking(old, new), "repos": repos,
            "versions": between, "changelog_files": files, "release_notes": releases,
            "missing_digests": [v for v, p in digests.items() if not Path(p).exists()],
            "digest_paths": digests,
            "status": "ok" if files or releases else f"changelog not found ({note or 'no file in crate'}); "
                      f"research manually, repository: {crate_repository(crate) or 'unknown'}"})
    if args.json:
        print(json.dumps(result, indent=2))
        return
    for r in result:
        print(f"{r['crate']} {r['old']} -> {r['new']}  {'BREAKING' if r['breaking'] else 'compatible'}"
              f"  repos: {', '.join(r['repos'])}")
        print(f"  versions: {', '.join(r['versions'])}")
        for f in r["changelog_files"] + r["release_notes"]:
            print(f"  source: {f}")
        if r["missing_digests"]:
            print(f"  digests to write: {', '.join(r['missing_digests'])} "
                  f"(dir {CACHE / 'crates' / r['crate']}/<version>/digest.md)")
        if r["status"] != "ok":
            print(f"  {r['status']}")


# ---------------------------------------------------------------- bump

def write(path, text, changes, what):
    if path.read_text() != text:
        path.write_text(text)
        changes.append(what)


def edit_manifests(repo, targets, changes, edition=True):
    """Set resolver/rust-version (and edition, once migrated) where the layout wants them."""
    root = repo / "Cargo.toml"
    text = root.read_text()
    kind = layout(text)
    meta, err = cargo_metadata(repo)
    if meta is None:
        die(f"cargo metadata failed: {err}")
    if kind == "single-crate":
        new = set_key(text, "package", "rust-version", f'"{targets["rust_version"]}"')
        if edition:
            new = set_key(new, "package", "edition", f'"{targets["edition"]}"')
        new = delete_key(new, "package", "resolver")
        write(root, new, changes, "Cargo.toml: [package] edition/rust-version; no explicit resolver")
        return
    new = set_key(text, "workspace", "resolver", f'"{targets["resolver"]}"')
    new = set_key(new, "workspace.package", "rust-version", f'"{targets["rust_version"]}"')
    if edition:
        new = set_key(new, "workspace.package", "edition", f'"{targets["edition"]}"')
    write(root, new, changes, "Cargo.toml: [workspace] resolver, [workspace.package] edition/rust-version")
    for mf in manifests(repo, meta):
        t = mf.read_text()
        n = t
        for key in ("edition", "rust-version") if edition else ("rust-version",):
            raw = get(n, "package", key)
            if raw is not None and "workspace" not in raw:
                lines = n.split("\n")
                for i, tb, k, _ in scan(n):
                    if tb == "package" and k == key:
                        lines[i] = f"{key}.workspace = true"
                n = "\n".join(lines)
        n = delete_key(n, "package", "resolver")
        write(mf, n, changes, f"{mf.relative_to(repo)}: inherit edition/rust-version; no member resolver")


def clippy_residue(text):
    """What is left of a clippy config once msrv is gone (comments and blanks don't count)."""
    rest = delete_key(text, "", "msrv")
    return [l for l in rest.splitlines() if l.strip() and not l.strip().startswith("#")]


def edit_side_files(repo, targets, changes):
    # Clippy falls back to the rust-version cargo passes it (inherited or not), so an msrv
    # here only duplicates Cargo.toml and can drift from it.
    for f in clippy_files(repo):
        text = f.read_text()
        if get(text, "", "msrv") is None:
            continue
        rel = f.relative_to(repo)
        if clippy_residue(text):
            write(f, delete_key(text, "", "msrv"), changes, f"{rel}: removed msrv")
            continue
        f.unlink()
        changes.append(f"{rel}: deleted (held only msrv)")
        refs = [h for h in grep(repo, ["*"], re.escape(f.name)) if not h.startswith(f"{rel}:")]
        changes += [f"STILL REFERENCES {f.name}, remove: {h}" for h in refs]
    for f in toolchain_files(repo):
        text = f.read_text()
        new = re.sub(r'(channel\s*=\s*")\d+\.\d+(\.\d+)?(")', rf'\g<1>{targets["toolchain"]}\g<3>', text)
        if f.name == "rust-toolchain" and re.fullmatch(r"\d+\.\d+(\.\d+)?\s*", text):
            new = targets["toolchain"] + "\n"
        write(f, new, changes, f"{f.name}: numeric channel -> {targets['toolchain']}")


def migrate_edition(repo, targets, changes):
    text = (repo / "Cargo.toml").read_text()
    tbl = "package" if layout(text) == "single-crate" else "workspace.package"
    cur = string_value(get(text, tbl, "edition")) or "2015"
    steps = [e for e in KNOWN_EDITIONS if int(e) > int(cur)]
    if targets["edition"] not in steps and int(targets["edition"]) > int(cur):
        steps.append(targets["edition"])
    steps = [e for e in steps if int(e) <= int(targets["edition"])]
    for e in steps:
        p = run(["cargo", "fix", "--edition", "--workspace", "--all-targets", "--all-features",
                 "--allow-dirty", "--allow-staged", "--manifest-path", str(repo / "Cargo.toml")], check=False)
        if p.returncode != 0:
            die(f"`cargo fix --edition` toward {e} failed; fix the code, then re-run bump:\n{p.stderr}")
        text = (repo / "Cargo.toml").read_text()
        (repo / "Cargo.toml").write_text(set_key(text, tbl, "edition", f'"{e}"'))
        changes.append(f"edition migrated to {e} via cargo fix --edition")


def normalize_requirements(repo, changes):
    meta, err = cargo_metadata(repo)
    if meta is None:
        die(f"cargo metadata failed after upgrade: {err}")
    lock = Path(meta["workspace_root"]) / "Cargo.lock"
    locked = lock_versions(lock.read_text() if lock.exists() else "")
    unresolved = []
    for mf in manifests(repo, meta):
        text = mf.read_text()
        lines = text.split("\n")
        for e in dep_entries(text):
            req = e["req"]
            if e["inherited"] or not req or not BARE_VERSION.match(req):
                continue
            full = best_locked(locked.get(e["crate"], []), req)
            if not full:
                unresolved.append(f"{mf.relative_to(repo)}: {e['key']} = {req}")
                continue
            lines[e["line"]] = re.sub(rf'(^|version\s*=\s*|=\s*)"{re.escape(req)}"',
                                      lambda m: f'{m.group(1)}"{full}"', lines[e["line"]], count=1)
        write(mf, "\n".join(lines), changes, f"{mf.relative_to(repo)}: bare requirements -> M.m.p")
    if unresolved:
        print("could not normalize (no locked version):\n  " + "\n  ".join(unresolved), file=sys.stderr)


def cmd_bump(args):
    repo = Path(args.repo).resolve()
    if not (repo / "Cargo.toml").exists():
        die(f"{repo} has no Cargo.toml")
    if not shutil.which("cargo-upgrade"):
        die("cargo-upgrade not found; install it with `cargo install cargo-edit`")
    targets = compute_targets()
    changes = []
    # Order matters. A toolchain pin is raised before any cargo command runs in the repo.
    # rust-version is raised before the edition flips (cargo rejects a new edition under an
    # old rust-version) and before `cargo upgrade` (which holds back to the old MSRV). The
    # edition migration runs on the pre-upgrade code, which is known to compile.
    edit_side_files(repo, targets, changes)
    edit_manifests(repo, targets, changes, edition=False)
    migrate_edition(repo, targets, changes)
    edit_manifests(repo, targets, changes)
    mp = ["--manifest-path", str(repo / "Cargo.toml")]
    p = run(["cargo", "upgrade", "--incompatible", *mp], check=False)
    if p.returncode != 0:
        die(f"cargo upgrade failed:\n{p.stdout}{p.stderr}")
    print(p.stdout.strip())
    run(["cargo", "update", *mp])
    normalize_requirements(repo, changes)
    print(json.dumps({"targets": targets, "changes": changes}, indent=2))


def cmd_follow(args):
    repo = Path(args.repo).resolve()
    if not shutil.which("cargo-upgrade"):
        die("cargo-upgrade not found; install it with `cargo install cargo-edit`")
    mp = ["--manifest-path", str(repo / "Cargo.toml")]
    held = []
    for crate in args.crates:
        latest = latest_stable(crate)
        if not latest:
            die(f"{crate} has no stable version on crates.io")
        p = run(["cargo", "upgrade", "--incompatible", "-p", f"{crate}@{latest}", *mp], check=False)
        if p.returncode != 0:
            die(f"cargo upgrade -p {crate}@{latest} failed:\n{p.stdout}{p.stderr}")
        print(p.stdout.strip())
        run(["cargo", "update", "-p", crate, *mp])
        meta, err = cargo_metadata(repo)
        if meta is None:
            die(f"cargo metadata failed: {err}")
        reqs = [e["req"] for mf in manifests(repo, meta) for e in dep_entries(mf.read_text())
                if e["crate"] == crate and e["req"]]
        if not reqs:
            held.append(f"{crate}: not a direct registry dependency of {repo.name}")
        held += [f"{crate}: requirement {r} is not {latest} (rust-version too old for it, or a "
                 f"non-M.m.p requirement cargo upgrade skips)" for r in reqs if r.lstrip("^") != latest]
    if held:
        die("not every crate moved to its latest version:\n  " + "\n  ".join(held))
    print(f"{repo.name}: {', '.join(args.crates)} at latest")


# ---------------------------------------------------------------- set-version / wait / preflight

def cmd_set_version(args):
    repo = Path(args.repo).resolve()
    root = repo / "Cargo.toml"
    text = root.read_text()
    tbl = "package" if layout(text) == "single-crate" else "workspace.package"
    cur = string_value(get(text, tbl, "version"))
    if not cur or not vtuple(cur):
        die(f"no M.m.p version in [{tbl}]; the repo versions crates independently — "
            "bump each library crate's own manifest by hand, following the repo's convention")
    a, b, c = vtuple(cur)
    new = f"{a}.{b + 1}.0" if args.level == "minor" else f"{a}.{b}.{c + 1}"
    root.write_text(set_key(text, tbl, "version", f'"{new}"'))
    run(["cargo", "update", "--workspace", "--manifest-path", str(root)])
    print(f"{cur} -> {new}")


def cmd_wait_published(args):
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if any(v == args.version for v, _ in index_versions(args.crate, fresh=True)):
            print(f"{args.crate} {args.version} is live on the crates.io index")
            return
        time.sleep(15)
    die(f"{args.crate} {args.version} not on the index after {args.timeout}s")


def cmd_preflight(_):
    ok = True
    for tool, fix in [("cargo", "install rustup: https://rustup.rs"),
                      ("rustup", "install rustup: https://rustup.rs"),
                      ("git", "xcode-select --install"),
                      ("cargo-upgrade", "cargo install cargo-edit")]:
        found = shutil.which(tool)
        ok &= bool(found)
        print(f"{'ok     ' if found else 'MISSING'} {tool}{'' if found else f'  -> {fix}'}")
    for tool, why in [("gh", "opening and watching PRs (the default way changes land), and GitHub "
                             "release notes when a crate ships no changelog file"),
                      ("cargo-semver-checks", "confirms the library version-bump level; "
                       "cargo install cargo-semver-checks")]:
        print(f"{'ok     ' if shutil.which(tool) else 'optional'} {tool}  ({why})")
    if sys.version_info < (3, 9):
        ok = False
        print("MISSING python >= 3.9")
    sys.exit(0 if ok else 1)


def cmd_targets(_):
    print(json.dumps(compute_targets(update=True), indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight").set_defaults(fn=cmd_preflight)
    sub.add_parser("targets").set_defaults(fn=cmd_targets)
    for name, fn in (("report", cmd_report), ("changelogs", cmd_changelogs)):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--json", action="store_true")
        p.set_defaults(fn=fn)
        if name == "report":
            p.add_argument("--upgrade", action="store_true", help="include upgrade gaps vs the targets")
            p.add_argument("--uses", nargs="+", default=[], metavar="CRATE",
                           help="list where each repo depends on CRATE directly")
    p = sub.add_parser("bump")
    p.add_argument("repo")
    p.set_defaults(fn=cmd_bump)
    p = sub.add_parser("follow")
    p.add_argument("repo")
    p.add_argument("crates", nargs="+", metavar="CRATE")
    p.set_defaults(fn=cmd_follow)
    p = sub.add_parser("set-version")
    p.add_argument("repo")
    p.add_argument("level", choices=["patch", "minor"])
    p.set_defaults(fn=cmd_set_version)
    p = sub.add_parser("wait-published")
    p.add_argument("crate")
    p.add_argument("version")
    p.add_argument("--timeout", type=int, default=900)
    p.set_defaults(fn=cmd_wait_published)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
