---
name: mock-design
description: Use when writing, reviewing, or refactoring a reusable mock implementation of a dependency-injected interface/trait — one with both a production implementation and a mock implementation — or when deciding how a mock should seed responses, record calls, or verify that every seeded response was consumed. Not for one-off inline stubs written inside a single test.
---

# Mock design

## Overview

This skill defines one design for mock implementations of dependency-injected interfaces/traits.
When it applies, the rules below are requirements, not suggestions — a mock that skips any of them
loses the guarantee it was built for.

It governs the mock in front of you. It makes no claim on your team's process, your review gates,
or code you have not asked it about.

**Scope:** a reusable mock type that implements a production interface/trait alongside its real
implementation. Throughout, *real implementation* means the one that does the actual work — never a
name to use in code (see **Layout and naming**). Not throwaway stubs defined inline in a single test.

## What the design buys

Each guarantee below is the reason for a specific rule. Break the rule and you lose the guarantee.

- **Deterministic tests** — responses resolve by argument value, never by call order, so tests
  cannot flake on scheduling.
- **Concurrency-safe** — two calls in flight at once with different arguments each resolve their
  own seeded response, with no interference.
- **Seeding that cannot silently drift** — the seeding method mirrors the real method's signature,
  so a signature change breaks the test setup at compile/type-check time instead of at runtime.
- **Exhaustiveness** — a seeded response that is never consumed fails the test, catching drift
  between what the test set up and what the production code actually calls.
- **Honest interfaces** — the real interface is never reshaped to make its mock more convenient.

## The four components

Every mock built to this design has exactly these four, and nothing else:

1. **Args record** — one per interface method, holding an owned copy of that method's parameters.
   Compared by value equality.
2. **Seeded response queue** — for each (method, args) pair, a FIFO queue of responses to return.
3. **Call log** — an ordered record of every call the mock received, for order-sensitive assertions.
4. **Exhaustiveness check** — fails loudly if any seeded response was never consumed.

Args records need only be **equatable**, not hashable. Seeds are stored as an ordered list matched
by equality, not as a hash map. A mock holds a handful of seeds, so scanning is free — and the
looser requirement means parameter types that cannot be hashed (floats, JSON values, maps, foreign
types you cannot extend) still work.

## Layout and naming

One directory/module/package per abstraction, holding the interface, each concrete implementation,
and the mock. Everything about one dependency lives in one place, so a signature change breaks
every file that must change, together.

- **Interface/trait** — named for the capability: `github_client` → `GithubClient`.
- **Concrete implementation** — named for *how it is built*, never `real`: `reqwest_github_client`
  → `ReqwestGithubClient`. "Real" says nothing about the implementation and collides the moment a
  second one exists.
- **Mock** — the interface name with a mock marker: `mock_github_client` → `MockGithubClient`. The
  file name tells you the type it holds at a glance.

Apply your language's own casing and file-extension conventions; the structure is what binds.

## Seeding

The seeding method **mirrors the real method's signature exactly**, plus one trailing parameter of
the method's return type. Borrowed parameters stay borrowed; optional parameters stay optional.
Conversion to owned values happens inside the seeding method, never at the call site.

Seeding the same arguments more than once enqueues both responses; calls consume them in FIFO order.

## What a mock method does

Every mock method, in this order:

1. Build the args record from its parameters.
2. Emit the request log (see **Log parity**).
3. Append the call to the call log.
4. Find the seeded queue whose args equal this call's args and take the front entry.
5. If there is no seed for these args, **panic** naming the method and the arguments.
6. Emit the response log before returning.

## Unseeded calls panic

An unseeded call is a test-authoring bug. It cannot occur in production, so representing it as a
production error value is a category error — and a dangerous one: the code under test catches that
error, takes its failure path, and a test asserting exactly that failure path goes **green against a
mock that was never wired up**.

There are no defaults. A method returning a collection does not fall back to empty; a method
returning nothing does not fall back to success. "No results" is a seeded answer, not the absence of
one — and seeding it is one line that proves the call was reachable with the arguments you expected.

A mock with **zero seeds is perfectly legal** as long as nothing calls it. Nothing here forces a
seed you do not need; the rule bites only on the call. Exhaustiveness passes vacuously when there is
nothing to consume.

## Exhaustiveness

The check must **fire automatically when the mock goes out of scope**, wherever the language offers
a scope-exit or teardown hook. A guarantee that depends on the author remembering one line at the
bottom of a long test is not a guarantee — and the tests most likely to forget are the long ones
where drift actually happens.

Two requirements on the automatic check:

- It **must stay silent when the test is already failing.** An unconsumed-response panic raised
  during an existing failure masks the real assertion and sends the reader debugging the wrong thing.
- The **explicit method remains available and is never removed.** Automatic checks only fire if the
  mock is actually destroyed inside the test — a mock parked in a shared handle that outlives the
  test never checks. The explicit call is also how a test asserts consumption at a chosen point.

**Escape hatch:** in a language with no scope-exit hook to hang this on, the automatic check is
dropped and the explicit call becomes mandatory at the end of every test that seeds anything.

The failure message names every method and args combination with responses left over, and how many.

## Composite mocks

When an abstraction is a composite — a client owning several sub-abstractions, each with its own
mock — the composite exposes **one** exhaustiveness check that delegates to every child. A test
using the whole composite ends with a single call; a test using one child calls that child's check
directly.

## Mock the primitives, not the composers

Only the interface's **required** operations get an args record, a response queue, and a call-log
entry. Operations the interface derives by composing required ones — default/provided methods — get
none of the three.

A test for a derived operation seeds each primitive it calls, then invokes the derived operation.
The real composition logic runs; the call log shows the primitive calls. This keeps the mock surface
minimal and forces tests to exercise composition rather than a stubbed shortcut of it.

Where primitives run concurrently, the call log's order is not deterministic — assert on a sorted
projection.

## Log parity

Mock logs mirror the real implementation: **the same log level** the real implementation uses for
its request and response logs, and **the same field names**. Parity is defined relative to the real
implementation, so this rule needs no external logging standard — and it is what lets you compare a
mocked run against a real one without re-reading both implementations.

Two mock-specific additions:

- A field identifying the mock method, and a message clearly marked as coming from a mock.
- Mock-internal failures use a distinct error-kind prefix (e.g. `mock_no_response_configured`), so
  they never pollute dashboards that track real transport failures.

## Keep the mock out of production builds

**Binding outcome:** the mock must not reach production builds, while staying reachable from the
test code of other packages that depend on this one.

Both halves matter. Shipping the mock means dead weight in the binary and a mock implementation of a
production interface that production code can construct. But hiding it in a test-only scope that
peer packages cannot import defeats the point — downstream tests are the main consumer.

How this is enforced is language-specific; see the reference file. **Escape hatch:** in a language
with no mechanism that satisfies both halves, this rule is dropped rather than half-applied.

## Rules and invariants

- **Args equality is order-sensitive for sequence parameters** — `["a", "b"]` does not match
  `["b", "a"]`. Seed the exact order production code constructs. If production order genuinely
  varies, prefer making it deterministic over seeding both.
- **No state beyond the four components** — no counters, no flags, no per-test scratch fields. The
  seeds and the call log are the mock's complete state.
- **Never reshape the real interface to make its mock easier.** Real-code ergonomics is primary;
  mock ergonomics is secondary. An awkward seeding method is the cost of mirroring.
- **Mirror when it is clean, fall back when it is not.** If mirroring a specific parameter type is
  genuinely awkward, take the owned type in the seeding method. Do not contort either side.
- **The args records and the call-log type are the mock module's public surface** — tests import
  them by module path.

## Testing the mock itself

Every mock has its own tests. At minimum, per method:

- Seeds one response for specific args, calls, and asserts both the returned value and the recorded
  call.
- Calls without seeding and asserts it panics.
- Seeds two responses for the same args, calls twice, and asserts FIFO order.

Plus one test that leaves a response unconsumed and asserts the exhaustiveness check fails.

## Review checklist

Use this when **reviewing** a mock, not when writing one. These conditions are deliberately stripped
of their rationale — writing a mock requires the reasoning above, and a checklist is not a substitute
for it. Mark each **PASS**, **FAIL**, or **N/A**; for every FAIL, name the section that owns the rule.

- **Layout and naming** — one module per abstraction; the concrete implementation is named for how it
  is built, never `real`; the mock file name announces the type it holds. → *Layout and naming*
- **Args records** — one per required operation, fields owned, compared by equality; no hashability
  requirement imposed on parameter types. → *The four components*
- **Seeding signature** — mirrors the real operation's signature plus one trailing response;
  conversion to owned values happens inside, not at the call site. → *Seeding*
- **Call handling** — args built, request logged, call recorded, seed taken, response logged, in that
  order. → *What a mock method does*
- **Unseeded calls panic** — no fallback anywhere to an empty collection, a success value, or a
  production error type. → *Unseeded calls panic*
- **Exhaustiveness is automatic** — fires on scope exit, stays silent when the test is already
  failing, and the explicit method still exists. → *Exhaustiveness*
- **Composite delegation** — a composite exposes one check that reaches every child. → *Composite
  mocks*
- **Derived operations are unmocked** — operations composed from required ones have no args record,
  no seed queue, and no call-log entry. → *Mock the primitives, not the composers*
- **Log parity** — same level and field names as the real implementation, the mock identified, and
  mock-internal failures under a distinct error-kind prefix. → *Log parity*
- **Production exclusion** — the mock cannot reach a production build and can still be imported by a
  dependent package's tests. → *Keep the mock out of production builds*
- **No extra state** — seeds and call log only; no counters, flags, or scratch fields. → *Rules and
  invariants*
- **Self-tests present** — seeded-response, panic-when-unseeded, FIFO, and unconsumed-response tests
  all exist. → *Testing the mock itself*
- **Language mechanics** — the reference file's review addendum also passes. → *Language references*

## Language references

| Language | Reference |
| --- | --- |
| Rust | `reference/rust.md` |

For a language with no reference file, everything above still binds. Choose the closest idiom that
satisfies it, and apply an escape hatch only where this document explicitly grants one.
