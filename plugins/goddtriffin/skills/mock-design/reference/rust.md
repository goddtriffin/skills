# Rust mechanics

How to satisfy the mock design in Rust. `SKILL.md` owns the rules; this file owns the syntax.

## Contents

- [Module layout](#module-layout)
- [Keeping mocks out of production builds](#keeping-mocks-out-of-production-builds)
- [Locks: std, not tokio](#locks-std-not-tokio)
- [Args structs](#args-structs)
- [The call-log enum](#the-call-log-enum)
- [Mock struct and seed storage](#mock-struct-and-seed-storage)
- [Constructors](#constructors)
- [Seeding methods](#seeding-methods)
- [The trait impl](#the-trait-impl)
- [Reading the call log](#reading-the-call-log)
- [The exhaustiveness check](#the-exhaustiveness-check)
- [Automatic check on scope exit](#automatic-check-on-scope-exit)
- [Composite mocks](#composite-mocks)
- [Default trait methods](#default-trait-methods)
- [Tests for the mock itself](#tests-for-the-mock-itself)
- [Rust review addendum](#rust-review-addendum)

## Module layout

One directory per abstraction. `mod.rs` is a thin re-export barrel and holds no logic, so the
public path stays flat (`crate::github_client::GithubClient`) while file names still announce
their contents.

```
src/github_client/
├── mod.rs                       // re-exports only
├── github_client.rs             // trait GithubClient
├── reqwest_github_client.rs     // struct ReqwestGithubClient
└── mock_github_client.rs        // struct MockGithubClient
```

```rust
// mod.rs
mod github_client;
mod reqwest_github_client;

pub use github_client::GithubClient;
pub use reqwest_github_client::ReqwestGithubClient;

#[cfg(feature = "mock")]
mod mock_github_client;
#[cfg(feature = "mock")]
pub use mock_github_client::{GetPullRequestArgs, ListLabelsArgs, MockCall, MockGithubClient};
```

A second concrete implementation is a second file — `graphql_github_client.rs` →
`GraphqlGithubClient` — with no renaming anywhere else.

## Keeping mocks out of production builds

An off-by-default cargo feature satisfies both halves of the rule: `#[cfg(test)]` would hide the
mock from the downstream crates that need it most.

```toml
# the abstraction's Cargo.toml
[features]
mock = []
```

```toml
# a consumer's Cargo.toml — dev-dependencies only
[dev-dependencies]
github-client = { path = "../github-client", features = ["mock"] }
```

Do **not** enable `mock` in the consumer's normal `[dependencies]`. Because cargo unifies features
across a build graph, one crate enabling it in `[dependencies]` switches it on for every consumer.

CI must build with the feature on — `cargo check --all-features` — or the mock silently rots.

## Locks: std, not tokio

Use `std::sync::RwLock`, even when the trait is `async`. The mock never holds a guard across an
`.await` (lookup and pop are synchronous), so the async-lock rationale does not apply — and clippy's
`await_holding_lock` catches it if that ever stops being true.

This matters for one specific reason: `Drop` cannot be async, so a `tokio::sync::RwLock` would make
the automatic exhaustiveness check impossible. Std locks also let `recorded_calls()` be a plain
non-async method, and keep the mock usable from a sync trait unchanged.

## Args structs

One per required trait method, holding owned copies of that method's parameters.

```rust
#[derive(Clone, Debug, PartialEq)]
pub struct GetPullRequestArgs {
    pub repo: String,
    pub number: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ListLabelsArgs {
    pub repo: String,
    pub tags: Vec<String>,
    pub author: Option<String>,
}
```

Derives are `Clone, Debug, PartialEq` — **not** `Eq` or `Hash`. Seeds are matched by equality, not
hashed, so parameter types that cannot derive `Hash` (`f64`, `serde_json::Value`, `HashMap`, foreign
types) work without special handling.

Every field is owned. Conversion from the trait's borrowed parameters happens inside the mock method
and the seeding method, never at the call site.

## The call-log enum

One variant per required trait method, each carrying its args struct.

```rust
#[derive(Clone, Debug, PartialEq)]
pub enum MockCall {
    GetPullRequest(GetPullRequestArgs),
    ListLabels(ListLabelsArgs),
}
```

Scoped to this module, so several mock modules may each define `MockCall` — use sites qualify it
(`github_client::MockCall`).

## Mock struct and seed storage

Seeds are an ordered `Vec` of `(args, queue)` pairs. Alias the shape once, or clippy's
`type_complexity` fires on every field.

```rust
use std::collections::VecDeque;
use std::sync::RwLock;

type Seeds<A, T> = RwLock<Vec<(A, VecDeque<Result<T, GithubError>>)>>;

pub struct MockGithubClient {
    get_pull_request_seeds: Seeds<GetPullRequestArgs, PullRequest>,
    list_labels_seeds: Seeds<ListLabelsArgs, Vec<Label>>,
    calls: RwLock<Vec<MockCall>>,
}
```

If a return type is itself non-trivial, alias that too (`type LabelsByName = HashMap<String,
Label>;`) so every field stays one readable line.

## Constructors

```rust
impl MockGithubClient {
    #[must_use]
    pub fn new() -> Self {
        Self {
            get_pull_request_seeds: RwLock::new(Vec::new()),
            list_labels_seeds: RwLock::new(Vec::new()),
            calls: RwLock::new(Vec::new()),
        }
    }
}

impl Default for MockGithubClient {
    fn default() -> Self {
        Self::new()
    }
}
```

## Seeding methods

Named `with_<method>_response`. The signature mirrors the trait method exactly — `&str` stays
`&str`, `&[&str]` stays `&[&str]`, `Option<&str>` stays `Option<&str>` — plus a trailing `response`
of the method's return type. Owning happens inside.

```rust
#[must_use]
pub fn with_list_labels_response(
    self,
    repo: &str,
    tags: &[&str],
    author: Option<&str>,
    response: Result<Vec<Label>, GithubError>,
) -> Self {
    let args = ListLabelsArgs {
        repo: repo.to_string(),
        tags: tags.iter().map(|t| (*t).to_string()).collect(),
        author: author.map(String::from),
    };
    push_seed(&self.list_labels_seeds, args, response);
    self
}
```

The shared push — appending to an existing entry preserves FIFO for repeated same-args seeds:

```rust
fn push_seed<A: PartialEq, T>(
    seeds: &Seeds<A, T>,
    args: A,
    response: Result<T, GithubError>,
) {
    let mut seeds = seeds.write().expect("mock seed lock poisoned");
    match seeds.iter_mut().find(|(existing, _)| *existing == args) {
        Some((_, queue)) => queue.push_back(response),
        None => seeds.push((args, VecDeque::from([response]))),
    }
}
```

Lint pragmas, when they apply:

```rust
#[expect(
    clippy::too_many_arguments,
    reason = "mirrors GithubClient::list_labels plus one response arg"
)]
```

## The trait impl

```rust
#[async_trait]
impl GithubClient for MockGithubClient {
    async fn list_labels(
        &self,
        repo: &str,
        tags: &[&str],
        author: Option<&str>,
    ) -> Result<Vec<Label>, GithubError> {
        let args = ListLabelsArgs {
            repo: repo.to_string(),
            tags: tags.iter().map(|t| (*t).to_string()).collect(),
            author: author.map(String::from),
        };

        // Same level and field names as ReqwestGithubClient's request log.
        debug!(
            mock_method = "MockGithubClient::list_labels",
            repo, args = ?args, "mock list labels"
        );

        self.calls
            .write()
            .expect("mock call log poisoned")
            .push(MockCall::ListLabels(args.clone()));

        let response = take_seed(&self.list_labels_seeds, &args).unwrap_or_else(|| {
            error!(
                error_kind = "mock_no_response_configured",
                mock_method = "MockGithubClient::list_labels",
                args = ?args,
                "mock has no seeded response"
            );
            panic!("MockGithubClient::list_labels: no response seeded for args {args:?}");
        });

        debug!(
            mock_method = "MockGithubClient::list_labels",
            ok = response.is_ok(), "mock list labels response"
        );
        response
    }
}
```

```rust
fn take_seed<A: PartialEq, T>(
    seeds: &Seeds<A, T>,
    args: &A,
) -> Option<Result<T, GithubError>> {
    let mut seeds = seeds.write().expect("mock seed lock poisoned");
    seeds
        .iter_mut()
        .find(|(existing, _)| existing == args)
        .and_then(|(_, queue)| queue.pop_front())
}
```

Both guards are dropped before the function returns and no `.await` sits between acquire and
release, so concurrent calls under `tokio::join!` never block each other meaningfully and never
interfere.

## Reading the call log

```rust
#[must_use]
pub fn recorded_calls(&self) -> Vec<MockCall> {
    self.calls.read().expect("mock call log poisoned").clone()
}
```

Use it only for order-sensitive assertions. Where the code under test issues calls concurrently
(`tokio::join!`), order is not deterministic — sort a projection before asserting.

## The exhaustiveness check

```rust
impl MockGithubClient {
    /// Panic if any seeded response is still unconsumed.
    ///
    /// # Panics
    ///
    /// Panics with a per-method, per-args report of everything left over.
    pub fn assert_all_responses_consumed(&self) {
        let lines = self.unconsumed_report();
        assert!(
            lines.is_empty(),
            "MockGithubClient has unconsumed seeded responses:\n{}",
            lines.join("\n")
        );
    }

    fn unconsumed_report(&self) -> Vec<String> {
        let mut lines = Vec::new();
        collect_unconsumed(
            &self.get_pull_request_seeds,
            "MockGithubClient::get_pull_request",
            &mut lines,
        );
        collect_unconsumed(
            &self.list_labels_seeds,
            "MockGithubClient::list_labels",
            &mut lines,
        );
        lines
    }
}

fn collect_unconsumed<A: std::fmt::Debug, T>(
    seeds: &Seeds<A, T>,
    method: &str,
    lines: &mut Vec<String>,
) {
    let seeds = seeds.read().expect("mock seed lock poisoned");
    for (args, queue) in seeds.iter().filter(|(_, q)| !q.is_empty()) {
        lines.push(format!(
            "  {method}: {} unconsumed response(s) for args {args:?}",
            queue.len()
        ));
    }
}
```

## Automatic check on scope exit

`Drop` makes the check fire whether or not the test remembered to ask.

```rust
impl Drop for MockGithubClient {
    fn drop(&mut self) {
        // Never panic while the test is already failing: a double panic aborts
        // the process and buries the assertion that actually matters.
        if std::thread::panicking() {
            return;
        }
        let lines = self.unconsumed_report();
        assert!(
            lines.is_empty(),
            "MockGithubClient has unconsumed seeded responses:\n{}",
            lines.join("\n")
        );
    }
}
```

The `thread::panicking()` guard also covers the explicit method: when
`assert_all_responses_consumed` panics, `Drop` runs during unwinding and returns immediately.

`Drop` only fires if the mock is actually dropped inside the test. A mock held in an `Arc` that
outlives the test body — or leaked — never checks; call the explicit method there.

## Composite mocks

When a client owns several sub-abstractions and has a blessed all-mock alias, add an inherent impl
on that alias:

```rust
type MockReleaseClient = ReleaseClient<MockGithubClient, MockArtifactStore>;

impl MockReleaseClient {
    /// Panic if any child mock has unconsumed seeded responses.
    ///
    /// # Panics
    ///
    /// Panics if any child mock has unconsumed seeded responses.
    pub fn assert_all_responses_consumed(&self) {
        self.github.assert_all_responses_consumed();
        self.artifacts.assert_all_responses_consumed();
    }
}
```

Each child's own `Drop` still fires independently, so this is a convenience for a precise failure
point, not the sole enforcement.

## Default trait methods

A trait method with a default body that composes required methods via `self.*` gets **no** args
struct, **no** seed field, and **no** `MockCall` variant. The mock inherits the default body; the
required-method impls record the underlying calls as usual.

```rust
// Seed the primitives...
let mock = MockGithubClient::new()
    .with_get_pull_request_response("owner/repo", 12, Ok(pr))
    .with_list_labels_response("owner/repo", &["bug"], None, Ok(vec![label]));

// ...then call the composer. The real default body runs.
let summary = mock.pull_request_summary("owner/repo", 12).await?;
```

## Tests for the mock itself

Colocated in the mock file:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn records_call_and_returns_seeded_response() {
        let mock = MockGithubClient::new()
            .with_list_labels_response("owner/repo", &["bug"], None, Ok(vec![]));

        let got = mock.list_labels("owner/repo", &["bug"], None).await;

        assert_eq!(got.unwrap(), vec![]);
        assert_eq!(
            mock.recorded_calls(),
            vec![MockCall::ListLabels(ListLabelsArgs {
                repo: "owner/repo".to_string(),
                tags: vec!["bug".to_string()],
                author: None,
            })]
        );
    }

    #[tokio::test]
    #[should_panic(expected = "no response seeded for args")]
    async fn panics_when_no_response_seeded() {
        let mock = MockGithubClient::new();
        let _ = mock.list_labels("owner/repo", &["bug"], None).await;
    }

    #[tokio::test]
    async fn pops_responses_in_fifo_order_for_same_args() {
        let mock = MockGithubClient::new()
            .with_list_labels_response("owner/repo", &[], None, Ok(vec![first()]))
            .with_list_labels_response("owner/repo", &[], None, Ok(vec![second()]));

        assert_eq!(mock.list_labels("owner/repo", &[], None).await.unwrap(), vec![first()]);
        assert_eq!(mock.list_labels("owner/repo", &[], None).await.unwrap(), vec![second()]);
    }

    #[test]
    #[should_panic(expected = "unconsumed seeded responses")]
    fn asserts_unconsumed_responses() {
        let mock = MockGithubClient::new()
            .with_list_labels_response("owner/repo", &[], None, Ok(vec![]));
        mock.assert_all_responses_consumed();
    }
}
```

Note the FIFO test consumes both seeds — otherwise `Drop` fails it on the way out. That is the
design working, and it is why the last test calls the explicit method: it needs the panic to happen
at a known point rather than during unwinding.

## Rust review addendum

Run alongside the review checklist in `SKILL.md`. These catch mechanics-level mistakes the
language-agnostic checklist cannot see.

- **Feature gate** — `mock = []` exists and is not in `default`; the mock module and its re-exports
  sit behind `#[cfg(feature = "mock")]`.
- **Consumer wiring** — dependents enable the feature under `[dev-dependencies]` only. Anything
  enabling it under `[dependencies]` switches it on for the whole build graph.
- **CI coverage** — the feature is built somewhere (`cargo check --all-features` or equivalent).
  Otherwise the mock compiles only on the machine that last touched it.
- **Locks** — `std::sync`, not `tokio::sync`, and no guard alive across an `.await`.
- **Args derives** — `Clone, Debug, PartialEq` and nothing more. An `Eq` or `Hash` derive means
  someone reintroduced the hashing requirement.
- **Drop guard** — `Drop` is implemented and returns early on `std::thread::panicking()`.
- **Shared report** — `Drop` and `assert_all_responses_consumed` read the same report helper, so the
  two paths cannot disagree.
- **Seed append** — repeated same-args seeding pushes onto the existing queue rather than replacing
  it.
- **Lint pragmas** — `#[expect(...)]` rather than `#[allow(...)]`, each carrying a `reason` that
  names the mirrored signature.
- **`#[must_use]`** — on `new()` and on every `with_*_response` builder.
- **Test placement** — colocated `#[cfg(test)] mod tests`, with each `#[should_panic(expected = ...)]`
  substring specific enough to tell the no-seed panic from the unconsumed-seed panic.
