# MVP Release Verification Log

Run date: 2026-10-10

## Automated checks

| Check | Result | Evidence |
|---|---|---|
| Backend test suite | Passed | 48 passed, 2 skipped; Python 3.12; one upstream LangChain deprecation warning. Run from `backend/` with `uv run pytest -q`. |
| Frontend assistance tests | Passed | 2 passed with `pnpm --dir frontend test:assistance`. |
| Signature crypto tests | Passed | 1 passed with `pnpm --dir frontend test:signature-crypto`. |
| Yjs/pycrdt interoperability | Passed | Binary interoperability fixture passed with `pnpm --dir frontend interop:crdt`. |
| Frontend production build | Passed | Vite build passed; reports existing large-chunk warnings for PDF.js and CodeMirror bundles. |
| Backup script syntax | Passed | `bash -n scripts/backup-local.sh`. |
| Compose configuration | Passed | Default and port-isolated validation configurations pass `docker compose config --quiet`. |
| Docker image build / clean Compose runtime | Blocked | BuildKit could not resolve/fetch dependencies through the environment's proxy (Corepack/pnpm registry and Python package host). No application containers or volumes were changed by the failed builds. Retry in a runner with working outbound build networking. |

## Acceptance cases not exercised here

These require resources not available in this run and remain release gates, not
passed checks:

- AC-12 and AC-31: two real browser sessions, accessibility and responsive UI.
- AC-20, AC-21, AC-22, AC-26, and live-provider portions of AC-30: controlled
  Google OAuth, Drive and Gmail test accounts and an explicitly approved test
  send. No email was sent and no provider credentials were used.
- AC-32/AC-38: a securely configured Groq account and current free-plan/tool
  round trip; documentation is not a substitute for live account verification.
- AC-33/AC-39: final approved template assets and the project's reviewed
  Impeccable PRODUCT/DESIGN context plus browser audit.
- AC-35: a real MongoDB/artifact backup-and-restore drill, clean Docker startup,
  and bootstrap idempotence. The runbook and backup script are in place, but the
  blocked image build prevented exercising them in an isolated local runtime.
- AC-37: the pnpm checks passed locally, but a frozen clean Docker install/build
  is still unverified because the image build could not download dependencies.

The API/unit tests do not establish every security and concurrency scenario in
`acceptance.md`. The MVP must not be described as fully release-verified until
the blocked runtime, browser, asset, and provider checks are completed with
synthetic identities and controlled test accounts.
