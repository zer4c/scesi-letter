# MVP Specification Package

Status: proposed specification; no application implementation is included.
Prepared on 2026-10-10. Repository instructions in `/AGENTS.md` apply.

This package defines a specification-driven development (SDD) workflow for a
small implementation model. Complete one task and its acceptance checks at a
time. Do not infer completed functionality from the current demonstration API.

## Reading Order

1. [Requirements and business rules](requirements.md)
2. [Decisions and unresolved prerequisites](decisions.md)
3. [Architecture and module boundaries](architecture.md)
4. [Data model and invariants](data-model.md)
5. [Security and signature lifecycle](security.md)
6. [API and event contracts](api.md)
7. [User experience](ui.md)
8. [External integrations and configuration](integrations.md)
9. [Implementation tasks](tasks.md)
10. [Acceptance scenarios and release gates](acceptance.md)
11. [Groq source evidence and Impeccable workflow](provider-notes.md)

## Authority and Change Control

Explicit user decisions take precedence over repository guidance. Requirements
with `BR-`, security rules with `SEC-`, and acceptance cases with `AC-` are
normative. Defaults labeled `PROPOSED` are reviewable engineering choices, not
previously confirmed product decisions. Provider facts labeled `UNVERIFIED`
must be checked before implementing the affected integration.

When a contract is insufficient, update the specification and record the
decision before implementing it. Do not silently simplify collaboration,
signature ownership, privacy, versioning, or OAuth to make a test pass.

## Small-Model Execution Protocol

For each task in `tasks.md`:

1. Read `/AGENTS.md`, the task card, and only its linked specifications.
2. Confirm dependency tasks are merged and their relevant checks pass.
3. Create the task branch from up-to-date `main`, following `/AGENTS.md`.
4. List the files and contracts affected. Implement only that task's scope.
5. Run its checks and the applicable backend, frontend, and Compose checks.
6. Record actual outcomes, unresolved issues, and changed assumptions in the
   task's review description. Provider tests without credentials are unrun.
7. Use an atomic English commit subject of at most 50 characters, including
   the type and colon. The task table supplies suitable examples.
8. Submit the branch for review. Start dependent work after its dependencies
   are available in `main`. Never force-push shared history for ordinary work.

For a larger card, make separately reviewable substeps: first its contract and
test fixture, then its minimal service, then its interface wiring. Keep each
substep coherent and stop at its validation gate before continuing. T10's binary
CRDT fixture and T13's encryption interoperability fixture are mandatory gates,
not optional follow-up tests.

Do not regenerate this package, expand into another task, or add another
service merely because a dependency is temporarily unavailable.

### Reusable Task Prompt

Give the implementation model one concrete task ID, not the whole MVP:

```text
Implement only TXX from specs/mvp/tasks.md.
Read AGENTS.md, that task card, and its relevant contracts first.
Confirm merged dependencies and unresolved prerequisites before coding.
Create the prescribed focused branch from current main.
Start with a failing contract/acceptance fixture, then the smallest implementation.
Use uv for Python and pnpm exclusively for JavaScript; pin resolved tools.
Follow installed Impeccable instructions for UI; do not claim unavailable skills.
Do not change business rules, add services, send real mail, or touch other tasks.
If a contract is ambiguous, report it and propose a spec correction before coding.
Run task checks; report passed, failed, skipped, and unrun checks separately.
Use atomic English commit subjects, including type, at most 50 characters.
Handoff: changed files, covered BR/SEC/AC IDs, evidence, and remaining blockers.
```

## Completion Definition

The MVP is complete only when the required cases in `acceptance.md` pass,
including two-user collaboration, signature isolation, immutable exports,
Drive synchronization, real personal and institutional Gmail sending, and an
actual Groq tool-calling check. Mocked integrations validate application logic
but do not establish external readiness.

Use pnpm exclusively for JavaScript work, including Impeccable installation,
Docker, and CI. Task T01 migrates the existing legacy dependency lock and commands
before implementation agents run frontend installation/build workflows.

Multiple simultaneous signers, free-position signature placement, a template
catalog, a version-history browsing screen, DOCX, scheduled arbitrary workflows,
and VPS deployment remain outside this release.
