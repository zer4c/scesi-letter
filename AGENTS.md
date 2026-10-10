# Repository Agent Instructions

## Scope

These instructions apply to the whole repository. More specific `AGENTS.md`
files may add constraints for their own directories.

## Language and content

- Write all source code, identifiers, comments, logs, tests, commit messages,
  branch names, and technical documentation in English.
- User-facing UI text may be localized. Keep the current Spanish UI only where
  it is intentionally presented to end users.
- Never add personal data, real credentials, private contact details, or
  institutional artifacts that are not explicitly required for development.
- Do not use emojis anywhere in source code, documentation, commits, or UI.
- Use Bootstrap Icons only for icons. Prefer the official inline SVG or the
  Bootstrap Icons class directly; do not introduce another icon library.

## Architecture

Use a modular monolith in both backend and frontend. Keep one deployable
application per side while separating business domains into modules.

Backend modules should follow this shape when a domain needs the layer:

```text
backend/app/
├── core/                  # settings, environment, shared infrastructure
└── modules/
    ├── automation/
    │   ├── controller.py
    │   ├── routes.py
    │   └── services.py
    └── user/
        ├── controller.py
        ├── routes.py
        └── services.py
```

Frontend features should use the same domain boundary:

```text
frontend/src/
├── core/                  # API client, configuration, shared infrastructure
├── shared/                # reusable UI primitives and utilities
└── modules/
    ├── automation/
    │   ├── components/
    │   ├── services/
    │   └── types.js
    └── user/
        ├── components/
        ├── services/
        └── types.js
```

Keep environment configuration in the relevant `core` area and load secrets
from environment variables. Do not hard-code secrets or environment-specific
values.

## Branching and GitFlow

- Never develop a new feature directly on `main`.
- Start every feature from an up-to-date `main` branch using
  `feature/<short-kebab-case>`, for example `feature/automation-new`.
- Use `fix/<short-kebab-case>` for bug fixes, `docs/<short-kebab-case>` for
  documentation-only work, and `chore/<short-kebab-case>` for maintenance.
- Keep changes focused. Merge through review into `main`; do not rewrite shared
  history unless the task explicitly requires history sanitization.

## Commits

- Make commits atomic: one coherent change per commit.
- Use the format `<type>: <message>`.
- Keep the complete commit subject at 50 characters or fewer.
- Use a concise imperative English subject.
- Allowed types include `feat`, `fix`, `docs`, `refactor`, `test`, `build`,
  `ci`, `chore`, and `perf`.
- Examples: `feat: add automation module`,
  `fix: validate webhook payload`, `docs: update setup guide`.
- Do not mix unrelated formatting, generated files, or refactors into a feature
  commit.

## Frontend quality

Before designing or changing frontend UI, follow the Impeccable frontend
workflow and principles:

https://impeccable.style/tutorials/getting-started/

Apply its guidance to hierarchy, spacing, typography, color, responsive layout,
states, accessibility, and implementation quality. Keep UI copy localized only
at the presentation boundary; keep components, props, services, and tests in
English.

## Tooling and validation

- Manage Python dependencies and projects with Astral `uv`.
- Use `pnpm` exclusively for JavaScript dependencies, scripts, builds, and
  one-off package commands. Never use `npm`, `npx`, or Yarn, including inside
  Dockerfiles, CI, setup scripts, or external-tool installation instructions.
- Pin the pnpm version in `packageManager`, commit `pnpm-lock.yaml`, and use
  `pnpm install --frozen-lockfile` for reproducible installations. Translate
  external instructions to pnpm; do not copy forbidden commands into workflows.
- Run the relevant backend tests and frontend production build before commit.
- Validate Docker Compose configuration when Docker-related files change.
- Never commit `node_modules`, virtual environments, build output, local logs,
  or environment files containing secrets.
